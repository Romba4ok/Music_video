"""Daily song prefetch (memory = md table, see HEAD): wanted songs (queue.md + KZ chart) -> allowed sources only (config licenses_allowed) -> verified MP3 -> out dir.
The workflow then uploads the folder to Drive/audio with rclone. Nothing is bypassed: a song with no licensed full recording is skipped and journaled.
python -m pipeline songs --out out/fetched [--have-file out/have.txt] [--state out/songs-memory.md] [--max 5] [--tries 40]
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

from . import download, song_ideas, sources
from .batch import parse_queue
from .common import ROOT, license_ok, load_config, parse_name, safe_err

RETRY_DAYS = 14  # a skipped song is searched again after this long (new uploads appear)
MIN_SEC, MAX_SEC = 90, 600  # full composition: not a 30 s preview, not a mix


def key(artist, title):
    return re.sub(r"[\W_]+", "", re.sub(r"[\(\[].*?[\)\]]", "", f"{artist}{title}").lower())


HEAD = """# Память песен

<!-- Пишет pipeline/fetch_songs.py (Drive/state/songs.md). status: used = ролик сделан, песня не повторяется;
     downloaded = скачана из разрешённого источника; skipped = лицензионной полной записи нет, поиск повторится через 14 дней. -->

| status | date | song | file | detail |
|---|---|---|---|---|
"""


def load_memory(path):
    """md table -> {"done": {key: row}, "skipped": {key: row}}. Rows that do not parse are ignored (the file is human-editable)."""
    st = {"done": {}, "skipped": {}}
    if not Path(path).exists():
        return st
    for ln in Path(path).read_text(encoding="utf-8").splitlines():
        c = [x.strip() for x in ln.strip().strip("|").split("|")]
        if len(c) >= 3 and c[0] in ("used", "downloaded", "skipped") and re.match(r"\d{4}-\d{2}-\d{2}", c[1]):
            a, t = parse_name(c[2])
            row = {"status": c[0], "date": c[1], "song": c[2], "file": c[3] if len(c) > 3 else "", "detail": c[4] if len(c) > 4 else ""}
            st["skipped" if c[0] == "skipped" else "done"][key(a, t)] = row
    return st


def save_memory(path, st, keep_skipped=300):
    cell = lambda x: " ".join(str(x).replace("|", "/").split())
    rows = sorted(st["done"].values(), key=lambda r: r["date"]) + sorted(st["skipped"].values(), key=lambda r: r["date"])[-keep_skipped:]
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    lines = [f'| {r["status"]} | {r["date"]} | {cell(r["song"])} | {cell(r["file"])} | {cell(r["detail"])[:160]} |' for r in rows]
    Path(path).write_text(HEAD + "\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")


def record_used(st, names, today):
    """Names of audio files that were processed (Drive/done): remembered as used, so the folder can be emptied without forgetting them."""
    for n in names:
        a, t = parse_name(os.path.splitext(n.strip())[0])
        if t and key(a, t) not in st["done"]:
            st["done"][key(a, t)] = {"status": "used", "date": today, "song": f"{a} - {t}" if a else t, "file": n.strip(), "detail": ""}
            st["skipped"].pop(key(a, t), None)


def taste_artists(st):
    """Artists of songs already made (memory `used`): the owner's taste, letters only, lowercase."""
    return {re.sub(r"[\W_]+", "", parse_name(r["song"])[0].lower()) for r in st["done"].values() if r["status"] == "used" and parse_name(r["song"])[0]}


def fits(artist, title, taste):
    """Russian-language chart song: Cyrillic in artist or title, or an artist the owner already uses (Latin spelling, e.g. Guf, Jah Khalib)."""
    if re.search(r"без слов|instrumental|инструментал|минус|karaoke|караоке|remix|ремикс|cover|кавер", f"{artist} {title}".lower()):
        return False  # no vocals to read lyrics from, or another recording of someone else's song
    return bool(re.search("[а-яё]", f"{artist}{title}".lower())) or re.sub(r"[\W_]+", "", artist.lower()) in taste


def wanted(cfg, queue_text="", fetch_chart=None, taste=frozenset()):
    """[{artist, title, sec}] queue first (curated by brief.md), then the chart songs that fit (Russian / owner's artists; owner's artists first).
    Chart failure = queue only."""
    out = [{"artist": e["artist"], "title": e["title"], "sec": 0} for e in parse_queue(queue_text)]
    try:
        rows = (fetch_chart or _chart)(cfg)
    except Exception as e:
        print("songs: chart unavailable:", safe_err(e), file=sys.stderr)
        rows = []
    own, other = [], []
    for r in rows:
        a, t = parse_name(r["title"])
        if a and t and fits(a, t, taste):
            (own if re.sub(r"[\W_]+", "", a.lower()) in taste else other).append({"artist": a, "title": t, "sec": r.get("sec", 0)})
    out += own + other
    seen, uniq = set(), []
    for w in out:
        if key(w["artist"], w["title"]) not in seen:
            seen.add(key(w["artist"], w["title"]))
            uniq.append(w)
    return uniq


