"""Template "widgets": phone-UI edit (pastel background, Dynamic-Island player, lyric line as a notification widget with an
own SVG illustration, carousel dots, player bar). Inspired by the format of popular "widget edit" videos; all art is our own SVG/CSS.

Pure function: build_html(plan, spec, cfg) -> HyperFrames index.html (every timed element is a .clip, GSAP timeline paused).
"""
import html
import random

PAL = {  # spec palette -> (bg1, bg2, bg3, accent, title gradient a, b)
    "dusk": ("#ffe6f1", "#e9e2ff", "#dbeafe", "#6a5cff", "#ff4f8b", "#a47bff"),
    "cold": ("#e0f0ff", "#e3e8ff", "#f1e4ff", "#3b6cff", "#2f8bff", "#8a6bff"),
    "warm": ("#fff0e0", "#ffe3ec", "#f3e6ff", "#ff5a2d", "#ff7a3d", "#ff3d8b"),
    "contrast": ("#e0fff3", "#e0f0ff", "#efe6ff", "#14956f", "#1fb98a", "#3b8bff"),
}
HEART = "M12 21.35l-1.45-1.32C5.4 15.36 2 12.28 2 8.5 2 5.42 4.42 3 7.5 3c1.74 0 3.41.81 4.5 2.09C13.09 3.81 14.76 3 16.5 3 19.58 3 22 5.42 22 8.5c0 3.78-3.4 6.86-8.55 11.54L12 21.35z"

# (key, app title, icon colour, stems that pick this widget for a line)
ARTS = [
    ("sunset", "Закат", "#ff9a6b", ("закат", "солнц", "рассвет", "свет", "лучи")),
    ("map", "Локатор", "#3b8bff", ("дорог", "путь", "иду", "идти", "город", "домой", "улиц", "куда", "где")),
    ("pulse", "Пульс", "#ff4f6d", ("сердц", "любо", "люби", "боль", "чувств", "душ", "дыш")),
    ("clock", "Часы", "#8a6bff", ("врем", "час", "год", "день", "секунд", "вчера", "завтра", "когда", "жизн")),
    ("rain", "Погода", "#4a6a9a", ("дожд", "слез", "плак", "гроз", "холод", "ветер")),
    ("moon", "Ночь", "#3a3f8f", ("ноч", "звезд", "луна", "сон", "спа", "тьм", "темн", "один")),
]


