"""Daily song prefetch (memory = md table, see HEAD): wanted songs (queue.md + KZ chart) -> allowed sources only (config licenses_allowed) -> verified MP3 -> out dir.
The workflow then uploads the folder to Drive/audio with rclone. Nothing is bypassed: a song with no licensed full recording is skipped and journaled.
python -m pipeline songs --out out/fetched [--have-file out/have.txt] [--state out/songs-memory.md] [--max 5] [--tries 40]
"""
import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.parse import urlsplit

import requests

from . import download, official, song_identity, song_ideas, sources
from .batch import parse_queue
from .common import ROOT, http_summary, license_ok, load_config, parse_name, safe_err

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
    lines = [f'| {r["status"]} | {r["date"]} | {cell(r["song"])} | {cell(r["file"])} | {cell(r["detail"])[:360]} |' for r in rows]
    Path(path).write_text(HEAD + "\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")


def record_used(st, names, today):
    """Names of audio files that were processed (Drive/done): remembered as used, so the folder can be emptied without forgetting them."""
    for n in names:
        if Path(n.strip()).suffix.lower() not in ('.mp3', '.wav', '.m4a', '.ogg', '.flac', '.mp4', '.webm', '.mkv', '.mov'):
            continue
        a, t = parse_name(os.path.splitext(n.strip())[0])
        k = key(a, t)
        previous = st['done'].get(k, {})
        if t and previous.get('status') != 'used':
            st["done"][k] = {**previous, "status": "used", "date": today,
                             "song": previous.get('song') or (f"{a} - {t}" if a else t),
                             "file": n.strip(), "detail": previous.get('detail', '')}
            st["skipped"].pop(k, None)


def known_sha(st):
    """sha256 prefixes of files already saved (written into the memory `detail` by fetch_url)."""
    return {m.group(1) for r in st["done"].values() for m in [re.search(r"sha256:([0-9a-f]{16})", r["detail"])] if m}


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
    out = [{"artist": e["artist"], "title": e["title"], "popular_line": e["popular_line"],
            "sec": 0, "url": e["audio_file"] if e["audio_file"].lower().startswith(("http://", "https://")) else ""}
           for e in parse_queue(queue_text)]
    try:
        rows = (fetch_chart or _chart)(cfg)
    except Exception as e:
        print("songs: chart unavailable:", safe_err(e), file=sys.stderr)
        rows = []
    own, other = [], []
    for r in rows:
        a, t = (r["artist"].strip(), r["title"].strip()) if r.get("artist") else parse_name(r["title"])
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


def _apple_chart(country):
    """Apple Music charts supply track names only. Audio still goes through fetch_one."""
    data = sources.get_json(f"https://rss.marketingtools.apple.com/api/v2/{country}/music/most-played/100/songs.json",
                            timeout=10, retries=1)
    return [{"artist": row["artistName"], "title": row["name"]} for row in data["feed"]["results"]
            if isinstance(row.get("artistName"), str) and isinstance(row.get("name"), str)]


def _fallback_charts():
    return [("Apple Music KZ", lambda cfg: _apple_chart("kz")),
            ("Apple Music RU", lambda cfg: _apple_chart("ru"))]


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