def _chart(cfg):
    k = os.environ.get("YOUTUBE_API_KEY")
    if k:
        return song_ideas.pick(song_ideas.fetch(cfg.get("trends", {}).get("region", "KZ"), k), top=50)
    return song_ideas.fetch_deezer()


def to_mp3(src, dst):
    if Path(src).suffix.lower() == ".mp3":
        if Path(src) != Path(dst):
            Path(src).replace(dst)
        return dst
    r = subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(src), "-vn", "-codec:a", "libmp3lame", "-q:a", "2", str(dst)], capture_output=True, text=True)
    if r.returncode or not Path(dst).exists():
        raise RuntimeError("ffmpeg mp3 conversion failed: " + (r.stderr or "")[-150:])
    Path(src).unlink(missing_ok=True)
    return dst


def fetch_one(w, cfg, out, searchers=None, dl=None, check=None, dead=None):
    """-> (file name | None, reason). Tries every matching candidate until one downloads, passes check_audio and is a full-length track.
    `dead` (shared set): sources that failed with a network/API error are not asked again in this run (each failure costs ~60 s of retries)."""
    dl, check = dl or download.download, check or download.check_audio
    dead = set() if dead is None else dead
    cfg = {**cfg, "sources": {**cfg["sources"], "order": [o for o in cfg["sources"]["order"] if o != "local" and o not in dead]}}
    cands, sts = sources.search(f'{w["artist"]} {w["title"]}', cfg, n=8, searchers=searchers)
    dead.update(x["source"] for x in sts if x["state"] == "unavailable")
    good = [c for c in cands if sources.matches(w["artist"], w["title"], c, w["sec"])]
    if not good:
        return None, f"no licensed match ({len(cands)} found, 0 matching; {', '.join(s['source'] + ':' + s['state'] for s in sts)})"
    Path(out).mkdir(parents=True, exist_ok=True)
    tmp = Path(out) / "_tmp"
    for c in good:
        try:
            raw = dl(c, tmp, cfg)
            path, _ = check(raw, min_sec=MIN_SEC, max_sec=MAX_SEC, fixdir=tmp / "fix")
            name = f'{download._slug(w["artist"])} - {download._slug(w["title"])}.mp3'
            final = to_mp3(path, Path(out) / name)
            lic = Path(str(raw) + ".license.json")
            side = json.loads(lic.read_text(encoding="utf-8")) if lic.exists() else {"attribution": c.attribution(), "license": c.license}
            side["source_site"] = c.source
            (Path(out) / (name + ".license.json")).write_text(json.dumps(side, ensure_ascii=False, indent=1), encoding="utf-8")
            return name, f"{c.source}: {c.attribution()}"
        except Exception as e:  # this candidate is bad (refused, damaged, preview): try the next one
            last = f"{c.source}: {type(e).__name__} {str(e)[:100]}"
    return None, last


PREVIEW_CLIPS = ("https://itunes.apple.com/search", "https://api.deezer.com/search")
AUDIO_EXT = (".mp3", ".wav", ".m4a", ".ogg", ".flac")


def preview_candidates(w, get=None):
    """Official 30 s promo clips (Apple Music KZ, Deezer) of the wanted song -> [Candidate]. Only clips the services publish for free through their public APIs."""
    get = get or sources.get_json
    q = f'{w["artist"]} {w["title"]}'
    out = []
    try:
        for r in get(PREVIEW_CLIPS[0], {"term": q, "country": "kz", "entity": "song", "limit": 8}).get("results", []):
            if r.get("previewUrl"):
                out.append(sources.Candidate("apple-preview", r.get("trackName") or "", r.get("artistName") or "", r["previewUrl"], "official-preview", "", r.get("trackViewUrl") or "", sec=30))
    except Exception as e:
        print("songs: apple preview search failed:", safe_err(e), file=sys.stderr)
    try:
        for r in get(PREVIEW_CLIPS[1], {"q": q, "limit": 8}).get("data", []):
            if r.get("preview"):
                out.append(sources.Candidate("deezer-preview", r.get("title") or "", (r.get("artist") or {}).get("name") or "", r["preview"], "official-preview", "", r.get("link") or "", sec=30))
    except Exception as e:
        print("songs: deezer preview search failed:", safe_err(e), file=sys.stderr)
    return [c for c in out if sources.matches(w["artist"], w["title"], c, 0)]


