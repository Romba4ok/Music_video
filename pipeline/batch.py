"""Autonomous batch (no LLM needed): queue.md -> fetch audio -> analyze -> auto spec -> render+QA, per song, fault tolerant.

python -m pipeline batch --mode auto|tiktok --count 3 [--date YYYY-MM-DD] [--lang ru]
A failing song/source is recorded in report.json and the next queue entry is tried; the batch never aborts on one failure.
Claude is optional here: it can replace autospec() for better captions/metaphors (prompts/generate.md)."""
import json
import os
import re
import shutil
import time
import zlib
from pathlib import Path

from . import analyze as analyze_mod
from . import author as author_mod
from . import build, download, sources
from .common import ROOT, load_config, parse_name
from .qa import METAPHORS, PALETTES

METAPHOR_ORDER = ["inner", "loneliness", "breakup", "love", "nostalgia", "time", "money"]
PALETTE_ORDER = ["dusk", "cold", "warm", "contrast"]


def parse_queue(text):
    """`artist | title | popular_line | audio_file | ...` lines; HTML comments and blanks ignored."""
    text = re.sub(r"<!--.*?-->", "", text, flags=re.S)
    out = []
    for ln in text.splitlines():
        if ln.startswith("#") or "|" not in ln:
            continue
        p = [x.strip() for x in ln.split("|")] + [""] * 5
        if p[0] and p[1]:
            out.append({"artist": p[0], "title": p[1], "popular_line": p[2], "audio_file": p[3]})
    return out


def parse_log(text):
    """-> (used {(artist,title)}, recent [(metaphor,palette)]) from log.md table rows."""
    used, recent = set(), []
    for ln in text.splitlines():
        c = [x.strip() for x in ln.strip().strip("|").split("|")]
        if len(c) >= 7 and re.match(r"\d{4}-\d{2}-\d{2}", c[0]):
            used.add((c[2].lower(), c[3].lower()))
            recent.append((c[4], c[5]))
    return used, recent


AUDIO_EXT = (".mp3", ".wav", ".m4a", ".ogg", ".flac", ".mp4", ".mov", ".mkv", ".webm", ".m4v")


def queue_from_audio(ad, queue):
    """Files dropped into audio_dir (`Artist - Title.ext`) that no queue line covers become queue entries (Drive flow)."""
    out = []
    for f in sorted(Path(ad).glob("*")) if Path(ad).exists() else []:
        if f.suffix.lower() not in AUDIO_EXT:
            continue
        stem = f.stem.lower()
        if any(e["audio_file"] == f.name or all(w in stem for w in re.split(r"\W+", f"{e['artist']} {e['title']}".lower()) if w)
               for e in queue):
            continue
        m = re.search(r"\s*\[([^\]]+)\]\s*$", f.stem)  # 'Artist - Title [first words of the line to start from]'
        artist, title = parse_name(f.stem[:m.start()] if m else f.stem)
        out.append({"artist": artist, "title": title, "popular_line": "=" + m.group(1).strip() if m else "", "audio_file": f.name})
    return out


def popular_for(entry, root=ROOT):
    """Popular lines of a song from data/popular_lines.json (TikTok analysis, see docs/video-spec.md) as 'a || b'; '' when unknown."""
    try:
        rec = json.loads((root / "data" / "popular_lines.json").read_text(encoding="utf-8")).get(f'{entry["artist"]}|{entry["title"]}'.lower())
    except (OSError, ValueError):
        return ""
    return " || ".join(rec.get("lines", [])) if isinstance(rec, dict) else ""


def pack(out, n, spec, mode, ready):
    """Copy the deliverables of video n into out/ready with readable names: mp4, caption.txt, sync.txt (tiktok)."""
    s = spec["song"]
    name = f'{s["artist"]} - {s["title"]}' if s["artist"] else s["title"]
    base = re.sub(r'[\\/:*?"<>|]+', "",f"{n} {name}").strip()
    ready.mkdir(parents=True, exist_ok=True)
    shutil.copy2(out / f"work-{n}" / "final.mp4", ready / f"{base}.mp4")
    text = (spec["caption"] + "\n" + " ".join(spec["hashtags"]))
    (ready / f"{base} caption.txt").write_text(text, encoding="utf-8")
    if (out / f"sync-{n}.txt").exists():
        shutil.copy2(out / f"sync-{n}.txt", ready / f"{base} sync.txt")
    return base  # report.json keeps it so the Buffer step finds the mp4 and caption.txt


def _pick(order, banned, key):
    pool = [x for x in order if x not in banned] or order
    return pool[zlib.crc32(key.encode("utf-8")) % len(pool)]