def fetch_one(w, cfg, out, searchers=None, dl=None, check=None, dead=None, *, known_sha=(), download_only=False):
    """Try matching downloadable tracks in source order until one passes validation."""
    if download_only and dl is None:
        from .catalog_audio import download_candidate
        dl = download_candidate
    dl, check = dl or download.download, check or download.check_audio
    dead = set() if dead is None else dead
    states = [f"{name}:unavailable" for name in sorted(dead)]
    order = [name for name in cfg["sources"]["order"] if name != "local" and name not in dead]
    cfg = {**cfg, "sources": {**cfg["sources"], "order": order}}
    out = Path(out)
    seen_urls = set()
    limited_hosts = set()
    candidate_count = 0
    failures = []
    track = (w["artist"], w["title"])
    batches = sources.search_batches(" ".join(track), cfg, n=8, searchers=searchers, track=track, download_only=download_only)
    for candidates, status in batches:
        source, state = status["source"], status["state"]
        states.append(f"{source}:{state}")
        if state == "unavailable":
            dead.add(source)
        candidate_count += len(candidates)
        for c in candidates:
            if not sources.matches(w["artist"], w["title"], c, w["sec"], collaborations=download_only) or c.url in seen_urls:
                continue
            host = urlsplit(c.url).hostname
            if host in limited_hosts:
                continue
            seen_urls.add(c.url)
            sources.bump(c.source, matched=1)
            try:
                out.mkdir(parents=True, exist_ok=True)
                with TemporaryDirectory(dir=out) as staging:
                    staging = Path(staging)
                    raw = dl(c, staging, cfg)
                    digest = download.file_sha256(raw)
                    if digest in known_sha or digest[:16] in known_sha or download.find_duplicate(out, raw, digest):
                        raise download.Refused("same audio already saved")
                    path, _ = check(raw, min_sec=MIN_SEC, max_sec=MAX_SEC, fixdir=staging / "fix")
                    name = f'{download._slug(w["artist"])} - {download._slug(w["title"])}.mp3'
                    lic = Path(str(raw) + ".license.json")
                    side = json.loads(lic.read_text(encoding="utf-8")) if lic.exists() else {"attribution": c.attribution(), "license": c.license}
                    side.update(source_site=c.source, sha256=digest)
                    if download_only:
                        side["identity"] = song_identity.verify(path, *track, w.get("popular_line", ""))
                        side.update(usage_rights="not_evaluated", download_only=True, analysis_only=True)
                    final = to_mp3(path, staging / name)
                    download._sidecar(final, side)
                    download.publish_audio(final, final, out)
                sources.bump(c.source, downloaded=1)
                return name, f"{c.source} sha256:{digest[:16]}: {c.attribution()}"
            except requests.RequestException as exc:
                code = getattr(exc.response, "status_code", 0)
                if code == 429:
                    limited_hosts.add(host)
                state_name = "refused" if code in (401, 403, 404, 410) else "unavailable"
                failures.append(f"{source}:{state_name} ({safe_err(exc)})")
            except (download.Refused, download.BadAudio) as exc:
                failures.append(f"{source}:refused ({exc})")
            except (OSError, RuntimeError, ValueError) as exc:
                failures.append(f"{source}:unavailable ({safe_err(exc)})")
    details = ", ".join(states + failures[:4])
    if failures:
        return None, f"no usable download ({details})"
    result = "no matching recording" if download_only else "no licensed match"
    return None, f"{result} ({candidate_count} found, 0 matching; {details})"


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


ALGO_VERSION = "2026-11-18.1"  # bump it when the search / matching algorithm changes: every skipped song is then searched again


def search_signature(cfg, env=None):
    """Short hash of everything that decides what a search can find: sources and their order, allowed licenses and hosts, which credentials exist, the
    algorithm version. A skipped song keeps the signature it was skipped under; another signature = 'checked with something else' = searched again now."""
    env = os.environ if env is None else env
    cred = sorted(n for n in ("JAMENDO_CLIENT_ID", "SOUNDCLOUD_CLIENT_ID", "YOUTUBE_API_KEY") if env.get(n))
    blob = json.dumps([ALGO_VERSION, cfg.get("sources", {}).get("order"), sorted(cfg.get("licenses_allowed", [])),
                       sorted((cfg.get("direct_urls") or {}).get("allowed_hosts", [])), cred, (cfg.get("official") or {}).get("enabled", True)], ensure_ascii=False)
    return hashlib.sha1(blob.encode("utf-8")).hexdigest()[:8]


TAG = re.compile(r"^\[sig:(\w+) n:(\d+) first:(\d{4}-\d{2}-\d{2})\]\s*")


def read_tag(detail):
    """'[sig:ab12 n:3 first:2026-11-16] reason' -> (sig, attempts, first date, reason). Old rows without a tag -> ('', 0, '', detail)."""
    m = TAG.match(detail or "")
    return (m.group(1), int(m.group(2)), m.group(3), detail[m.end():]) if m else ("", 0, "", detail or "")


def tag(sig, prev, today, why):
    """Same song, same row: the attempt counter grows and the first date stays, so nothing of the history is lost and no duplicate row appears."""
    _, n, first, _ = read_tag(prev["detail"]) if prev else ("", 0, "", "")
    return f"[sig:{sig} n:{n + 1} first:{first or (prev or {}).get('date') or today}] {why}"