def fetch_preview(w, out, cands=None, http=None):
    """Download the first matching official preview as `Artist - Title.mp3` + a sidecar marked analysis_only (lyric timing; never the sound of a video).
    -> (file name | None, detail)."""
    import requests
    http = http or requests
    cands = preview_candidates(w) if cands is None else cands
    if not cands:
        return None, "нет совпадающего официального превью (Apple, Deezer)"
    Path(out).mkdir(parents=True, exist_ok=True)
    tmp = Path(out) / "_tmp"
    tmp.mkdir(parents=True, exist_ok=True)
    last = ""
    for c in cands:
        try:
            if not c.url.startswith("https://"):
                raise ValueError("not https")
            r = http.get(c.url, timeout=30)
            r.raise_for_status()
            if len(r.content) > 5 * 1024 * 1024:
                raise ValueError("clip is too large")
            raw = tmp / ("preview" + (Path(c.url.split("?")[0]).suffix or ".mp3"))
            raw.write_bytes(r.content)
            path, _ = download.check_audio(raw, min_sec=20, max_sec=60, fixdir=tmp / "fix")
            name = f'{download._slug(w["artist"])} - {download._slug(w["title"])}.mp3'
            to_mp3(path, Path(out) / name)
            (Path(out) / (name + ".license.json")).write_text(json.dumps({"attribution": "", "license": "official-preview", "analysis_only": True,
                "source": c.landing, "source_site": c.source, "note": "official 30 s promo clip; used only to time the lyrics, never mixed into a video"}, ensure_ascii=False, indent=1), encoding="utf-8")
            return name, f"превью {c.source}: {c.artist} - {c.title}"
        except Exception as e:
            last = f"{c.source}: {type(e).__name__} {str(e)[:80]}"
    return None, last


def off_list(audio_dir, queue_text):
    """Audio files in the folder that are NOT songs of queue.md (the workflow stops if any)."""
    qk = {key(e["artist"], e["title"]) for e in parse_queue(queue_text)}
    bad = []
    for f in sorted(Path(audio_dir).glob("*")) if Path(audio_dir).exists() else []:
        if f.suffix.lower() in AUDIO_EXT or f.suffix.lower() in (".mp4", ".mov", ".mkv", ".webm", ".m4v"):
            a, t = parse_name(f.stem)
            if key(a, t) not in qk:
                bad.append(f.name)
    return bad


DISCOVER_QUERIES = ["песня", "любовь", "город", "ночь", "душа", "дорога", "осень", "мечта", "сердце", "время"]


def discover(cfg, out, seen, need, find=None, sleep=time.sleep, day=None):
    """Fallback when the queue and the chart gave too little: Russian-titled full tracks under an allowed license found by browsing Openverse.
    Mostly independent artists, NOT what is in the chart. -> [(wanted dict, file name, detail)]. `seen` = keys already known (mutated)."""
    find = find or (lambda q: sources._openverse(q, 20, cfg, {}))
    day = time.gmtime().tm_yday if day is None else day
    got, dead = [], set()
    for i in range(len(DISCOVER_QUERIES)):
        if len(got) >= need:
            break
        try:
            cands = find(DISCOVER_QUERIES[(day + i) % len(DISCOVER_QUERIES)])
        except Exception as e:
            print("songs: discover failed:", safe_err(e), file=sys.stderr)
            continue
        for c in cands:
            k = key(c.artist, c.title)
            if len(got) >= need:
                break
            if k in seen or not fits(c.artist, c.title, frozenset()) or not (100 <= (c.sec or 180) <= 420) or not license_ok(c.license or c.license_url, cfg["licenses_allowed"]):
                continue
            seen.add(k)
            w = {"artist": c.artist, "title": c.title, "sec": c.sec}
            name, why = fetch_one(w, cfg, out, {"openverse": lambda q, n, cf, e, c=c: [c]}, dead=dead)
            if name:
                got.append((w, name, why))
        sleep(1)
    return got