def autospec(entry, n, date, recent, cfg, mode, audio_rel, trend_tags=()):
    key = f'{entry["artist"]}{entry["title"]}'
    metaphor = _pick(METAPHOR_ORDER, [m for m, _ in recent[-3:]], key)
    palette = _pick(PALETTE_ORDER, [p for _, p in recent[-3:]], key + "p")
    tag = "#" + re.sub(r"\W+", "", entry["artist"].lower(), flags=re.U)
    tags = list(dict.fromkeys(list(cfg.get("default_hashtags", [])) + list(trend_tags)[:2] + ([tag] if len(tag) > 1 else [])))[:5]
    who = f' — {entry["artist"]}' if entry["artist"] else ""
    cap = f'«{entry["title"]}»{who}. О чём эта строка?'[:150]
    spec = {"id": f"{date}-{n}", "mode": "with_audio" if mode == "auto" else "tiktok",
            "song": {"artist": entry["artist"], "title": entry["title"]}, "metaphor": metaphor, "palette": palette,
            "caption": cap, "hashtags": tags, "ai_label": True}
    if mode == "auto":
        spec["audio"] = audio_rel
    return spec


CARDS_LOG = "cards.jsonl"


def recall_cards(acc, n=3):
    """The card record of the last n built videos (accounts/<acc>/cards.jsonl, one JSON per line), oldest first; never raises."""
    f = Path(acc) / CARDS_LOG
    out = []
    for ln in (f.read_text(encoding="utf-8").splitlines() if f.exists() else [])[-n:]:
        try:
            out.append(json.loads(ln))
        except ValueError:
            pass
    return out