def needs_recheck(sk, sig, today, force=False):
    """A skipped song is searched again when: --force-retry; the search signature changed (sources, permissions, credentials, algorithm); a source did not
    answer (that is not a real 'no'); or RETRY_DAYS have passed."""
    if force:
        return True
    s, _, _, why = read_tag(sk["detail"])
    if s != sig or ":unavailable" in why:
        return True
    age = time.mktime(time.strptime(today, "%Y-%m-%d")) - time.mktime(time.strptime(sk["date"], "%Y-%m-%d"))
    return age >= RETRY_DAYS * 86400


def run(a, cfg=None, searchers=None, fetch_chart=None, sleep=time.sleep, find=None, preview_find=None, official_try=None,
        *, replacement_attempts=None, stop_at=None):
    cfg = cfg or load_config()
    download_only = getattr(a, "download_only", False)
    if download_only:
        from . import catalog_audio
        cfg = {**cfg, "sources": {**cfg["sources"], "order": list(catalog_audio.SITES)}}
        searchers = searchers or catalog_audio.searchers()
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
    sig = search_signature(cfg)
    if download_only:
        sig = hashlib.sha1((sig + ":download-only-lyrics-v4").encode()).hexdigest()[:8]
    # Public catalogs exhaust the existing queue before asking for chart additions.
    cands = wanted(cfg, qtext, (lambda cfg: []) if download_only else fetch_chart, taste)
    got, tries, dead, blocked, retried, skip_kinds, src_states = [], 0, set(), 0, 0, {}, {}
    sources.STATS.clear()
    octx = official.Ctx(cache_file=state_f.with_name("musicbrainz-cache.json"))  # MusicBrainz / page answers are shared by all songs of this run
    if not download_only and cfg.get("official", {}).get("enabled", True) and not octx.contact:
        print("songs: MUSICBRAINZ_CONTACT не настроен: MusicBrainz получит User-Agent 'VYBEX/1.0' без контакта (задайте переменную репозитория с вашим адресом или URL проекта)", file=sys.stderr)
    links, per_song = [], []  # links: (song, page, note) found by the official stage; per_song: one report row per checked song
    pending = []  # (wanted song, key, previous skipped row or None)
    skipped_known, chart_checked, queue_added = 0, not download_only, []
    charts = iter([("primary", fetch_chart or _chart), *_fallback_charts()]) if download_only and replacement_attempts is None else iter(())
    chart_log = []
    queue_update = None

    def enqueue(items):
        nonlocal blocked, skipped_known
        for w in items:
            k = key(w['artist'], w['title'])
            if k in have or k in state['done'] or (replacement_attempts is not None and k in replacement_attempts):
                skipped_known += 1
                continue
            sk = state['skipped'].get(k)
            if sk is None or needs_recheck(sk, sig, today, a.force_retry) or (a.previews and k in qkeys):
                pending.append((w, k, sk))
            else:
                blocked += 1

    def refill_from_chart(label, loader):
        nonlocal chart_checked, queue_update
        chart_checked = True
        seen = {key(w['artist'], w['title']) for w in cands} | set(have) | set(state['done'])
        fresh = [w for w in wanted(cfg, '', loader, taste) if key(w['artist'], w['title']) not in seen]
        cands.extend(fresh)
        enqueue(fresh)
        chart_log.append({"chart": label, "new_tracks": len(fresh)})
        print(f"songs: {label}: {len(fresh)} new chart tracks", file=sys.stderr, flush=True)
        if fresh:
            cell = lambda value: ' '.join(value.replace('|', '/').split())
            # Keep the explicit file field so the existing consumer applies its
            # normal metadata/usage checks to chart tracks as well.
            queue_added.extend(
                f"{cell(w['artist'])} | {cell(w['title'])} | | {download._slug(w['artist'])} - {download._slug(w['title'])}.mp3"
                for w in fresh
            )
            queue_update = state_f.with_name('queue-next.md')
            queue_update.parent.mkdir(parents=True, exist_ok=True)
            queue_update.write_text(qtext.rstrip() + '\n\n' + '\n'.join(queue_added) + '\n', encoding='utf-8')

    enqueue(cands)
    if download_only and replacement_attempts is None:
        # On the next runner, start with untried queue rows before repeating temporary failures.
        journal_order = {k: n for n, k in enumerate(state["skipped"])}
        pending.sort(key=lambda item: ((item[2] or {}).get("date", ""),
                                       read_tag((item[2] or {}).get("detail", ""))[0] == sig,
                                       journal_order.get(item[1], -1)))
    # Leave time for the workflow's Drive upload before the 30-minute runner timeout.
    deadline = time.monotonic() + 20 * 60 if download_only else float("inf")
    if stop_at is not None:  # Replacement searches share the generate job's remaining budget.
        deadline = stop_at
    try_limit = a.tries if a.tries is not None else (float("inf") if download_only else 40)
    done_n = 0
    while len(got) < a.max and tries < try_limit and time.monotonic() < deadline:
        if done_n == len(pending):
            chart = next(charts, None)
            if chart is None:
                break
            refill_from_chart(*chart)
            continue
        w, k, sk = pending[done_n]
        done_n += 1
        if replacement_attempts is not None:
            replacement_attempts.add(k)
        want_preview = a.previews and k in qkeys
        known_none = bool(sk and not needs_recheck(sk, sig, today, a.force_retry))
        tries += 1
        retried += 1 if sk else 0
        if w.get("url"):  # a direct link the owner wrote into queue.md (4th field): host allowlist + owner declaration, see fetch_url.py
            from . import fetch_url
            try:
                if download_only:
                    name, digest, why = fetch_url.fetch_download_only(w["url"], w["artist"], w["title"], out, cfg,
                                                                    known_sha=known_sha(state), queue_hook=w.get("popular_line", ""))
                else:
                    name, digest, why = fetch_url.fetch(w["url"], w["artist"], w["title"], out, cfg, rights="owner", known_sha=known_sha(state))
            except fetch_url.Duplicate as e:
                name, why = None, f"дубликат: {e}"
            except fetch_url.DownloadUnavailable as e:
                name, why = None, f"ссылка: direct-url:unavailable ({e})"
            except requests.RequestException as e:
                code = getattr(e.response, "status_code", 0)
                state_name = "refused" if code in (400, 404, 410) else "unavailable"
                name, why = None, f"ссылка: direct-url:{state_name} ({safe_err(e)})"
            except (fetch_url.Refused, download.BadAudio, RuntimeError, OSError, ValueError) as e:
                name, why = None, f"ссылка: {str(e)[:150]}"
        else:
            if known_none:
                name, why = None, read_tag(sk["detail"])[3]
            else:
                options = {"download_only": True} if download_only else {}
                name, why = fetch_one(w, cfg, out, searchers=searchers, dead=dead, known_sha=known_sha(state), **options)
        song = f'{w["artist"]} - {w["title"]}'
        official_note = ""
        if not download_only and not name and not known_none and not w.get("url") and cfg.get("official", {}).get("enabled", True):  # stage 2: the artist's own pages (docs/rights.md)
            off = (official_try or official.try_song)(w, cfg, out, known_sha(state), ctx=octx)
            links += [(song, p, n) for p, n in off["links"]]
            if off["file"]:
                name, why = off["file"], off["detail"]
            else:
                official_note = off["reason"] or ("ссылки сохранены: %d" % len(off["links"]))
                why = f"{why}; official: {official_note}"
        if not name and want_preview:
            name, why = fetch_preview(w, out, None if preview_find is None else preview_find(w))
        per_song.append({"song": song, "result": "downloaded" if name else ("link_saved" if any(l[0] == song for l in links) else "skipped"),
                         "file": name or "", "reason": "" if name else why[:400], "links": [p for s, p, n in links if s == song]})
        if name:
            state["done"][k] = {"status": "downloaded", "date": today, "song": song, "file": name, "detail": why}
            state["skipped"].pop(k, None)
            got.append(name)
        else:
            if download_only:
                # Preserve check order within a date when the daily time budget cuts a sweep short.
                state["skipped"].pop(k, None)
            state["skipped"][k] = {"status": "skipped", "date": today, "song": song, "file": "", "detail": tag(sig, sk, today, why)}
            kind = why.split(" (")[0].split(":")[0][:40]
            skip_kinds[kind] = skip_kinds.get(kind, 0) + 1
            for s, st in re.findall(r"([\w-]+):(empty|needs_auth|unavailable|refused|ok)\b", why):
                src_states[f"{s}:{st}"] = src_states.get(f"{s}:{st}", 0) + 1
        sleep(1)  # be polite to the free APIs
    if a.discover and len(got) < a.max:
        seen = set(have) | set(state["done"]) | set(state["skipped"])
        for w, name, why in discover(cfg, out, seen, a.max - len(got), find, sleep):
            k = key(w["artist"], w["title"])
            state["done"][k] = {"status": "downloaded", "date": today, "song": f'{w["artist"]} - {w["title"]}', "file": name, "detail": "discover " + why}
            got.append(name)
    shutil.rmtree(out / "_tmp", ignore_errors=True)
    save_memory(state_f, state)
    octx.save()
    if links:
        official.save_links(state_f.with_name("song-links.md"), links, today)
    report = {"download_only": download_only, "usage_rights": "not_evaluated" if download_only else "policy_checked",
              "configured_sources": cfg.get('sources', {}).get('order', []),
              "skipped_known": skipped_known, "chart_checked": chart_checked, "charts": chart_log,
              "queue_added": queue_added, "queue_update_file": str(queue_update) if queue_update else None,
              "songs": per_song,"candidates": len(cands), "eligible": len(pending) + blocked, "blocked_recent": blocked, "rechecked_skipped": retried, "checked": tries,
              "left_unchecked": len(pending) - done_n, "downloaded": got, "skipped_total": len(state["skipped"]),
              "skip_reasons": skip_kinds, "source_states": src_states, "sources": sources.STATS, "http": http_summary(), "musicbrainz_contact": bool(octx.contact), "signature": sig, "force_retry": bool(a.force_retry)}
    print(json.dumps(report, ensure_ascii=False))
    return got