def _art(key, uid):
    g = f"g{uid}"
    if key == "sunset":
        return (f'<defs><linearGradient id="{g}" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#ffd6a5"/>'
                f'<stop offset=".55" stop-color="#ff9a8b"/><stop offset="1" stop-color="#c3a6ff"/></linearGradient></defs>'
                f'<rect width="800" height="420" fill="url(#{g})"/><circle id="sun{uid}" cx="520" cy="210" r="70" fill="#fff3c4"/>'
                f'<rect y="260" width="800" height="160" fill="#8f7bd9"/>'
                + "".join(f'<rect x="{x}" y="{y}" width="{w}" height="6" rx="3" fill="#ffffff" opacity=".55"/>'
                          for x, y, w in ((140, 290, 220), (330, 320, 260), (180, 350, 160), (470, 365, 200))))
    if key == "map":
        return (f'<rect width="800" height="420" fill="#1b2a4a"/>'
                + "".join(f'<path d="M{x} 0V420" stroke="#2c4272" stroke-width="3"/>' for x in range(0, 800, 80))
                + "".join(f'<path d="M0 {y}H800" stroke="#2c4272" stroke-width="3"/>' for y in range(40, 420, 80))
                + '<path d="M-20 330C200 300 260 120 480 190S720 120 840 60" stroke="#3b8bff" stroke-width="22" fill="none" stroke-linecap="round"/>'
                f'<circle id="rip{uid}" cx="470" cy="215" r="60" fill="none" stroke="#ff4f6d" stroke-width="4" opacity=".6"/>'
                '<circle cx="470" cy="190" r="34" fill="#ff4f6d"/><circle cx="470" cy="190" r="13" fill="#fff"/>'
                '<path d="M470 224L452 190H488Z" fill="#ff4f6d"/>')
    if key == "pulse":
        return (f'<defs><linearGradient id="{g}" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#ffd1e0"/>'
                f'<stop offset="1" stop-color="#ffb3c8"/></linearGradient></defs><rect width="800" height="420" fill="url(#{g})"/>'
                f'<g id="hb{uid}" style="transform-origin:400px 190px"><path transform="translate(280 60) scale(10)" d="{HEART}" fill="#ff4f6d"/></g>'
                '<path d="M0 330H260L300 270L350 380L400 300L440 330H800" stroke="#fff" stroke-width="10" fill="none" '
                'stroke-linecap="round" stroke-linejoin="round"/>')
    if key == "clock":
        ticks = "".join(f'<rect x="397" y="52" width="6" height="26" rx="3" fill="#8a6bff" transform="rotate({a} 400 210)"/>'
                        for a in range(0, 360, 30))
        return (f'<defs><linearGradient id="{g}" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#e6dcff"/>'
                f'<stop offset="1" stop-color="#cfe0ff"/></linearGradient></defs><rect width="800" height="420" fill="url(#{g})"/>'
                f'<circle cx="400" cy="210" r="170" fill="#fff"/>{ticks}'
                f'<rect id="mh{uid}" x="396" y="90" width="8" height="125" rx="4" fill="#3a3f8f" style="transform-origin:400px 210px"/>'
                f'<rect id="hh{uid}" x="394" y="130" width="12" height="85" rx="6" fill="#8a6bff" style="transform-origin:400px 210px"/>'
                '<circle cx="400" cy="210" r="12" fill="#ff4f6d"/>')
    if key == "rain":
        drops = "".join(f'<path id="d{uid}_{i}" d="M{90 + i * 60} 250l-10 36" stroke="#9ec5ff" stroke-width="5" stroke-linecap="round"/>'
                        for i in range(11))
        return (f'<defs><linearGradient id="{g}" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#5b7aa8"/>'
                f'<stop offset="1" stop-color="#2d3f66"/></linearGradient></defs><rect width="800" height="420" fill="url(#{g})"/>'
                '<g fill="#e9f0ff"><circle cx="330" cy="150" r="70"/><circle cx="430" cy="120" r="85"/><circle cx="520" cy="160" r="62"/>'
                '<rect x="290" y="150" width="270" height="72" rx="36"/></g>' + drops)
    return (f'<defs><linearGradient id="{g}" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#1b1f5c"/>'
            f'<stop offset="1" stop-color="#4a3f8f"/></linearGradient></defs><rect width="800" height="420" fill="url(#{g})"/>'
            '<circle cx="470" cy="190" r="95" fill="#fff6d6"/><circle cx="515" cy="165" r="88" fill="#3a3a8a"/>'
            + "".join(f'<circle id="st{uid}_{i}" cx="{x}" cy="{y}" r="{r}" fill="#fff"/>'
                      for i, (x, y, r) in enumerate(((120, 90, 5), (220, 250, 4), (300, 120, 6), (650, 90, 5), (700, 280, 4), (160, 330, 5))))
            )


def _clip(text, n):
    """Hard-truncate with an ellipsis: the layout check rejects CSS-clipped text, so text must fit by construction."""
    return text if len(text) <= n else text[:n - 1].rstrip() + "…"


def _pick(text, idx):
    t = text.lower()
    for k, (key, *_rest) in enumerate(ARTS):
        if any(s in t for s in ARTS[k][3]):
            return k
    return idx % len(ARTS)


def _cross(i, rng, col):
    x, y, s = rng.randint(30, 1020), rng.randint(120, 1750), rng.randint(18, 42)
    return (f'<svg id="sp{i}" class="sp" style="left:{x}px;top:{y}px;width:{s}px;height:{s}px" viewBox="0 0 10 10">'
            f'<path d="M5 1v8M1 5h8" stroke="{col}" stroke-width="2" stroke-linecap="round"/></svg>')