def run(a, cfg=None, searchers=None, fetch_chart=None, sleep=time.sleep, find=None, preview_find=None):
    cfg = cfg or load_config()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    state_f = Path(a.state)
    state = load_memory(state_f)
    today = time.strftime("%Y-%m-%d", time.gmtime())
    if a.record_used:
        record_used(state, [l for l in open(a.record_used, encoding="utf-8").read().splitlines() if l.strip()], today)
        save_memory(state_f, state)
        print(json.dumps({"recorded_used": len(state["done"])}, ensure_ascii=False))
        return []
    taste = taste_artists(state)
    if a.prune:  # songs this job downloaded earlier that do not fit (not Russian / not the owner's artists): the workflow deletes these files from Drive/audio
        bad = [(k, r) for k, r in state["done"].items() if r["status"] == "downloaded" and r["file"] and not fits(*parse_name(r["song"]), taste)]
        Path(a.prune).write_text("".join(f'{r["file"]}\n{r["file"]}.license.json\n' for _, r in bad), encoding="utf-8")
        for k, r in bad:
            state["done"].pop(k)
            state["skipped"][k] = {**r, "status": "skipped", "date": today, "file": "", "detail": "удалена: не на русском и не из ваших артистов"}
        save_memory(state_f, state)
        print(json.dumps({"pruned": [r["file"] for _, r in bad]}, ensure_ascii=False))
        return []
    have = [key(*parse_name(os.path.splitext(l.strip())[0])) for l in open(a.have_file, encoding="utf-8") if l.strip()] if a.have_file and os.path.exists(a.have_file) else []
    q = Path(a.queue)
    qtext = q.read_text(encoding="utf-8") if q.exists() else ""
    qkeys = {key(e["artist"], e["title"]) for e in parse_queue(qtext)}  # previews only for songs of the owner's list
    got, tries, dead = [], 0, set()
    for w in wanted(cfg, qtext, fetch_chart, taste):
        k = key(w["artist"], w["title"])
        if len(got) >= a.max or tries >= a.tries:
            break
        if k in have or k in state["done"]:
            continue
        sk = state["skipped"].get(k)
        known_none = bool(sk and time.mktime(time.strptime(today, "%Y-%m-%d")) - time.mktime(time.strptime(sk["date"], "%Y-%m-%d")) < RETRY_DAYS * 86400)
        want_preview = a.previews and k in qkeys
        if known_none and not want_preview:
            continue
        tries += 1
        name, why = (None, sk["detail"]) if known_none else fetch_one(w, cfg, out, searchers, dead=dead)  # no licensed full file is already known: go straight to the preview
        if not name and want_preview:
            name, why = fetch_preview(w, out, None if preview_find is None else preview_find(w))
        if name:
            state["done"][k] = {"status": "downloaded", "date": today, "song": f'{w["artist"]} - {w["title"]}', "file": name, "detail": why}
            state["skipped"].pop(k, None)
            got.append(name)
        else:
            state["skipped"][k] = {"status": "skipped", "date": today, "song": f'{w["artist"]} - {w["title"]}', "file": "", "detail": why}
        sleep(1)  # be polite to the free APIs
    if a.discover and len(got) < a.max:
        seen = set(have) | set(state["done"]) | set(state["skipped"])
        for w, name, why in discover(cfg, out, seen, a.max - len(got), find, sleep):
            k = key(w["artist"], w["title"])
            state["done"][k] = {"status": "downloaded", "date": today, "song": f'{w["artist"]} - {w["title"]}', "file": name, "detail": "discover " + why}
            got.append(name)
    shutil.rmtree(out / "_tmp", ignore_errors=True)
    save_memory(state_f, state)
    print(json.dumps({"downloaded": got, "tried": tries, "skipped_total": len(state["skipped"])}, ensure_ascii=False))
    return got


def main(argv):
    ap = argparse.ArgumentParser(prog="pipeline songs")
    ap.add_argument("--out", default="out/fetched")
    ap.add_argument("--have-file", help="names already in Drive (audio/ and done/), one per line")
    ap.add_argument("--state", default="out/songs-memory.md", help="memory (md table): used, downloaded and skipped songs")
    ap.add_argument("--discover", action="store_true", help="if the queue/chart gave fewer than --max songs: browse open sources for Russian-titled tracks (indie, not chart)")
    ap.add_argument("--previews", action="store_true", help="for queue.md songs with no licensed full file: take the official 30 s preview (Apple/Deezer) for lyric timing only; the video must then be made in mode tiktok")
    ap.add_argument("--check-list", help="audio folder: exit 1 if it holds a song that is not in queue.md (the workflow stops), search nothing")
    ap.add_argument("--prune", help="write to this file the names of earlier downloads that do not fit (not Russian / not your artists), forget them in the memory, search nothing")
    ap.add_argument("--record-used", help="text file of processed audio names (Drive/done): only add them to the memory as `used`, search nothing")
    ap.add_argument("--queue", default=str(ROOT / "accounts" / "main" / "queue.md"))
    ap.add_argument("--max", type=int, default=5, help="max new songs per run")
    ap.add_argument("--tries", type=int, default=40, help="max songs searched per run")
    a = ap.parse_args(argv)
    if a.check_list:
        q = Path(a.queue)
        bad = off_list(a.check_list, q.read_text(encoding="utf-8") if q.exists() else "")
        print(json.dumps({"not_in_list": bad}, ensure_ascii=False))
        return 1 if bad else 0
    run(a)
    return 0  # finding nothing is a normal outcome, not a failure


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
