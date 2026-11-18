"""Render: spec + scenario -> props.json -> Remotion composition `Widgets` (remotion/) -> silent MP4 -> mux the audio fragment
(loudness-normalised, faded out). The picture is a pure function of the props (pipeline/widgets_plan.py); the audio never goes through Remotion.
"""
import json
import re
import shutil
import subprocess
from pathlib import Path

from . import widgets_plan
from .common import ROOT, plain

REMOTION = ROOT / "remotion"


def _run(cmd, stdout_only=False, **kw):
    r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", **kw)
    return r.returncode, (r.stdout or "") if stdout_only else (r.stdout or "") + (r.stderr or "")


def npx():
    return shutil.which("npx") or shutil.which("npx.cmd") or "npx"


def _ebu(args):
    """ffmpeg ... ebur128=peak=true -> (integrated LUFS, true peak dBFS), None when unreadable (same reading as qa.loudness)."""
    rc, log = _run(["ffmpeg", "-hide_banner", "-nostats", *args, "-f", "null", "-"])
    tail = log[log.rfind("Summary:"):]
    i, p = re.search(r"I:\s+(-?[\d.]+) LUFS", tail), re.search(r"Peak:\s+(-?[\d.]+) dBFS", tail)
    return (float(i.group(1)), float(p.group(1))) if i and p and not rc else (None, None)


def make_audio(src, start, length, out, cfg, fade=1.5, tries=4):
    """Fragment -> AAC at the target loudness. Closed loop instead of one-pass loudnorm: gain = target - measured, a limiter holds the peaks, then the
    ENCODED file is measured again (what QA measures): missing loudness is added as gain, a peak over the QA ceiling lowers the limiter. One-pass
    loudnorm left dynamic tracks 3-4 LU under the target (-18 LUFS vs -14) because its true-peak ceiling stopped the gain."""
    pre = f"apad=whole_dur={length},afade=t=out:st={max(0, length - fade):.2f}:d={fade}"
    target, ceiling = cfg["target_lufs"], cfg["max_true_peak"] + 0.3  # the QA limits: |LUFS - target| <= 2.5, true peak <= ceiling
    src_args = ["-ss", f"{start}", "-t", f"{length}", "-i", str(src), "-vn"]

    def encode(gain, limit):
        af = f"{pre},volume={gain:.2f}dB,alimiter=limit={limit:.3f}:level=disabled"
        rc, log = _run(["ffmpeg", "-y", "-loglevel", "error", *src_args, "-af", af, "-ar", "48000", "-c:a", "aac", "-b:a", "192k", str(out)])
        if rc:
            raise RuntimeError("ffmpeg audio failed: " + log[-300:])
        return _ebu(["-i", str(out), "-af", "ebur128=peak=true"])

    lufs, _ = _ebu([*src_args, "-af", f"{pre},ebur128=peak=true"])
    gain, limit, best = (target - lufs) if lufs is not None else 0.0, 0.85, None  # 0.85 = -1.4 dBFS; the AAC encode may add a dB or two, the loop below checks it
    for _ in range(tries):
        got, peak = encode(gain, limit)
        if got is None or peak is None:
            return  # cannot measure: keep this encode, QA will judge it
        ok = peak <= ceiling
        if best is None or (ok, -abs(got - target)) > best[0]:
            best = ((ok, -abs(got - target)), gain, limit)
        if ok and abs(got - target) <= 1.0:
            return
        gain += target - got
        if not ok:
            limit *= 10 ** ((ceiling - peak - 0.3) / 20)
    if (best[1], best[2]) != (gain, limit):  # the loop ended on a worse try than the best one: encode that one again
        encode(best[1], best[2])


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


def review_files(video, dur, wd):
    """cover.png (a frame about a second in: hook on screen, the first card already drawn) and sheet.png (8 evenly spaced frames) for a quick look."""
    _run(["ffmpeg", "-y", "-loglevel", "error", "-ss", "1.0", "-i", str(video), "-frames:v", "1", str(wd / "cover.png")])
    pick = "+".join(f"eq(n,{int(dur * 30 * k / 8)})" for k in range(8))
    _run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(video), "-vf", f"select='{pick}',crop=1080:1080:0:420,scale=270:-1,tile=8x1", "-frames:v", "1", "-an", str(wd / "sheet.png")])


def render(spec, plan, workdir, cfg, audio_src=None):
    """plan = script_gen.build_scenes output (or commentary equivalent). Returns path to final mp4."""
    wd = Path(workdir).resolve()  # absolute: Remotion runs with cwd=remotion/
    wd.mkdir(parents=True, exist_ok=True)
    props = widgets_plan.resolve(plan, spec, cfg)
    errs = check_props(props)
    if errs:
        raise RuntimeError("props check failed: " + "; ".join(errs))
    pj = wd / "props.json"
    pj.write_text(json.dumps(props, ensure_ascii=False, default=plain), encoding="utf-8")
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
    review_files(final, plan["duration"], wd)
    return final