def arguments(argv):
    ap = argparse.ArgumentParser(prog="pipeline songs")
    ap.add_argument("--out", default="out/fetched")
    ap.add_argument("--download-only", action="store_true", help="queue/chart to public Hitmo/Sefon downloads with technical checks, without evaluating usage rights")
    ap.add_argument("--have-file", help="names already in Drive (audio/ and done/), one per line")
    ap.add_argument("--state", default="out/songs-memory.md", help="memory (md table): used, downloaded and skipped songs")
    ap.add_argument("--discover", action="store_true", help="if the queue/chart gave fewer than --max songs: browse open sources for Russian-titled tracks (indie, not chart)")
    ap.add_argument("--force-retry", action="store_true", help="search ALL skipped songs again now (ignores the 14-day wait and the search signature); history rows are updated, never duplicated")
    ap.add_argument("--previews", action="store_true", help="for queue.md songs with no licensed full file: take the official 30 s preview (Apple/Deezer) for lyric timing only; the video must then be made in mode tiktok")
    ap.add_argument("--check-list", help="audio folder: exit 1 if it holds a song that is not in queue.md (the workflow stops), search nothing")
    ap.add_argument("--prune", help="write to this file the names of earlier downloads that do not fit (not Russian / not your artists), forget them in the memory, search nothing")
    ap.add_argument("--record-used", help="text file of processed audio names (Drive/done): only add them to the memory as `used`, search nothing")
    ap.add_argument("--queue", default=str(ROOT / "accounts" / "main" / "queue.md"))
    ap.add_argument("--max", type=int, default=5, help="max new songs per run")
    ap.add_argument("--tries", type=int, help="max songs searched per run (default: 40 outside download-only)")
    return ap.parse_args(argv)


def main(argv):
    a = arguments(argv)
    if a.check_list:
        q = Path(a.queue)
        bad = off_list(a.check_list, q.read_text(encoding="utf-8") if q.exists() else "")
        print(json.dumps({"not_in_list": bad}, ensure_ascii=False))
        return 1 if bad else 0
    run(a)
    return 0  # finding nothing is a normal outcome, not a failure


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
