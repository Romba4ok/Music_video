"""Render: spec + scenario -> props.json -> Remotion composition `Widgets` (remotion/) -> silent MP4 -> mux the audio fragment
(loudness-normalised, faded out). The picture is a pure function of the props (pipeline/widgets_plan.py); the audio never goes through Remotion.
"""
import json
import shutil
import subprocess
from pathlib import Path

from . import widgets_plan
from .common import ROOT

REMOTION = ROOT / "remotion"


def _run(cmd, stdout_only=False, **kw):
    r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", **kw)
    return r.returncode, (r.stdout or "") if stdout_only else (r.stdout or "") + (r.stderr or "")


def npx():
    return shutil.which("npx") or shutil.which("npx.cmd") or "npx"


def make_audio(src, start, length, out, cfg, fade=1.5):
    af = f"apad=whole_dur={length},afade=t=out:st={max(0, length - fade):.2f}:d={fade},loudnorm=I={cfg['target_lufs']}:TP={cfg['max_true_peak'] - 1}:LRA=11,alimiter=limit=0.7:level=disabled"  # the AAC encode adds up to ~2 dB over loudnorm's ceiling on loud masters (+0.2 dBFS seen on a real track)
    rc, log = _run(["ffmpeg", "-y", "-loglevel", "error", "-ss", f"{start}", "-t", f"{length}", "-i", str(src), "-vn", "-af", af,
                    "-ar", "48000", "-c:a", "aac", "-b:a", "192k", str(out)])
    if rc:
        raise RuntimeError("ffmpeg audio failed: " + log[-300:])


def check_props(props):
    """Cheap sanity check before the (slow) render: the composition needs at least one card and a finite duration."""
    errs = []
    if not any(x["role"] == "lyric" for x in props["scenes"]):
        errs.append("no cards")
    if not props["duration"] or props["duration"] <= 0:
        errs.append("bad duration")
    if props["ostart"] >= props["duration"]:
        errs.append("end card starts after the video ends")
    return errs


def render(spec, plan, workdir, cfg, audio_src=None):
    """plan = script_gen.build_scenes output (or commentary equivalent). Returns path to final mp4."""
    wd = Path(workdir).resolve()  # absolute: Remotion runs with cwd=remotion/
    wd.mkdir(parents=True, exist_ok=True)
    props = widgets_plan.resolve(plan, spec, cfg)
    errs = check_props(props)
    if errs:
        raise RuntimeError("props check failed: " + "; ".join(errs))
    pj = wd / "props.json"
    pj.write_text(json.dumps(props, ensure_ascii=False), encoding="utf-8")
    silent = wd / "silent.mp4"
    rc, log = _run([npx(), "remotion", "render", "src/index.ts", "Widgets", str(silent), f"--props={pj}", "--codec=h264", "--crf=18"], cwd=REMOTION)
    if rc or not silent.exists():
        raise RuntimeError("remotion render failed: " + log[-500:])
    final = wd / "final.mp4"
    if audio_src:
        aud = wd / "audio.m4a"
        make_audio(audio_src, plan["audio_start"], plan["audio_len"], aud, cfg)
        rc, log = _run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(silent), "-i", str(aud), "-c:v", "copy", "-c:a", "copy",
                        "-shortest", str(final)])
        if rc:
            raise RuntimeError("ffmpeg mux failed: " + log[-300:])
    else:
        shutil.copy2(silent, final)
    return final