def build_html(plan, spec, cfg):
    w, hgt, fps = cfg["width"], cfg["height"], cfg["fps"]
    dur, intro = plan["duration"], plan.get("intro", 0.0)
    b1, b2, b3, acc, ta, tb = PAL[spec["palette"]]
    song = spec["song"]
    artist, title = song.get("artist", ""), song["title"]
    handle = cfg.get("handle", "").strip()
    rng = random.Random(7)
    cols = ["#ff6b9d", "#6aa8ff", "#7be0a8", "#ffc15a", "#b58cff"]
    sparks = "".join(_cross(i, rng, cols[i % 5]) for i in range(16))
    js = [f'tl.to("#sp{i}",{{y:{rng.randint(-260, 260)},x:{rng.randint(-80, 80)},rotation:{rng.randint(-90, 90)},'
          f'duration:{dur},ease:"none"}},0);' for i in range(16)]
    clips = []
    # --- intro: big title word, ring, handle
    if intro >= 0.6:
        head = html.escape(_clip(title, 40).upper())
        sub = html.escape(_clip(artist, 40))
        ring = f'<svg id="ring" viewBox="0 0 400 400" style="position:absolute;left:340px;top:360px;width:400px;height:400px"><circle cx="200" cy="200" r="180" fill="none" stroke="{acc}" stroke-width="5" stroke-dasharray="3 22" stroke-linecap="round" opacity=".5"/></svg>'
        fs = max(72, min(150, int(900 / (0.8 * max(len(title), 1)))))
        clips.append(
            f'<div id="clipIntro" class="clip" data-start="0" data-duration="{intro}" data-track-index="2" style="left:0;top:0;width:{w}px;height:{hgt}px">'
            f'<div id="intro" style="position:absolute;inset:0">{ring}'
            f'<div style="position:absolute;left:60px;top:470px;width:960px;display:flex;flex-direction:column;gap:22px">'
            f'<div class="ititle" style="font-size:{fs}px">{head}</div><div class="isub">{sub}</div>'
            + (f'<div class="ihandle">{html.escape(handle)}</div>' if handle else "")
            + '</div></div></div>')
        js.append(f'tl.fromTo("#intro",{{opacity:0,scale:.9}},{{opacity:1,scale:1,duration:.4,ease:"back.out(1.6)"}},0);')
        js.append(f'tl.to("#ring",{{rotation:120,duration:{intro},ease:"none",transformOrigin:"50% 50%"}},0);')
        js.append(f'tl.to("#intro",{{opacity:0,scale:1.06,duration:.25,ease:"power2.in"}},{max(.3, round(intro - .27, 3))});')
    # --- static player chrome (island + bottom bar) from intro to end
    cd = round(dur - intro, 3)
    bars = "".join(f'<div id="eq{k}" class="eq" style="left:{k * 12}px"></div>' for k in range(4))
    clips.append(
        f'<div id="clipChrome" class="clip" data-start="{intro}" data-duration="{cd}" data-track-index="1" style="left:0;top:0;width:{w}px;height:{hgt}px">'
        f'<div id="chrome" style="position:absolute;inset:0">'
        f'<div class="stat" style="left:110px;top:196px">19:47</div><div class="batt" style="left:880px;top:204px"></div>'
        f'<div class="island"><div class="ico"><svg viewBox="0 0 24 24" width="30" height="30"><path d="M9 18V6l10-2v12" stroke="#fff" stroke-width="2" fill="none" stroke-linecap="round"/><circle cx="7" cy="18" r="3" fill="#fff"/><circle cx="17" cy="16" r="3" fill="#fff"/></svg></div>'
        f'<div class="itxt"><b>{html.escape(_clip(title, 17))}</b><span>{html.escape(_clip(artist, 22))}</span></div><div class="eqs">{bars}</div></div>'
        + (f'<div class="chip"><i></i>{html.escape(handle)}</div>' if handle else "")
        + f'<div class="ptitle">{html.escape(_clip((artist + " - " if artist else "") + title, 32))}</div>'
        f'<div class="track"><div id="fill"></div></div><div id="tl" class="tm" style="left:160px">0:00</div><div id="tr" class="tm" style="right:160px">-0:00</div>'
        '</div></div>')
    js.append(f'tl.fromTo("#chrome",{{opacity:0}},{{opacity:1,duration:.4}},{intro});')
    js.append(f'tl.fromTo("#fill",{{width:0}},{{width:760,duration:{cd},ease:"none"}},{intro});')
    js.append(f'const clk={{v:0}};tl.to(clk,{{v:{cd},duration:{cd},ease:"none",onUpdate(){{const a=Math.floor(clk.v),r=Math.ceil({cd}-clk.v);'
              f'document.getElementById("tl").textContent=Math.floor(a/60)+":"+String(a%60).padStart(2,"0");'
              f'document.getElementById("tr").textContent="-"+Math.floor(r/60)+":"+String(r%60).padStart(2,"0");}}}},{intro});')
    grid = [b + intro for b in plan.get("beats", [])] if len(plan.get("beats", [])) >= 8 else [intro + i * .5 for i in range(int(cd / .5))]
    for t in grid[:300]:
        for k in range(4):
            js.append(f'tl.to("#eq{k}",{{scaleY:{rng.uniform(.35, 1):.2f},duration:.12,ease:"power1.out"}},{round(t, 3)});')
    # --- one widget per scene
    for i, s in enumerate(plan["scenes"]):
        d = round(s["end"] - s["start"], 3)
        if d <= 0:
            continue
        outro = s["role"] == "outro"
        k = 2 if outro else _pick(s["text"], i)
        key, app, icol, _ = ARTS[k]
        sub = (f'<span class="w" id="c{i}w0">{html.escape(s["text"])}</span>' if outro or not s.get("words") else
               " ".join(f'<span class="w" id="c{i}w{j}">{html.escape(x["w"])}</span>' for j, x in enumerate(s["words"])))
        app_title = "Слушать полностью" if outro else app
        dots = "".join(f'<i class="dot{" on" if j == i % 5 else ""}"></i>' for j in range(5))
        clips.append(
            f'<div id="clip{i}" class="clip" data-start="{s["start"]}" data-duration="{d}" data-track-index="3" style="left:90px;top:330px;width:900px;height:800px">'
            f'<div id="card{i}" class="wcard"><div class="head"><span class="app" style="background:{icol}"></span><b>{html.escape(app_title)}</b></div>'
            f'<div class="lyric" style="font-size:{44 if len(s["text"]) <= 50 else 38 if len(s["text"]) <= 75 else 32}px">{sub}</div><svg id="art{i}" class="art" viewBox="0 0 800 420" preserveAspectRatio="xMidYMid slice">{_art(key, i)}</svg></div>'
            f'<div class="dots">{dots}</div></div>')
        js.append(f'tl.fromTo("#clip{i}",{{opacity:0,x:70}},{{opacity:1,x:0,duration:.3,ease:"power3.out"}},{s["start"]});')
        js.append(f'tl.to("#clip{i}",{{opacity:0,x:-70,duration:.2,ease:"power2.in"}},{max(round(s["start"] + .31, 3), round(s["end"] - .22, 3))});')
        js.append(f'tl.fromTo("#art{i}",{{scale:1}},{{scale:1.05,duration:{d},ease:"none",transformOrigin:"50% 50%"}},{s["start"]});')
        for j, x in enumerate(s.get("words") or []):
            js.append(f'tl.fromTo("#c{i}w{j}",{{opacity:.28}},{{opacity:1,duration:.12,ease:"power2.out"}},{x["s"]});')
        if not s.get("words"):
            js.append(f'tl.fromTo("#c{i}w0",{{opacity:.3}},{{opacity:1,duration:.3}},{round(s["start"] + .1, 3)});')
        if key == "sunset":
            js.append(f'tl.fromTo("#sun{i}",{{y:40}},{{y:-30,duration:{d},ease:"none"}},{s["start"]});')
        elif key == "map":
            js.append(f'tl.fromTo("#rip{i}",{{scale:.5,opacity:.8,transformOrigin:"50% 50%"}},{{scale:1.8,opacity:0,duration:{min(d, 1.6)},ease:"power1.out"}},{s["start"]});')
        elif key == "pulse":
            js.append(f'tl.fromTo("#hb{i}",{{scale:.92}},{{scale:1.08,duration:{min(d, 1.2)},ease:"sine.inOut"}},{s["start"]});')
        elif key == "clock":
            js.append(f'tl.fromTo("#mh{i}",{{rotation:0}},{{rotation:{int(d * 60)},duration:{d},ease:"none"}},{s["start"]});')
            js.append(f'tl.fromTo("#hh{i}",{{rotation:0}},{{rotation:{int(d * 5)},duration:{d},ease:"none"}},{s["start"]});')
        elif key == "rain":
            for q in range(11):
                js.append(f'tl.fromTo("#d{i}_{q}",{{y:-40,opacity:0}},{{y:110,opacity:1,duration:.7,ease:"none"}},{round(s["start"] + (q % 4) * .15, 3)});')
        else:
            js.append(f'tl.fromTo("#st{i}_0",{{opacity:.2}},{{opacity:1,duration:{min(d, 1.5)},ease:"sine.inOut"}},{s["start"]});')
    return f"""<!doctype html>
<html lang="ru"><head><meta charset="utf-8"><meta name="viewport" content="width={w}, height={hgt}">
<script src="https://cdn.jsdelivr.net/npm/gsap@3.12.5/dist/gsap.min.js"></script>
<style>
html,body{{margin:0;background:{b1};}}
#root{{position:relative;width:{w}px;height:{hgt}px;overflow:hidden;font-family:'Montserrat',sans-serif;
 background:linear-gradient(160deg,{b1},{b2} 55%,{b3});}}
.sp{{position:absolute;opacity:.7}}
.clip{{position:absolute}}
.ititle{{text-align:center;font-weight:900;line-height:1.05;letter-spacing:-2px;overflow-wrap:anywhere;
 background:linear-gradient(90deg,{ta},{tb});-webkit-background-clip:text;background-clip:text;color:transparent;}}
.isub{{text-align:center;font-weight:700;font-size:44px;color:#9a8fb5}}
.ihandle{{text-align:center;font-weight:800;font-size:52px;color:#1a1a2e}}
.stat{{position:absolute;font-weight:800;font-size:34px;color:#1a1a2e}}
.batt{{position:absolute;width:62px;height:28px;border:3px solid #1a1a2e;border-radius:9px;background:linear-gradient(90deg,#1a1a2e 70%,transparent 70%)}}
.island{{position:absolute;left:260px;top:178px;width:560px;height:96px;border-radius:48px;background:#0b0b10;display:flex;align-items:center;gap:16px;padding:0 24px 0 20px;box-sizing:border-box}}
.ico{{width:60px;height:60px;border-radius:14px;background:#2a2a38;display:flex;align-items:center;justify-content:center;flex:none}}
.itxt{{display:flex;flex-direction:column;flex:1;min-width:0}}
.itxt b{{color:#fff;font-size:28px;white-space:nowrap}}
.itxt span{{color:#9a9ab0;font-size:21px;font-weight:600;white-space:nowrap}}
.eqs{{position:relative;width:44px;height:44px;flex:none}}
.eq{{position:absolute;bottom:0;width:8px;height:44px;border-radius:4px;background:{ta};transform-origin:50% 100%}}
.wcard{{position:absolute;left:0;top:0;width:900px;height:740px;box-sizing:border-box;padding:38px 40px;border-radius:60px;background:rgba(255,255,255,.94);
 box-shadow:0 24px 60px rgba(90,70,160,.22);display:flex;flex-direction:column}}
.head{{display:flex;align-items:center;gap:18px;color:#14141f;font-size:40px;font-weight:800;height:52px}}
.app{{width:46px;height:46px;border-radius:13px;display:inline-block}}
.lyric{{margin:10px 0 18px;height:160px;overflow:hidden;font-size:44px;font-weight:700;line-height:1.2;color:{acc}}}
.lyric .w{{display:inline-block;margin-right:12px}}
.art{{width:820px;height:380px;border-radius:36px;overflow:hidden;display:block}}
.dots{{position:absolute;left:0;top:770px;width:900px;display:flex;justify-content:center;gap:14px}}
.dot{{width:14px;height:14px;border-radius:7px;background:#b9b4d6;display:block}}
.dot.on{{width:34px;background:#14141f}}
.chip{{position:absolute;left:400px;top:1136px;width:280px;height:60px;border-radius:30px;background:rgba(255,255,255,.9);
 display:flex;align-items:center;justify-content:center;gap:12px;font-size:30px;font-weight:800;color:#14141f;box-shadow:0 8px 24px rgba(90,70,160,.15)}}
.chip i{{width:30px;height:30px;border-radius:15px;background:linear-gradient(135deg,{ta},{tb});display:block}}
.ptitle{{position:absolute;left:60px;top:1215px;width:960px;text-align:center;white-space:nowrap;font-weight:800;font-size:44px;color:#14141f}}
.track{{position:absolute;left:160px;top:1292px;width:760px;height:8px;border-radius:4px;background:rgba(20,20,31,.15)}}
#fill{{height:8px;border-radius:4px;background:linear-gradient(90deg,{ta},{tb})}}
.tm{{position:absolute;top:1312px;font-size:26px;font-weight:700;color:#6b6585}}
</style></head>
<body>
<div id="root" data-composition-id="main" data-start="0" data-duration="{dur}" data-width="{w}" data-height="{hgt}" data-fps="{fps}">
{sparks}
{chr(10).join(clips)}
</div>
<script>
window.__timelines = window.__timelines || {{}};
const tl = gsap.timeline({{paused:true}});
{chr(10).join(js)}
window.__timelines["main"] = tl;
</script>
</body></html>
"""
