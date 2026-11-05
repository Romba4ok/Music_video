"""Render: scenes -> HyperFrames index.html -> silent MP4 -> mux the audio fragment (loudness-normalised, faded out).

HTML is generated here (every timed element is written with class="clip" + data-start/data-duration), so HyperFrames lint passes
and the result is a pure function of the spec. Visual motifs are CSS/SVG only: no third-party images.
"""
import html
import json
import random
import shutil
import subprocess
from pathlib import Path

PALETTES = {
    "cold": ("#0b1e33", "#1f4e79", "#e8f4ff", "#7cc4ff"),
    "warm": ("#3a1208", "#b5532a", "#fff4e6", "#ffb347"),
    "dusk": ("#1a0f2e", "#6b2d5c", "#fdf0ff", "#ff7ac8"),
    "contrast": ("#050505", "#1a1a1a", "#ffffff", "#ffd400"),
}
HEART = "M12 21.35l-1.45-1.32C5.4 15.36 2 12.28 2 8.5 2 5.42 4.42 3 7.5 3c1.74 0 3.41.81 4.5 2.09C13.09 3.81 14.76 3 16.5 3 19.58 3 22 5.42 22 8.5c0 3.78-3.4 6.86-8.55 11.54L12 21.35z"


def motif(metaphor, dur, rng, accent):
    """(html, js) for a slow ambient motif. All tweens span the video: deterministic."""
    h, j = [], []
    if metaphor == "inner":  # rain
        for i in range(26):
            x, w, hh, d0 = rng.randint(0, 1060), rng.choice([2, 3]), rng.randint(60, 140), rng.uniform(0, dur * .5)
            h.append(f'<div id="m{i}" class="m" style="left:{x}px;top:-200px;width:{w}px;height:{hh}px;background:{accent};opacity:.25"></div>')
            j.append(f'tl.to("#m{i}",{{y:2300,duration:{max(1, dur - d0):.2f},ease:"none"}},{d0:.2f});')
    elif metaphor in ("love", "breakup"):
        for i in range(7):
            x, y, s = rng.randint(40, 940), rng.randint(300, 1700), rng.randint(60, 140)
            op = .22 if metaphor == "love" else .14
            h.append(f'<svg id="m{i}" class="m" style="left:{x}px;top:{y}px;width:{s}px;height:{s}px;opacity:{op}" viewBox="0 0 24 24"><path d="{HEART}" fill="{accent}"/></svg>')
            dx = rng.randint(-120, 120) * (1 if i % 2 else -1)
            j.append(f'tl.to("#m{i}",{{y:{-rng.randint(250, 700)},x:{dx},rotation:{rng.randint(-25, 25)},duration:{dur},ease:"none"}},0);')
    elif metaphor == "loneliness":
        h.append(f'<div id="m0" class="m" style="left:120px;top:1450px;width:160px;height:160px;border-radius:50%;background:{accent};opacity:.35;filter:blur(18px)"></div>')
        j.append(f'tl.to("#m0",{{x:60,y:-60,scale:1.15,duration:{dur},ease:"none"}},0);')
    elif metaphor == "nostalgia":
        for i in range(5):
            x, y = rng.randint(60, 760), rng.randint(250, 1500)
            h.append(f'<div id="m{i}" class="m" style="left:{x}px;top:{y}px;width:260px;height:320px;border:6px solid {accent};opacity:.18;transform-origin:center"></div>')
            j.append(f'tl.fromTo("#m{i}",{{rotation:{rng.randint(-14, 14)}}},{{rotation:{rng.randint(-14, 14)},y:{rng.randint(-160, 160)},duration:{dur},ease:"none"}},0);')
    elif metaphor == "money":
        for i in range(9):
            x, hh = 60 + i * 110, rng.randint(160, 700)
            h.append(f'<div id="m{i}" class="m" style="left:{x}px;top:{1700 - hh}px;width:70px;height:{hh}px;background:{accent};opacity:.18;transform-origin:bottom"></div>')
            j.append(f'tl.fromTo("#m{i}",{{scaleY:.3}},{{scaleY:1,duration:{dur * .8:.2f},ease:"power1.out"}},{i * .15:.2f});')
    elif metaphor == "time":
        h.append(f'<div id="m0" class="m" style="left:240px;top:560px;width:600px;height:600px;border:8px solid {accent};border-radius:50%;opacity:.2"></div>')
        h.append(f'<div id="m1" class="m" style="left:536px;top:580px;width:8px;height:280px;background:{accent};opacity:.3;transform-origin:50% 280px"></div>')
        j.append(f'tl.to("#m1",{{rotation:{int(dur * 12)},duration:{dur},ease:"none"}},0);')
    return "\n".join(h), "\n".join(j)


