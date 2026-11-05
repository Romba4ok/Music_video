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
        artist, title = parse_name(f.stem)
        out.append({"artist": artist, "title": title, "popular_line": "", "audio_file": f.name})
    return out


def pack(out, n, spec, mode, ready):
    """Copy the deliverables of video n into out/ready with readable names: mp4, caption.txt, sync.txt (tiktok)."""
    s = spec["song"]
    name = f'{s["artist"]} - {s["title"]}' if s["artist"] else s["title"]
    base = re.sub(r'[\\/:*?"<>|]+', "",f"{n} {name}").strip()
    ready.mkdir(parents=True, exist_ok=True)
    shutil.copy2(out / f"work-{n}" / "final.mp4", ready / f"{base}.mp4")
    text = (spec["caption"] + "\n" + " ".join(spec["hashtags"])
            + "\n\nВключите в TikTok метку «Создано ИИ» (AI-generated content).")
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
    cap = f'«{entry["title"]}»{who}. О чём эта строка? Сделано с ИИ'[:150]
    spec = {"id": f"{date}-{n}", "mode": "with_audio" if mode == "auto" else "tiktok",
            "song": {"artist": entry["artist"], "title": entry["title"]}, "metaphor": metaphor, "palette": palette,
            "caption": cap, "hashtags": tags, "ai_label": True}
    if mode == "auto":
        spec["audio"] = audio_rel
    return spec


def fetch_audio(entry, cfg, mode):
    """Resolve an audio file: queue file -> local match -> allowed sources. Returns (path|None, statuses)."""
    ad = ROOT / cfg["audio_dir"]
    if entry["audio_file"] and (ad / entry["audio_file"]).exists():
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
    st = {"fetch": fetch_audio, "analyze": analyze_mod.analyze, "build": build.build_one, "author": author_mod.author}
    st.update(stages or {})
    acc = root / "accounts" / "main"
    queue = parse_queue((acc / "queue.md").read_text(encoding="utf-8")) if (acc / "queue.md").exists() else []
    queue += queue_from_audio(root / cfg["audio_dir"], queue)
    used, recent = parse_log((acc / "log.md").read_text(encoding="utf-8")) if (acc / "log.md").exists() else (set(), [])
    out = root / "out" / date
    out.mkdir(parents=True, exist_ok=True)
    report, done = [], 0
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
            analysis = st["analyze"](audio, entry["popular_line"], cfg)
            rec["stages"]["analyze"] = "ok" if analysis.get("fragment") else "no_fragment"
            if not analysis.get("fragment"):
                (out / f"analysis-{n}.json").write_text(json.dumps(analysis, ensure_ascii=False), encoding="utf-8")
                report.append(rec)
                continue
            rel = str(Path(audio).resolve().relative_to(root)).replace("\\", "/") if mode == "auto" else None
            spec = autospec(entry, n, date, recent, cfg, mode, rel, trend_tags)
            analysis, spec, rec["stages"]["author"] = st["author"](entry, analysis, spec, cfg)  # Claude writes cards/hook; falls back to auto
            (out / f"analysis-{n}.json").write_text(json.dumps(analysis, ensure_ascii=False), encoding="utf-8")
            (out / f"spec-{n}.json").write_text(json.dumps(spec, ensure_ascii=False, indent=1), encoding="utf-8")
            sid, lines, video = st["build"](out, n, cfg)
            rec["stages"]["render"] = "ok" if video else "FAIL"
            rec["qa"] = [f"{s} {nm} {d}".strip() for s, nm, d in lines if s != "PASS"]
            if video:
                rec["ready"] = pack(out, n, spec, mode, out / "ready")
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
