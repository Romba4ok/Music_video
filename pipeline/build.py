"""Stage 3 (render): python -m pipeline.build out/<date> [--only N]
spec-N.json (+ analysis-N.json) -> lyric cards -> HyperFrames render -> QA -> meta-N.json.

Modes (spec["mode"]):
  with_audio  AUTO: audio fragment from a licensed source is mixed into the mp4.
  tiktok      TIKTOK: silent mp4 timed to the song + sync-N.json/.txt (where to start the official sound in the app).
              The audio file is only analysed locally and is never embedded or published.
  commentary  silent mp4 with hand-written scenes (no song analysis).
One failing video never stops the others; the exit code is 1 if any failed."""
import argparse
import json
import sys
from pathlib import Path

from . import qa, render, script_gen
from .common import ROOT, load_config


def fmt_ts(s):
    return f"{int(s // 60)}:{s % 60:05.2f}"


def sync_info(spec, plan):
    song = spec["song"]
    t = plan["audio_start"]
    steps = [
        "Загрузите ролик в TikTok (из inbox или вручную).",
        f"Нажмите «Добавить звук» → найдите официальный трек «{song['artist']} — {song['title']}».",
        f"В обрезке звука поставьте начало на {fmt_ts(t)} (фрагмент песни {plan['duration'] - 2.5:.0f} с, ролик {plan['duration']} с).",
        "Громкость оригинального звука ролика не нужна: в файле звука нет.",
        "Включите метку «Создано ИИ» перед публикацией.",
    ]
    return {"song": song, "sound_start_sec": t, "sound_start": fmt_ts(t), "video_duration": plan["duration"],
            "beats_first": plan["beats"][:8], "steps": steps}


def _plan(spec, d, n, cfg):
    mode = spec.get("mode")
    if mode in ("with_audio", "tiktok"):
        ap = d / f"analysis-{n}.json"
        if not ap.exists():
            raise FileNotFoundError(f"{ap.name} missing: run the analyze stage first")
        analysis = json.loads(ap.read_text(encoding="utf-8"))
        if not analysis.get("fragment"):
            raise ValueError("analysis has no fragment (no lyrics recognised)")
        return script_gen.build_scenes(analysis, spec["song"], cfg,
                                       intro=cfg.get("intro_sec", 0.0) if cfg.get("style") == "widgets" else 0.0,
                                       widgets=spec.get("widgets") if cfg.get("style") == "widgets" else None)
    scenes = [{"role": "outro" if s["role"] == "outro" else "meaning", "text": s["text"], "start": s["start"],
               "end": round(s["start"] + s["dur"], 3), "words": []} for s in spec.get("scenes", [])]
    return {"duration": round(max((s["end"] for s in scenes), default=0), 2), "scenes": scenes, "beats": []}


def build_one(d, n, cfg):
    d = Path(d)
    try:
        spec = json.loads((d / f"spec-{n}.json").read_text(encoding="utf-8"))
    except Exception as e:
        return f"spec-{n}", [("FAIL", "spec_read", type(e).__name__)], None
    sid = spec.get("id", f"spec-{n}")
    errs = qa.validate_spec(spec, cfg)
    if errs:
        return sid, [("FAIL", "spec_valid", "; ".join(errs))], None
    try:
        plan = _plan(spec, d, n, cfg)
        audio_src = ROOT / spec["audio"] if spec["mode"] == "with_audio" else None
        if audio_src is not None and not audio_src.exists():
            raise FileNotFoundError(f"audio file missing: {spec['audio']}")
        video = render.render(spec, plan, d / f"work-{n}", cfg, audio_src)
    except Exception as e:
        return sid, [("FAIL", "render", f"{type(e).__name__}: {str(e)[:450]}")], None
    lines = qa.run_checks(spec, video, plan, cfg)
    if any(s == "FAIL" for s, _, _ in lines):
        return sid, lines, None
    attrib = []
    if audio_src is not None and Path(str(audio_src) + ".license.json").exists():
        attrib.append(json.loads(Path(str(audio_src) + ".license.json").read_text(encoding="utf-8")).get("attribution", ""))
    meta = {"id": sid, "mode": spec["mode"], "video": str(video), "caption": spec["caption"], "hashtags": spec["hashtags"],
            "song": spec["song"], "metaphor": spec["metaphor"], "palette": spec["palette"],
            "attribution": [a for a in attrib if a], "ai_label": True}
    if spec["mode"] == "tiktok":
        sync = sync_info(spec, plan)
        meta["sync"] = sync
        (d / f"sync-{n}.json").write_text(json.dumps(sync, ensure_ascii=False, indent=1), encoding="utf-8")
        (d / f"sync-{n}.txt").write_text("\n".join(f"{i}. {s}" for i, s in enumerate(sync["steps"], 1)), encoding="utf-8")
    (d / f"meta-{n}.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")
    return sid, lines, video


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("dir")
    ap.add_argument("--only", type=int)
    a = ap.parse_args(argv)
    d, cfg, bad = Path(a.dir), load_config(), False
    nums = [a.only] if a.only else sorted(int(p.stem.split("-")[1]) for p in d.glob("spec-*.json"))
    for n in nums:
        sid, lines, video = build_one(d, n, cfg)
        for st, name, det in lines:
            print(f"{st} {sid} {name} {det}".rstrip())
        print(f"{'PASS' if video else 'FAIL'} {sid} overall {video or ''}".rstrip())
        bad |= video is None
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