def build_html(scenes, beats, palette, metaphor, duration, cfg, seed=1):
    w, hgt, fps = cfg["width"], cfg["height"], cfg["fps"]
    bg1, bg2, fg, accent = PALETTES[palette]
    rng = random.Random(seed)
    m_html, m_js = motif(metaphor, duration, rng, accent)
    clips, js = [], []
    for i, s in enumerate(scenes):
        dur = round(s["end"] - s["start"], 3)
        if dur <= 0:
            continue
        cls = "card outro" if s["role"] == "outro" else "card"
        if s.get("words"):
            inner = "".join(f'<span class="w" id="c{i}w{k}">{html.escape(x["w"])}</span> ' for k, x in enumerate(s["words"]))
        else:
            inner = f'<span class="w" id="c{i}w0">{html.escape(s["text"])}</span>'
        clips.append(f'<div id="clip{i}" class="clip" data-start="{s["start"]}" data-duration="{dur}" data-track-index="2">'
                     f'<div id="card{i}" class="{cls}">{inner}</div></div>')
        js.append(f'tl.fromTo("#card{i}",{{opacity:0,y:50}},{{opacity:1,y:0,duration:.25,ease:"power3.out"}},{s["start"]});')
        js.append(f'tl.to("#card{i}",{{opacity:0,y:-30,duration:.2,ease:"power2.in"}},{max(s["start"] + .26, round(s["end"] - .22, 3))});')
        for k, x in enumerate(s.get("words") or []):
            js.append(f'tl.fromTo("#c{i}w{k}",{{opacity:.3,scale:.94}},{{opacity:1,scale:1,duration:.12,ease:"power2.out"}},{x["s"]});')
        if not s.get("words"):
            js.append(f'tl.fromTo("#c{i}w0",{{opacity:.3}},{{opacity:1,duration:.3}},{s["start"] + .1});')
    for b in beats[:400]:
        js.append(f'tl.to("#glow",{{scale:1.07,duration:.08,ease:"power2.out"}},{b}).to("#glow",{{scale:1,duration:.25,ease:"power2.in"}},{round(b + .08, 3)});')
    return f"""<!doctype html>
<html lang="ru"><head><meta charset="utf-8"><meta name="viewport" content="width={w}, height={hgt}">
<script src="https://cdn.jsdelivr.net/npm/gsap@3.12.5/dist/gsap.min.js"></script>
<style>
html,body{{margin:0;background:{bg1};}}
#root{{position:relative;width:{w}px;height:{hgt}px;overflow:hidden;background:linear-gradient(180deg,{bg1},{bg2});font-family:'Montserrat',sans-serif;}}
#glow{{position:absolute;inset:0;background:radial-gradient(circle at 50% 45%,{accent}33,transparent 60%);}}
.m{{position:absolute;}}
.clip{{position:absolute;left:90px;top:168px;width:{w - 180}px;height:1160px;}}
.card{{position:absolute;inset:0;display:flex;flex-wrap:wrap;align-content:center;justify-content:center;text-align:center;gap:0 22px;
 font-weight:800;font-size:78px;line-height:1.18;color:{fg};text-shadow:0 6px 30px #0008;}}
.card .w{{display:inline-block;}}
.card.outro{{font-size:54px;color:{accent};font-weight:700;}}
</style></head>
<body>
<div id="root" data-composition-id="main" data-start="0" data-duration="{duration}" data-width="{w}" data-height="{hgt}" data-fps="{fps}">
<div id="glow"></div>
{m_html}
{chr(10).join(clips)}
</div>
<script>
window.__timelines = window.__timelines || {{}};
const tl = gsap.timeline({{paused:true}});
{m_js}
{chr(10).join(js)}
window.__timelines["main"] = tl;
</script>
</body></html>
"""


def _run(cmd, stdout_only=False, **kw):
    r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", **kw)
    return r.returncode, (r.stdout or "") if stdout_only else (r.stdout or "") + (r.stderr or "")


def npx():
    return shutil.which("npx") or shutil.which("npx.cmd") or "npx"


def check(workdir):
    """HyperFrames lint. Returns (ok, errors)."""
    rc, out = _run([npx(), "hyperframes", "check", "--json"], stdout_only=True, cwd=workdir)
    try:
        data = json.loads(out[out.index("{"):])
    except Exception:
        return False, ["check output unreadable: " + out[-300:]]
    errs = []
    for sec in ("lint", "runtime", "layout", "motion", "contrast", "craft", "audio"):
        for f in (data.get(sec) or {}).get("findings", []):
            if f.get("severity") == "error":
                errs.append(f'{sec}:{f.get("code")}: {f.get("message")} Fix: {f.get("fixHint")}'[:300])
    if not errs and not data.get("ok"):
        bad = [k for k, v in data.items() if isinstance(v, dict) and v.get("ok") is False]
        errs = ["check ok=false in: " + ",".join(bad) + " " + json.dumps({k: data[k] for k in bad}, ensure_ascii=False)[:500]]
    return not errs and bool(data.get("ok")), errs


def make_audio(src, start, length, out, cfg, fade=1.5):
    af = f"apad=whole_dur={length},afade=t=out:st={max(0, length - fade):.2f}:d={fade},loudnorm=I={cfg['target_lufs']}:TP={cfg['max_true_peak'] - 1}:LRA=11"
    rc, log = _run(["ffmpeg", "-y", "-loglevel", "error", "-ss", f"{start}", "-t", f"{length}", "-i", str(src), "-vn", "-af", af,
                    "-ar", "48000", "-c:a", "aac", "-b:a", "192k", str(out)])
    if rc:
        raise RuntimeError("ffmpeg audio failed: " + log[-300:])


def render(spec, plan, workdir, cfg, audio_src=None):
    """plan = script_gen.build_scenes output (or commentary equivalent). Returns path to final mp4."""
    wd = Path(workdir).resolve()  # absolute: the CLI runs with cwd=wd, relative -o paths would nest
    wd.mkdir(parents=True, exist_ok=True)
    if cfg.get("style") == "widgets":
        from . import render_widgets
        page = render_widgets.build_html(plan, spec, cfg)
    else:
        page = build_html(plan["scenes"], plan.get("beats", []), spec["palette"], spec["metaphor"], plan["duration"], cfg)
    (wd / "index.html").write_text(page, encoding="utf-8")
    ok, errs = check(wd)
    if not ok:
        raise RuntimeError("hyperframes check failed: " + "; ".join(errs)[:600])
    silent = wd / "silent.mp4"
    rc, log = _run([npx(), "hyperframes", "render", "-o", str(silent), "--fps", str(cfg["fps"]), "--quality", "looks"], cwd=wd)
    if rc or not silent.exists():
        raise RuntimeError("hyperframes render failed: " + log[-500:])
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