def remember_cards(acc, date, song, spec):
    """Append what this video was made of (kinds, hook, theme): the next runs avoid the same recipe, `pipeline insights` joins it with views."""
    ws = spec.get("widgets") or []
    rec = {"date": date, "song": song, "hook": spec.get("hook", ""), "theme": spec.get("theme", "light"), "n_cards": len(ws),
           "kinds": [w.get("kind") for w in ws], "draw_share": round(sum(w.get("kind") == "draw" for w in ws) / max(1, len(ws)), 2),
           "details": sum(bool(w.get("big") or w.get("chips")) for w in ws),
           "anim_share": round(sum(bool(w.get("tw")) for w in ws) / max(1, len(ws)), 2),  # share of cards whose objects move by tweens (not frame slideshows)
           "hook_question": str(spec.get("hook", "")).strip().endswith("?"), "renderer": "remotion"}
    Path(acc).mkdir(parents=True, exist_ok=True)
    with open(Path(acc) / CARDS_LOG, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def fetch_audio(entry, cfg, mode):
    """Resolve an audio file: queue file -> local match -> allowed sources. Returns (path|None, statuses)."""
    ad = ROOT / cfg["audio_dir"]
    if entry["audio_file"] and (ad / entry["audio_file"]).exists():
        side = ad / (entry["audio_file"] + ".license.json")
        if mode == "auto" and side.exists() and json.loads(side.read_text(encoding="utf-8")).get("analysis_only"):
            # an official 30 s preview is for lyric timing only: it must never become the sound of a published video
            return None, [{"source": "local", "state": "refused", "detail": "official preview: analysis only, run with mode tiktok (sound is added in TikTok)"}]
        return download.ensure_audio(ad / entry["audio_file"], _declared(ad, entry["audio_file"])), [
            {"source": "local", "state": "ok", "detail": entry["audio_file"]}]
    cands, sts = sources.search(f'{entry["artist"]} {entry["title"]}', cfg, n=5)
    path, dsts = download.download_first(cands, ad, cfg)
    return path, sts + dsts


def _declared(ad, name):
    f = ad / "sources.json"
    # shortcut: Drive drop-in counts as the owner's declaration only when the workflow sets this env var explicitly
    return os.environ.get("VYBEX_OWNER_DECLARES_RIGHTS") == "1" or (f.exists() and name in json.loads(f.read_text(encoding="utf-8")))


def run_batch(mode, count, date, cfg=None, lang=None, root=ROOT, stages=None, trend_tags=()):
    cfg = dict(cfg or load_config())
    if lang:
        cfg["language"] = lang
    st = {"fetch": fetch_audio, "check_audio": download.check_audio, "analyze": analyze_mod.analyze, "build": build.build_one, "author": author_mod.author}
    st.update(stages or {})
    acc = root / "accounts" / "main"
    queue = parse_queue((acc / "queue.md").read_text(encoding="utf-8")) if (acc / "queue.md").exists() else []
    queue += queue_from_audio(root / cfg["audio_dir"], queue)
    used, recent = parse_log((acc / "log.md").read_text(encoding="utf-8")) if (acc / "log.md").exists() else (set(), [])
    out = root / "out" / date
    out.mkdir(parents=True, exist_ok=True)
    past = recall_cards(acc)  # earlier runs count too: the same recipe on the next day looks the same
    report, done = [], 0
    themes = [r.get("theme", "light") for r in past]
    for entry in queue:
        if done >= count:
            break
        if (entry["artist"].lower(), entry["title"].lower()) in used:
            continue
        n = done + 1
        rec = {"song": f'{entry["artist"]} — {entry["title"]}', "stages": {}}
        try:
            audio, sts = st["fetch"](entry, cfg, mode)
            rec["sources"] = sts
            if not audio:
                rec["stages"]["fetch"] = "no_audio"
                rec["note"] = "no allowed source had this track; put a file you have rights to into audio_dir"
                report.append(rec)
                continue
            rec["stages"]["fetch"] = "ok"
            rec["audio_name"] = Path(audio).name
            try:  # a broken file must not reach whisper (minutes of CPU) or stop the other songs
                audio, notes = st["check_audio"](audio, cfg["min_len"])
            except download.BadAudio as e:
                rec["stages"]["fetch"] = "bad_audio"
                rec["note"] = f"audio file rejected: {e}"
                report.append(rec)
                continue
            if notes:
                rec["audio_notes"] = notes
            analysis = st["analyze"](audio, entry["popular_line"] or popular_for(entry, root), cfg)  # a line typed by the owner always wins
            fr = analysis.get("fragment")
            rec["stages"]["analyze"] = "ok" if fr else "no_fragment"
            if fr and fr.get("low_ratio", 0) > cfg["whisper"].get("max_low_ratio", 0.15):  # no window with reliably recognised words: do not render guesses
                rec["stages"]["analyze"] = "low_confidence"
                rec["note"] = f'{fr["low_ratio"]:.0%} of the words in the best window are low-confidence (limit {cfg["whisper"].get("max_low_ratio", 0.15):.0%}); not rendered'
                (out / f"analysis-{n}.json").write_text(json.dumps(analysis, ensure_ascii=False), encoding="utf-8")
                report.append(rec)
                continue
            if fr and "end_kind" in fr and fr["end_kind"] is None and not fr.get("pinned"):  # the end is not a finished thought: say so, never silently
                rec["note"] = "the fragment does not end on a finished thought (no closing line within reach)"
            if not analysis.get("fragment"):
                (out / f"analysis-{n}.json").write_text(json.dumps(analysis, ensure_ascii=False), encoding="utf-8")
                report.append(rec)
                continue
            rel = str(Path(audio).resolve().relative_to(root)).replace("\\", "/") if mode == "auto" else None
            spec = autospec(entry, n, date, recent, cfg, mode, rel, trend_tags)
            entry["recent_themes"] = themes
            analysis, spec, rec["stages"]["author"] = st["author"](entry, analysis, spec, cfg)
            if rec["stages"]["author"].startswith("fallback"):  # keyword cards look alike: never let that pass unnoticed
                rec["note"] = "Claude author failed, this video uses keyword cards: " + rec["stages"]["author"]
            themes.append(spec.get("theme", "light"))
            (out / f"analysis-{n}.json").write_text(json.dumps(analysis, ensure_ascii=False), encoding="utf-8")
            (out / f"spec-{n}.json").write_text(json.dumps(spec, ensure_ascii=False, indent=1), encoding="utf-8")
            if spec.get("scenario"):  # the card script the video is built from, readable without opening the spec
                (out / f"scenario-{n}.txt").write_text(author_mod.render_scenario(spec["scenario"]), encoding="utf-8")
            sid, lines, video = st["build"](out, n, cfg)
            rec["stages"]["render"] = "ok" if video else "FAIL"
            rec["qa"] = [f"{s} {nm} {d}".strip() for s, nm, d in lines if s != "PASS"]
            if video:
                rec["ready"] = pack(out, n, spec, mode, out / "ready")
                remember_cards(acc, date, rec["song"], spec)
                done += 1
                recent.append((spec["metaphor"], spec["palette"]))
        except Exception as e:  # one song must never stop the batch
            rec["stages"]["error"] = f"{type(e).__name__}: {str(e)[:200]}"
        report.append(rec)
    summary = {"mode": mode, "date": date, "requested": count, "succeeded": done, "songs": report,
               "queue_left": max(0, len(queue) - len(report))}
    (out / "report.json").write_text(json.dumps(summary, ensure_ascii=False, indent=1), encoding="utf-8")
    return summary


def main(argv):
    import argparse
    ap = argparse.ArgumentParser(prog="pipeline batch")
    ap.add_argument("--mode", choices=["auto", "tiktok"], default="auto")
    ap.add_argument("--count", type=int, default=3)
    ap.add_argument("--date", default=time.strftime("%Y-%m-%d", time.gmtime()))
    ap.add_argument("--lang")
    a = ap.parse_args(argv)
    s = run_batch(a.mode, a.count, a.date, lang=a.lang)
    print(json.dumps({k: v for k, v in s.items() if k != "songs"}, ensure_ascii=False))
    for r in s["songs"]:
        print(r["song"], r["stages"], *(r.get("qa") or []), sep=" | ")
    return 0 if s["succeeded"] else 1
