"""Template "widgets": phone-UI edit. Pastel background, Dynamic-Island player, every lyric phrase = one notification-style widget whose
body is a small ANIMATED story that interprets the line (counter, search, camera, chat, scene, dots), optional fake notification in the island.
Inspired by the format of popular "widget edit" videos; all art is our own SVG/CSS.

Pure function: build_html(plan, spec, cfg) -> HyperFrames index.html (every timed element is a .clip, GSAP timeline paused, no randomness
other than a seeded RNG). A scene carries `widget` (dict from spec["widgets"]) or None (auto: scene art picked by keywords).
"""
import html
import json
import math
import random

from . import widget_kinds as wk

PAL = {  # spec palette -> (bg1, bg2, bg3, accent, title gradient a, b)
    "dusk": ("#ffe6f1", "#e9e2ff", "#dbeafe", "#6a5cff", "#ff4f8b", "#a47bff"),
    "cold": ("#e0f0ff", "#e3e8ff", "#f1e4ff", "#3b6cff", "#2f8bff", "#8a6bff"),
    "warm": ("#fff0e0", "#ffe3ec", "#f3e6ff", "#ff5a2d", "#ff7a3d", "#ff3d8b"),
    "contrast": ("#e0fff3", "#e0f0ff", "#efe6ff", "#14956f", "#1fb98a", "#3b8bff"),
}
HEART = "M12 21.35l-1.45-1.32C5.4 15.36 2 12.28 2 8.5 2 5.42 4.42 3 7.5 3c1.74 0 3.41.81 4.5 2.09C13.09 3.81 14.76 3 16.5 3 19.58 3 22 5.42 22 8.5c0 3.78-3.4 6.86-8.55 11.54L12 21.35z"
KINDS = ("scene", "counter", "search", "camera", "chat", "dots", "versus") + wk.NEW_KINDS

# (art key, default app title, icon colour, stems that pick this art for a line)
ARTS = [
    ("sunset", "Закат", "#ff9a6b", ("закат", "солнц", "рассвет", "свет", "лучи")),
    ("map", "Локатор", "#3b8bff", ("дорог", "путь", "иду", "идти", "город", "домой", "улиц", "куда", "где")),
    ("pulse", "Пульс", "#ff4f6d", ("сердц", "любо", "люби", "боль", "чувств", "душ", "дыш")),
    ("clock", "Часы", "#8a6bff", ("врем", "час", "год", "день", "секунд", "вчера", "завтра", "когда", "жизн")),
    ("rain", "Погода", "#4a6a9a", ("дожд", "слез", "плак", "гроз", "холод", "ветер")),
    ("moon", "Ночь", "#3a3f8f", ("ноч", "звезд", "луна", "сон", "спа", "тьм", "темн", "один")),
]
ART_KEYS = [a[0] for a in ARTS] + ["eye", "city", "coins"]
APP_ICON = {a[0]: a[2] for a in ARTS} | {"eye": "#2f8bff", "city": "#5b5bd6", "coins": "#ffb020"}


def _bg(g, a, b, vertical=False):
    d = 'x1="0" y1="0" x2="0" y2="1"' if vertical else 'x1="0" y1="0" x2="1" y2="1"'
    return (f'<defs><linearGradient id="{g}" {d}><stop offset="0" stop-color="{a}"/><stop offset="1" stop-color="{b}"/></linearGradient></defs>'
            f'<rect width="800" height="420" fill="url(#{g})"/>')


def _art(key, uid):
    g = f"g{uid}"
    if key == "sunset":
        return (_bg(g, "#ffd6a5", "#c3a6ff", True) + f'<circle id="sun{uid}" cx="520" cy="210" r="70" fill="#fff3c4"/>'
                '<rect y="260" width="800" height="160" fill="#8f7bd9"/>'
                + "".join(f'<rect x="{x}" y="{y}" width="{w}" height="6" rx="3" fill="#fff" opacity=".55"/>'
                          for x, y, w in ((140, 290, 220), (330, 320, 260), (180, 350, 160), (470, 365, 200))))
    if key == "map":
        return ('<rect width="800" height="420" fill="#1b2a4a"/>'
                + "".join(f'<path d="M{x} 0V420" stroke="#2c4272" stroke-width="3"/>' for x in range(0, 800, 80))
                + "".join(f'<path d="M0 {y}H800" stroke="#2c4272" stroke-width="3"/>' for y in range(40, 420, 80))
                + '<path d="M-20 330C200 300 260 120 480 190S720 120 840 60" stroke="#3b8bff" stroke-width="22" fill="none" stroke-linecap="round"/>'
                f'<circle id="rip{uid}" cx="470" cy="215" r="60" fill="none" stroke="#ff4f6d" stroke-width="4" opacity=".6"/>'
                '<circle cx="470" cy="190" r="34" fill="#ff4f6d"/><circle cx="470" cy="190" r="13" fill="#fff"/><path d="M470 224L452 190H488Z" fill="#ff4f6d"/>')
    if key == "pulse":
        return (_bg(g, "#ffd1e0", "#ffb3c8") + f'<g id="hb{uid}" style="transform-origin:400px 190px"><path transform="translate(280 60) scale(10)" d="{HEART}" fill="#ff4f6d"/></g>'
                '<path d="M0 330H260L300 270L350 380L400 300L440 330H800" stroke="#fff" stroke-width="10" fill="none" stroke-linecap="round" stroke-linejoin="round"/>')
    if key == "clock":
        ticks = "".join(f'<rect x="397" y="52" width="6" height="26" rx="3" fill="#8a6bff" transform="rotate({a} 400 210)"/>' for a in range(0, 360, 30))
        return (_bg(g, "#e6dcff", "#cfe0ff") + f'<circle cx="400" cy="210" r="170" fill="#fff"/>{ticks}'
                f'<rect id="mh{uid}" x="396" y="90" width="8" height="125" rx="4" fill="#3a3f8f" style="transform-origin:400px 210px"/>'
                f'<rect id="hh{uid}" x="394" y="130" width="12" height="85" rx="6" fill="#8a6bff" style="transform-origin:400px 210px"/><circle cx="400" cy="210" r="12" fill="#ff4f6d"/>')
    if key == "rain":
        drops = "".join(f'<path id="d{uid}_{i}" d="M{90 + i * 60} 250l-10 36" stroke="#9ec5ff" stroke-width="5" stroke-linecap="round"/>' for i in range(11))
        return (_bg(g, "#5b7aa8", "#2d3f66", True) + '<g fill="#e9f0ff"><circle cx="330" cy="150" r="70"/><circle cx="430" cy="120" r="85"/>'
                '<circle cx="520" cy="160" r="62"/><rect x="290" y="150" width="270" height="72" rx="36"/></g>' + drops)
    if key == "coins":
        return (_bg(g, "#fff1c4", "#ffd36b", True) + "".join(f'<circle cx="{x}" cy="{y}" r="{r}" fill="#ffc83d" stroke="#e59a00" stroke-width="8"/>'
                                                          for x, y, r in ((260, 300, 70), (540, 300, 70), (400, 210, 100)))
                + '<text x="400" y="252" text-anchor="middle" font-size="130" font-weight="900" fill="#b97a00">₸</text>')
    if key == "eye":
        lashes = "".join(f'<path d="M{400 + 190 * math.cos(math.radians(a)):.0f} {210 - 120 * math.sin(math.radians(a)):.0f}'
                         f'L{400 + 245 * math.cos(math.radians(a)):.0f} {210 - 170 * math.sin(math.radians(a)):.0f}" stroke="#14141f" stroke-width="9" stroke-linecap="round"/>'
                         for a in (50, 70, 90, 110, 130))
        return (_bg(g, "#1b5fd1", "#0a2a6e", True) + '<circle cx="120" cy="90" r="16" fill="#fff" opacity=".25"/><circle cx="690" cy="320" r="22" fill="#fff" opacity=".2"/>'
                '<path d="M110 210Q400 40 690 210Q400 380 110 210Z" fill="#fff"/>' + f'<g id="iris{uid}" style="transform-origin:400px 210px">'
                '<circle cx="400" cy="210" r="92" fill="#4f6bff"/><circle cx="400" cy="210" r="58" fill="#1f2fa8"/><circle cx="400" cy="210" r="30" fill="#0b0b24"/>'
                '<circle cx="428" cy="182" r="16" fill="#fff"/></g>' + lashes)
    if key == "city":
        rng = random.Random(uid + 3)
        b, x = [], 0
        while x < 800:
            w, h = rng.randint(70, 130), rng.randint(120, 300)
            b.append(f'<rect x="{x}" y="{420 - h}" width="{w - 6}" height="{h}" fill="#26245e"/>')
            for wy in range(420 - h + 18, 400, 36):
                for wx in range(x + 12, x + w - 22, 30):
                    if rng.random() < .55:
                        b.append(f'<rect x="{wx}" y="{wy}" width="14" height="18" rx="3" fill="#ffd66b" opacity=".9"/>')
            x += w
        return _bg(g, "#3b2f8f", "#14123a", True) + '<circle cx="640" cy="90" r="40" fill="#fff6d6"/>' + "".join(b)
    return (_bg(g, "#1b1f5c", "#4a3f8f", True) + '<circle cx="470" cy="190" r="95" fill="#fff6d6"/><circle cx="515" cy="165" r="88" fill="#3a3a8a"/>'
            + "".join(f'<circle id="st{uid}_{i}" cx="{x}" cy="{y}" r="{r}" fill="#fff"/>'
                      for i, (x, y, r) in enumerate(((120, 90, 5), (220, 250, 4), (300, 120, 6), (650, 90, 5), (700, 280, 4), (160, 330, 5)))))


def _clip(text, n):
    """Hard-truncate with an ellipsis: the layout check rejects CSS-clipped text, so text must fit by construction."""
    return text if len(text) <= n else text[:n - 1].rstrip() + "…"


def _esc(t, n=60):
    return html.escape(_clip(str(t), n))


def _pick(text, idx):
    t = text.lower()
    for k, a in enumerate(ARTS):
        if any(s in t for s in a[3]):
            return k
    return idx % len(ARTS)


def _cross(i, rng, col):
    x, y, s = rng.randint(30, 1020), rng.randint(20, 1040), rng.randint(18, 42)
    return (f'<svg id="sp{i}" class="sp" style="left:{x}px;top:{y}px;width:{s}px;height:{s}px" viewBox="0 0 10 10">'
            f'<path d="M5 1v8M1 5h8" stroke="{col}" stroke-width="2" stroke-linecap="round"/></svg>')


def _fmt_js(var):
    return f'Math.round({var}).toString().replace(/\\B(?=(\\d{{3}})+(?!\\d))/g,"\\u2009")'


def _num(v):
    return f"{int(v):,}".replace(",", " ")


def _emblem(k):
    if k == "crown":
        return ('<path d="M10 78L16 30L38 52L50 18L62 52L84 30L90 78Z" fill="#ffc83d" stroke="#e59a00" stroke-width="3" stroke-linejoin="round"/>'
                '<circle cx="50" cy="62" r="6" fill="#ff4f6d"/><circle cx="28" cy="64" r="4.5" fill="#3b8bff"/><circle cx="72" cy="64" r="4.5" fill="#3bd18a"/>')
    if k == "heart":
        return f'<path transform="translate(8 8) scale(3.5)" d="{HEART}" fill="#ff4f6d"/>'
    return '<path d="M50 8l12 28 30 3-23 20 7 30-26-16-26 16 7-30L8 39l30-3z" fill="#ffc83d" stroke="#e59a00" stroke-width="3" stroke-linejoin="round"/>'


def _camera_art(i, w):
    rng = random.Random(i + 5)
    bokeh = "".join(f'<circle cx="{rng.randint(40, 760)}" cy="{rng.randint(40, 380)}" r="{rng.randint(30, 80)}" fill="{rng.choice(["#ff9ad5", "#ffd27a", "#7aa8ff"])}" opacity=".22"/>' for _ in range(9))
    corners = "".join(f'<path d="{p}" stroke="#ffd400" stroke-width="7" fill="none" stroke-linecap="round" stroke-linejoin="round"/>'
                      for p in ("M250 95H215V130", "M550 95H585V130", "M250 335H215V300", "M550 335H585V300"))
    hearts = "".join(f'<path id="ht{i}_{q}" transform="translate({300 + q * 45} {150 + (q % 2) * 40}) scale(1.4)" d="{HEART}" fill="#ff4f8b" opacity="0"/>' for q in range(5))
    bub = _clip(str(w.get("bubble", "")), 10)
    return (_bg(f"g{i}", "#3d1f66", "#1a0f3a", True) + bokeh +
            '<circle cx="400" cy="400" r="150" fill="#ff7ac8"/><circle cx="400" cy="205" r="78" fill="#ffd3b8"/><path d="M322 190Q400 90 478 190Q440 140 400 140Q360 140 322 190Z" fill="#6b3b2a"/>'
            '<circle cx="372" cy="210" r="7" fill="#2a1a1a"/><circle cx="428" cy="210" r="7" fill="#2a1a1a"/><path d="M375 242Q400 262 425 242" stroke="#c0455f" stroke-width="6" fill="none" stroke-linecap="round"/>'
            f'<g id="vf{i}">{corners}</g>'
            f'<text x="400" y="78" text-anchor="middle" font-size="30" font-weight="800" fill="#ffd400">ФОКУС: {_esc(w.get("focus", "ЦЕЛЬ"), 12).upper()}</text>'
            f'<circle id="rec{i}" cx="58" cy="76" r="9" fill="#ff3b3b"/><text x="78" y="85" font-size="24" font-weight="800" fill="#fff">REC</text>'
            f'<text x="50" y="352" font-size="26" font-weight="800" fill="#ffd400">ПОРТРЕТ</text>'
            f'<text id="zt{i}" x="750" y="352" text-anchor="end" font-size="30" font-weight="800" fill="#fff">1.0x</text>'
            + hearts
            + (f'<g id="bb{i}"><rect x="470" y="110" width="{60 + 22 * len(bub)}" height="64" rx="32" fill="#ff4f8b"/>'
               f'<text x="{500 + 11 * len(bub)}" y="153" text-anchor="middle" font-size="36" font-weight="800" fill="#fff">{html.escape(bub)}</text></g>'
               if bub else ""))


def _art_anim(key, i, s, d):
    j = []
    if key == "sunset":
        j.append(f'tl.fromTo("#sun{i}",{{y:50}},{{y:-30,duration:{d},ease:"none"}},{s});')
    elif key == "map":
        j.append(f'tl.fromTo("#rip{i}",{{scale:.5,opacity:.8,transformOrigin:"50% 50%"}},{{scale:1.8,opacity:0,duration:{min(d, 1.6)},ease:"power1.out"}},{s});')
    elif key == "pulse":
        j.append(f'tl.fromTo("#hb{i}",{{scale:.92}},{{scale:1.08,duration:{min(d, 1.2)},ease:"sine.inOut"}},{s});')
    elif key == "clock":
        j.append(f'tl.fromTo("#mh{i}",{{rotation:0}},{{rotation:{int(d * 60)},duration:{d},ease:"none"}},{s});')
        j.append(f'tl.fromTo("#hh{i}",{{rotation:0}},{{rotation:{int(d * 5)},duration:{d},ease:"none"}},{s});')
    elif key == "rain":
        for q in range(11):
            j.append(f'tl.fromTo("#d{i}_{q}",{{y:-40,opacity:0}},{{y:110,opacity:1,duration:.7,ease:"none"}},{round(s + (q % 4) * .15, 3)});')
    elif key == "eye":
        j.append(f'tl.fromTo("#iris{i}",{{scale:.8}},{{scale:1.12,duration:{min(d, 1.8)},ease:"sine.inOut"}},{s});')
    elif key == "moon":
        j.append(f'tl.fromTo("#st{i}_0",{{opacity:.2}},{{opacity:1,duration:{min(d, 1.5)},ease:"sine.inOut"}},{s});')
    return j


# ---- widget bodies: (html, js) ----------------------------------------------------------------------------------------
def _body(kind, w, i, s, d, text):
    """HTML+JS of the 820x340 body. s = scene start (abs), d = scene duration; times in JS are absolute."""
    def at(f):
        return round(s + min(f * d, max(d - .35, .1)), 3)
    h, j = "", []
    if kind == "counter":
        art = w.get("art") if w.get("art") in ART_KEYS else "map"
        a, b = int(w.get("from", 0)), int(w.get("to", 100))
        size = max(54, min(120, int(400 / (0.62 * max(len(_num(a)), len(_num(b)), 1)))))
        h = (f'<div class="row"><svg class="cart" viewBox="0 0 800 420" preserveAspectRatio="xMidYMid slice">{_art(art, i)}</svg>'
             f'<div class="cc"><div class="clab">{_esc(w.get("label", ""), 26)}</div>'
             f'<div class="cnum" style="font-size:{size}px"><span id="n{i}">{_num(a)}</span><span id="inf{i}" class="inf" style="font-size:{size}px">∞</span>'
             f'<small>{_esc(w.get("unit", ""), 6)}</small></div>'
             f'<div class="cbar"><i id="bf{i}"></i></div>'
             + (f'<div id="pb{i}" class="pbtn">{_esc(w.get("button"), 20)}</div>' if w.get("button") else "") + '</div></div>')
        j.append(f'const o{i}={{v:{a}}};tl.to(o{i},{{v:{b},duration:{round(d * .7, 3)},ease:"power2.out",onUpdate(){{'
                 f'document.getElementById("n{i}").textContent={_fmt_js(f"o{i}.v")};}}}},{s});')
        j.append(f'tl.fromTo("#bf{i}",{{width:0}},{{width:"{int(float(w.get("fill", 1)) * 100)}%",duration:{round(d * .7, 3)},ease:"power2.out"}},{s});')
        if w.get("button"):
            j.append(f'tl.fromTo("#pb{i}",{{opacity:0,scale:.7,transformOrigin:"0% 50%"}},{{opacity:1,scale:1,duration:.3,ease:"back.out(2)"}},{at(.55)});')
        if w.get("inf"):
            j.append(f'tl.to("#n{i}",{{opacity:0,duration:.2}},{at(.75)});tl.fromTo("#inf{i}",{{opacity:0,scale:.5}},{{opacity:1,scale:1,duration:.3,ease:"back.out(2)"}},{at(.75)});')
        j.extend(_art_anim(art, i, s, d))
    elif kind == "search":
        q = str(w.get("query", text))[:34]
        h = (f'<div class="srch"><span class="mag"></span><span id="q{i}"></span><i class="caret"></i></div>'
             f'<div id="rb{i}" class="rbig">{_esc(w.get("result", "0 результатов"), 18)}</div><div id="rs{i}" class="rsub">{_esc(w.get("sub", ""), 34)}</div>')
        j.append(f'const q{i}={{n:0}};tl.to(q{i},{{n:{len(q)},duration:{round(d * .5, 3)},ease:"none",onUpdate(){{'
                 f'document.getElementById("q{i}").textContent={json.dumps(q, ensure_ascii=False)}.slice(0,Math.round(q{i}.n));}}}},{s + .15:.3f});')
        j.append(f'tl.fromTo("#rb{i}",{{opacity:0,scale:.8,transformOrigin:"50% 50%"}},{{opacity:1,scale:1,duration:.35,ease:"back.out(1.8)"}},{at(.62)});')
        j.append(f'tl.fromTo("#rs{i}",{{opacity:0,y:14}},{{opacity:1,y:0,duration:.3}},{at(.7)});')
    elif kind == "camera":
        zoom = float(w.get("zoom", 4.6))
        h = f'<svg class="cart" style="width:820px;height:340px" viewBox="0 0 800 420" preserveAspectRatio="xMidYMid slice">{_camera_art(i, w)}</svg>'
        j.append(f'const z{i}={{v:1}};tl.to(z{i},{{v:{zoom},duration:{round(d * .8, 3)},ease:"power2.inOut",onUpdate(){{'
                 f'document.getElementById("zt{i}").textContent=z{i}.v.toFixed(1)+"x";}}}},{s});')
        j.append(f'tl.fromTo("#vf{i}",{{scale:1.5,opacity:0,transformOrigin:"400px 190px"}},{{opacity:1,scale:1,duration:.4,ease:"power3.out"}},{s + .1:.3f});')
        j.append(f'tl.to("#rec{i}",{{opacity:.2,duration:.25,yoyo:true,repeat:{max(1, int(d / .5))},ease:"none"}},{s});')
        if w.get("bubble"):
            j.append(f'tl.fromTo("#bb{i}",{{opacity:0,scale:.5,transformOrigin:"0% 100%"}},{{opacity:1,scale:1,duration:.35,ease:"back.out(2)"}},{at(.62)});')
            for q in range(5):
                j.append(f'tl.fromTo("#ht{i}_{q}",{{opacity:0,y:20}},{{opacity:1,y:-60,duration:.9,ease:"power1.out"}},{at(.6 + q * .05)});')
    elif kind == "chat":
        msgs = (w.get("msgs") or [{"from": "her", "text": text}])[:3]
        rows = []
        for k, m in enumerate(msgs):
            me = m.get("from") == "me"
            rows.append(f'<div id="m{i}_{k}" class="bub {"me" if me else "her"}">{_esc(m.get("text", ""), 46)}</div>')
            j.append(f'tl.fromTo("#m{i}_{k}",{{opacity:0,y:30,scale:.85,transformOrigin:"{"100%" if me else "0%"} 100%"}},'
                     f'{{opacity:1,y:0,scale:1,duration:.3,ease:"back.out(1.8)"}},{at(.1 + k * .28)});')
        h = f'<div class="chat">{"".join(rows)}</div>'
    elif kind == "dots":
        a, b = int(w.get("from", 8000000000)), int(w.get("to", 1))
        dots = "".join(f'<circle id="dt{i}_{r * 24 + c}" cx="{20 + c * 33}" cy="{20 + r * 33}" r="7" fill="#b9b4d6"/>' for r in range(6) for c in range(24))
        h = (f'<svg class="dgrid" viewBox="0 0 800 210">{dots}</svg>'
             f'<div id="ch{i}" class="chosen">{_esc(w.get("chosen", "Она"), 8)}</div>'
             f'<div class="dlab">{_esc(w.get("label", ""), 30)}</div><div class="dnum" id="dn{i}">{_num(a)}</div><div class="dsub">{_esc(w.get("sub", ""), 30)}</div>')
        order = list(range(144))
        random.Random(i + 11).shuffle(order)
        for n, idx in enumerate(order):
            j.append(f'tl.to("#dt{i}_{idx}",{{opacity:0,duration:.25}},{round(s + .25 + n / 144 * d * .5, 3)});')
        j.append(f'const dd{i}={{v:{a}}};tl.to(dd{i},{{v:{b},duration:{round(d * .6, 3)},ease:"power3.out",onUpdate(){{'
                 f'document.getElementById("dn{i}").textContent={_fmt_js(f"dd{i}.v")};}}}},{s + .2:.3f});')
        j.append(f'tl.fromTo("#ch{i}",{{opacity:0,scale:.3,transformOrigin:"50% 50%"}},{{opacity:1,scale:1,duration:.45,ease:"back.out(2)"}},{at(.6)});')
    elif kind == "versus":
        keys = [w.get("art") if w.get("art") in ART_KEYS else "sunset", w.get("art2") if w.get("art2") in ART_KEYS else "rain"]
        labs = [w.get("label", ""), w.get("label2", "")]
        for side, (key, lab) in enumerate(zip(keys, labs)):
            uid = 1000 + i * 2 + side
            h += (f'<div id="vs{side}_{i}" style="position:absolute;left:{side * 420}px;top:0;width:400px;height:340px">'
                  f'<svg viewBox="0 0 800 420" preserveAspectRatio="xMidYMid slice" style="width:400px;height:270px;border-radius:26px;display:block">{_art(key, uid)}</svg>'
                  f'<div style="margin-top:14px;text-align:center;font-weight:800;font-size:30px;color:#14141f">{_esc(lab, 20)}</div></div>')
            j.append(f'tl.fromTo("#vs{side}_{i}",{{opacity:0,x:{-60 if side == 0 else 60},scale:.92}},{{opacity:1,x:0,scale:1,duration:.4,ease:"back.out(1.6)"}},{at(.02 if side == 0 else .28)});')
            j.extend(_art_anim(key, uid, s, d))
    elif kind in wk.BUILD:
        h, jj = wk.BUILD[kind](w, i, s, d, at)
        j.extend(jj)
    else:  # scene
        art = w.get("art") if w.get("art") in ART_KEYS else "sunset"
        over = ""
        if w.get("big"):
            over += f'<div class="sbig">{_esc(w["big"], 8)}</div>'
        if w.get("emblem") in ("crown", "heart", "star"):
            over += (f'<svg id="em{i}" class="emb" viewBox="0 0 100 100"' + (' style="left:600px;top:70px;width:170px;height:170px"' if w.get("big") else "")
                     + f'>{_emblem(w["emblem"])}</svg>')
            j.append(f'tl.fromTo("#em{i}",{{opacity:0,y:-60,rotation:-14,scale:.6,transformOrigin:"50% 50%"}},{{opacity:1,y:0,rotation:0,scale:1,duration:.5,ease:"bounce.out"}},{at(.18)});')
        if w.get("pill"):
            over += f'<div id="pl{i}" class="spill"><i></i>{_esc(w["pill"], 24)}</div>'
            j.append(f'tl.fromTo("#pl{i}",{{opacity:0,y:30,scale:.8}},{{opacity:1,y:0,scale:1,duration:.35,ease:"back.out(2)"}},{at(.5)});')
        h = f'<div class="sc"><svg class="cart" style="width:820px;height:340px" viewBox="0 0 800 420" preserveAspectRatio="xMidYMid slice">{_art(art, i)}</svg>{over}</div>'
        j.extend(_art_anim(art, i, s, d))
    return h, j


AUTO = [  # (stems, widget): meaning-by-keyword fallback when the spec has no hand-written widget for a line (first match wins)
    (("смерт", "убил", "оруж", "убий", "пуля", "кровь", "опасн"), {"kind": "alert", "word": "ОПАСНО"}),
    (("люб", "сердц"), {"kind": "pulse", "from": 72, "to": 128}),
    (("вместе", "двое", "рядом", "с тобой", "тобой", "мы "), {"kind": "pair", "a": "Я", "b": "Ты"}),
    (("год", "лет", "помн", "раньше", "прошл", "вчера"), {"kind": "polaroid", "from": 2019, "to": 2026, "label": "тогда и сейчас"}),
    (("холод", "боль", "болел", "болен", "мерз", "темпер"), {"kind": "thermo"}),
    (("путь", "дорог", "иду", "идти", "домой", "город", "шаг"), {"kind": "route", "from": "Откуда", "to": "Куда"}),
    (("счасть", "радост", "улыб", "смех", "мечт"), {"kind": "ring", "from": 10, "to": 100, "label": "счастье"}),
    (("цель", "стрел", "враг", "бой"), {"kind": "target"}),
]
GREY, INK = "#b9b4cf", "#14141f"
BODY_X, BODY_Y = 130, 396  # stage coords of the 820x340 card body
ANCH = {"pair": (410, 150), "pulse": (190, 110), "route": (660, 60), "venn": (410, 170), "ring": (410, 150), "thermo": (241, 272),
        "alert": (410, 190), "target": (410, 170), "polaroid": (165, 150), "versus": (200, 130), "counter": (170, 170),
        "search": (410, 45), "camera": (410, 170), "chat": (200, 170), "dots": (410, 88), "scene": (410, 170)}
CARD_H = 606  # 30+64 head+14+128 lyric+340 body+30 padding; fixed so every card sits the same way


GLYPH = {
    "bubble": '<path d="M4 5h16v11H9l-5 4z" fill="#fff"/>',
    "heart": f'<path d="{HEART}" fill="#fff"/>',
    "pin": '<path d="M12 2a7 7 0 0 0-7 7c0 5 7 13 7 13s7-8 7-13a7 7 0 0 0-7-7zm0 9.5A2.5 2.5 0 1 1 12 6.5a2.5 2.5 0 0 1 0 5z" fill="#fff"/>',
    "lines": '<path d="M5 6h14M5 12h14M5 18h9" stroke="#fff" stroke-width="2.4" stroke-linecap="round"/>',
    "bell": '<path d="M12 3a6 6 0 0 0-6 6v4l-2 3h16l-2-3V9a6 6 0 0 0-6-6zm-2 15a2 2 0 0 0 4 0z" fill="#fff"/>',
}


def _glyph(bn):
    a = (str(bn.get("app", "")) + str(bn.get("glyph", ""))).lower()
    key = ("bubble" if any(x in a for x in ("сообщ", "чат", "бесед")) else "heart" if any(x in a for x in ("здоров", "пульс", "фото", "любов"))
           else "pin" if "карт" in a else "lines" if any(x in a for x in ("журнал", "напомин", "заметк", "новост", "выбор")) else "bell")
    return f'<svg viewBox="0 0 24 24" width="32" height="32">{GLYPH[key]}</svg>'


def _auto(text, prev):
    t = text.lower()
    for stems, wd in AUTO:
        if wd["kind"] != prev and any(x in t for x in stems):
            return dict(wd)
    return {}


def build_html(plan, spec, cfg):
    w, hgt, fps = cfg["width"], cfg["height"], cfg["fps"]
    SQ = w  # the whole phone-UI lives in a 1:1 square in the middle of the 9:16 frame; black bars above/below are TikTok safe zones
    OY = (hgt - SQ) // 2
    dur, intro = plan["duration"], plan.get("intro", 0.0)
    b1, b2, b3, acc, ta, tb = PAL[spec["palette"]]
    song = spec["song"]
    artist, title = song.get("artist", ""), song["title"]
    handle = (cfg.get("handle") or "vybex").strip().lstrip("@")
    credit = f"автор: {handle}"
    hook = html.escape(_clip(str(spec.get("hook") or "О чём эта строка?").upper(), 36))
    hfs = 124 if len(hook) <= 14 else 100 if len(hook) <= 24 else 80
    rng = random.Random(7)
    cols = ["#ff6b9d", "#6aa8ff", "#7be0a8", "#ffc15a", "#b58cff"]
    sparks = "".join(_cross(i, rng, cols[i % 5]) for i in range(16))
    sparks += "".join(f'<svg id="cd{k}" class="sp" style="left:{rng.randint(20, 1040)}px;top:{rng.randint(20, 1040)}px;width:{rng.randint(10, 22)}px;height:{rng.randint(10, 22)}px" '
                      f'viewBox="0 0 10 10"><circle cx="5" cy="5" r="4" fill="{cols[k % 5]}"/></svg>' for k in range(16))
    js = [f'tl.to("#cd{k}",{{y:{rng.randint(-300, 300)},x:{rng.randint(-100, 100)},duration:{dur},ease:"none"}},0);' for k in range(16)]
    js += [f'tl.to("#sp{i}",{{y:{rng.randint(-260, 260)},x:{rng.randint(-80, 80)},rotation:{rng.randint(-90, 90)},'
          f'duration:{dur},ease:"none"}},0);' for i in range(16)]
    clips = []
    if intro >= 0.6:  # --- intro: album-style icon + dashed ring + credit
        ring = (f'<svg id="ring" viewBox="0 0 400 400" style="position:absolute;left:340px;top:240px;width:400px;height:400px"><circle cx="200" cy="200" r="180" '
                f'fill="none" stroke="{acc}" stroke-width="5" stroke-dasharray="3 22" stroke-linecap="round" opacity=".55"/></svg>')
        icon = (f'<div id="iicon" style="position:absolute;left:430px;top:330px;width:220px;height:220px;border-radius:54px;'
                f'background:linear-gradient(135deg,{ta},{tb});box-shadow:0 20px 50px rgba(90,70,160,.3);display:flex;align-items:center;justify-content:center">'
                f'<svg viewBox="0 0 24 24" width="120" height="120"><path d="M9 18V6l10-2v12" stroke="#fff" stroke-width="2" fill="none" stroke-linecap="round"/>'
                f'<circle cx="7" cy="18" r="3" fill="#fff"/><circle cx="17" cy="16" r="3" fill="#fff"/></svg></div>')
        clips.append(
            f'<div id="clipIntro" class="clip" data-start="0" data-duration="{intro}" data-track-index="2" style="left:0;top:0;width:{w}px;height:{SQ}px">'
            f'<div id="intro" style="position:absolute;inset:0">{ring}{icon}'
            f'<div id="itx" style="position:absolute;left:0;top:640px;width:{w}px;display:flex;flex-direction:column;gap:14px">'
            f'<div class="icredit">{html.escape(credit)}</div><div class="isub">{html.escape(_clip((artist + " — " if artist else "") + title, 30))}</div></div></div></div>')
        js.append(f'tl.fromTo("#iicon",{{scale:.3,rotation:-20,opacity:0}},{{scale:1,rotation:0,opacity:1,duration:.5,ease:"back.out(1.8)"}},0);')
        js.append(f'tl.fromTo("#ring",{{scale:.6,opacity:0}},{{scale:1,opacity:1,duration:.4,ease:"power2.out",transformOrigin:"50% 50%"}},0);')
        js.append(f'tl.to("#ring",{{rotation:150,duration:{intro},ease:"none",transformOrigin:"50% 50%"}},0);')
        js.append(f'tl.fromTo("#iicon",{{y:0}},{{y:-10,duration:.5,yoyo:true,repeat:{max(1, int(intro / .5))},ease:"sine.inOut",immediateRender:false}},.5);')
        js.append(f'tl.fromTo("#itx",{{opacity:0,y:24}},{{opacity:1,y:0,duration:.35,ease:"power2.out"}},.2);')
        js.append(f'tl.to("#intro",{{opacity:0,scale:1.08,duration:.25,ease:"power2.in",transformOrigin:"50% 40%"}},{max(.3, round(intro - .27, 3))});')
        for q in range(14):  # confetti ring burst
            ang = q / 14 * 6.283
            clips.append(f'<svg id="ib{q}" class="sp" style="left:{525 + int(110 * math.cos(ang))}px;top:{425 + int(110 * math.sin(ang))}px;width:30px;height:30px;opacity:0" viewBox="0 0 10 10">'
                         f'<path d="M5 1v8M1 5h8" stroke="{cols[q % 5]}" stroke-width="2" stroke-linecap="round"/></svg>')
            js.append(f'tl.fromTo("#ib{q}",{{opacity:.95,x:0,y:0,rotation:0}},{{opacity:0,x:{int(260 * math.cos(ang))},y:{int(260 * math.sin(ang))},rotation:{120 + q * 17},duration:.9,ease:"power2.out",immediateRender:false}},.12);')
    ost = next((x["start"] for x in plan["scenes"] if x["role"] == "outro"), dur)  # end card start: the player chrome leaves before it
    cd = round(ost - intro, 3)  # --- static player chrome
    bars = "".join(f'<div id="eq{k}" class="eq" style="left:{k * 12}px"></div>' for k in range(4))
    clips.append(
        f'<div id="clipChrome" class="clip" data-start="{intro}" data-duration="{cd}" data-track-index="1" style="left:0;top:0;width:{w}px;height:{SQ}px">'
        f'<div id="chrome" style="position:absolute;inset:0">'
        f'<div class="stat" style="left:110px;top:62px">19<span id="colon">:</span>47</div><div class="batt" style="left:880px;top:70px"><i id="bf"></i></div>'
        f'<div id="isl" class="island"><div id="isc" class="isc"><div id="inote" class="ico"><svg viewBox="0 0 24 24" width="30" height="30"><path d="M9 18V6l10-2v12" stroke="#fff" stroke-width="2" fill="none" stroke-linecap="round"/>'
        f'<circle cx="7" cy="18" r="3" fill="#fff"/><circle cx="17" cy="16" r="3" fill="#fff"/></svg></div>'
        f'<div class="itxt"><b>{html.escape(_clip(title, 17))}</b><span>{html.escape(_clip(artist, 22))}</span></div><div class="eqs">{bars}</div></div></div>'
        f'<div id="chip" class="chip"><i id="cav"></i>{html.escape(credit)}</div>'
        f'<div id="ptitle" class="ptitle">{html.escape(_clip((artist + " — " if artist else "") + title, 32))}</div>'
        f'<div class="track"><div id="fill"></div></div><div id="thumb" class="thumb"></div><div id="tl" class="tm" style="left:160px">0:00</div><div id="tr" class="tm" style="right:160px">-0:00</div>'
        '</div></div>')
    js.append(f'tl.fromTo("#chrome",{{opacity:0}},{{opacity:1,duration:.4}},{intro});')
    js.append(f'tl.to("#chrome",{{opacity:0,duration:.3}},{round(max(intro + .5, ost - .3), 3)});')
    js.append(f'tl.fromTo("#thumb",{{x:0}},{{x:760,duration:{cd},ease:"none"}},{intro});')
    js.append(f'tl.fromTo("#fill",{{width:0}},{{width:760,duration:{cd},ease:"none"}},{intro});')
    js.append(f'const clk={{v:0}};tl.to(clk,{{v:{cd},duration:{cd},ease:"none",onUpdate(){{const a=Math.floor(clk.v),r=Math.ceil({cd}-clk.v);'
              f'document.getElementById("tl").textContent=Math.floor(a/60)+":"+String(a%60).padStart(2,"0");'
              f'document.getElementById("tr").textContent="-"+Math.floor(r/60)+":"+String(r%60).padStart(2,"0");}}}},{intro});')
    # idle motion: nothing on screen stands still
    js.append(f'tl.fromTo("#colon",{{opacity:1}},{{opacity:.15,duration:.5,yoyo:true,repeat:{max(1, int(cd / .5))},ease:"steps(1)"}},{intro});')
    js.append(f'tl.fromTo("#bf",{{width:"70%"}},{{width:"52%",duration:{cd},ease:"none"}},{intro});')
    js.append(f'tl.fromTo("#inote",{{rotation:-12}},{{rotation:12,duration:.6,yoyo:true,repeat:{max(1, int(cd / .6))},ease:"sine.inOut"}},{intro});')
    js.append(f'tl.fromTo("#cav",{{rotation:0}},{{rotation:{360 * max(1, int(cd / 3))},duration:{cd},ease:"none"}},{intro});')
    js.append(f'tl.fromTo("#ptitle",{{y:-3}},{{y:3,duration:1.2,yoyo:true,repeat:{max(1, int(cd / 1.2))},ease:"sine.inOut"}},{intro});')
    js.append(f'tl.fromTo("#bl1",{{x:0,y:0}},{{x:420,y:380,duration:{dur},ease:"sine.inOut"}},0);')
    js.append(f'tl.fromTo("#bl2",{{x:0,y:0}},{{x:-420,y:-380,duration:{dur},ease:"sine.inOut"}},0);')
    tq = intro
    while tq < ost - .2:  # the equalizer keeps moving between beats too
        for k in range(4):
            js.append(f'tl.to("#eq{k}",{{scaleY:{rng.uniform(.3, 1):.2f},duration:.2,ease:"sine.inOut"}},{round(tq, 3)});')
        tq += .25
    grid = list(plan.get("beats", [])) if len(plan.get("beats", [])) >= 8 else [intro + i * .5 for i in range(int(cd / .5))]
    for t in grid[:300]:
        for k in range(4):
            js.append(f'tl.to("#eq{k}",{{scaleY:{rng.uniform(.35, 1):.2f},duration:.12,ease:"power1.out"}},{round(t, 3)});')
    for bi, t in enumerate(grid[:300]):  # downbeats (every 4th): island, chip, title, progress thumb pop; background flashes
        if bi % 4 == 0 and t >= intro:
            js.append(f'tl.fromTo("#flash",{{opacity:.5}},{{opacity:0,duration:.4,ease:"power2.out",immediateRender:false}},{round(t, 3)});')
            for el, sc in (("isl", 1.07), ("chip", 1.08), ("ptitle", 1.05), ("thumb", 1.6)):
                js.append(f'tl.fromTo("#{el}",{{scale:{sc}}},{{scale:1,duration:.3,ease:"power3.out",immediateRender:false}},{round(t, 3)});')
    prev, couriers = "", []
    for i, s in enumerate(plan["scenes"]):  # --- one widget per scene
        nxt = plan["scenes"][i + 1]["start"] if i + 1 < len(plan["scenes"]) else s["end"]
        s = dict(s, end=max(s["end"], min(nxt, s["end"] + 1.2, dur)))  # hold the card through short vocal gaps: never an empty stage
        d = round(s["end"] - s["start"], 3)
        if d <= 0:
            continue
        outro = s["role"] == "outro"
        if outro:  # end card (mirrors the intro): the last card collapses into an orb, then icon + big title + credit + confetti ring
            t0 = s["start"]
            tt = html.escape(_clip(title.upper(), 24))
            fs2 = max(60, min(112, int(900 / (0.78 * max(len(_clip(title, 24)), 1)))))
            clips.append(
                f'<div id="clip{i}" class="clip" data-start="{t0}" data-duration="{d}" data-track-index="3" style="left:0;top:0;width:{w}px;height:{SQ}px">'
                f'<svg id="oring" viewBox="0 0 400 400" style="position:absolute;left:340px;top:240px;width:400px;height:400px"><circle cx="200" cy="200" r="180" fill="none" '
                f'stroke="{acc}" stroke-width="5" stroke-dasharray="3 22" stroke-linecap="round" opacity=".55"/></svg>'
                f'<div id="oicon" style="position:absolute;left:430px;top:330px;width:220px;height:220px;border-radius:54px;background:linear-gradient(135deg,{ta},{tb});'
                f'box-shadow:0 20px 50px rgba(90,70,160,.3);display:flex;align-items:center;justify-content:center"><svg viewBox="0 0 24 24" width="120" height="120">'
                f'<path d="M9 18V6l10-2v12" stroke="#fff" stroke-width="2" fill="none" stroke-linecap="round"/><circle cx="7" cy="18" r="3" fill="#fff"/><circle cx="17" cy="16" r="3" fill="#fff"/></svg></div>'
                f'<div id="otx" style="position:absolute;left:0;top:585px;width:{w}px;display:flex;flex-direction:column;align-items:center;gap:12px">'
                f'<div class="fbig" style="font-size:{fs2}px">{tt}</div><div class="isub">{html.escape(_clip(artist, 30))}</div>'
                f'<div class="icredit" style="font-size:46px">{html.escape(credit)}</div></div></div>')
            js.append(f'tl.fromTo("#oring",{{scale:.6,opacity:0}},{{scale:1,opacity:1,duration:.4,ease:"power2.out",transformOrigin:"50% 50%"}},{round(t0 + .2, 3)});')
            js.append(f'tl.to("#oring",{{rotation:150,duration:{d},ease:"none",transformOrigin:"50% 50%"}},{t0});')
            js.append(f'tl.fromTo("#oicon",{{scale:.2,rotation:-25,opacity:0}},{{scale:1,rotation:0,opacity:1,duration:.5,ease:"back.out(1.8)"}},{round(t0 + .2, 3)});')
            js.append(f'tl.fromTo("#otx",{{opacity:0,y:24}},{{opacity:1,y:0,duration:.4,ease:"power2.out"}},{round(t0 + .45, 3)});')
            couriers.append(f'<div id="orb" class="cr" style="left:480px;top:403px;width:120px;height:120px;border-radius:60px;'
                            f'background:radial-gradient(circle,#fff 0 20%,{ta} 42%,rgba(255,255,255,0) 72%)"></div>')
            js.append(f'tl.fromTo("#orb",{{scale:.2,opacity:0}},{{scale:1,opacity:1,duration:.3,ease:"power2.out"}},{round(t0 - .2, 3)});')
            js.append(f'tl.to("#orb",{{scale:2.8,opacity:0,duration:.35,ease:"power2.out"}},{round(t0 + .15, 3)});')
            js.append(f'tl.fromTo("#oicon",{{y:0}},{{y:-10,duration:.8,yoyo:true,repeat:{max(1, int(d / .8))},ease:"sine.inOut",immediateRender:false}},{round(t0 + .75, 3)});')
            js.append(f'tl.fromTo("#otx",{{scale:1}},{{scale:1.04,duration:.9,yoyo:true,repeat:{max(1, int(d / .9))},ease:"sine.inOut",immediateRender:false}},{round(t0 + .9, 3)});')
            for q in range(14):
                ang = q / 14 * 6.283
                clips.append(f'<svg id="ob{q}" class="sp" style="left:{525 + int(110 * math.cos(ang))}px;top:{425 + int(110 * math.sin(ang))}px;width:30px;height:30px;opacity:0" viewBox="0 0 10 10">'
                             f'<path d="M5 1v8M1 5h8" stroke="{cols[q % 5]}" stroke-width="2" stroke-linecap="round"/></svg>')
                js.append(f'tl.fromTo("#ob{q}",{{opacity:.95,x:0,y:0,rotation:0}},{{opacity:0,x:{int(260 * math.cos(ang))},y:{int(260 * math.sin(ang))},rotation:{120 + q * 17},duration:.9,ease:"power2.out",immediateRender:false}},{round(t0 + .2, 3)});')
            wd, kind = {}, "outro"
        else:
            wd = s.get("widget") or _auto(s["text"], prev)
            k = _pick(s["text"], i)
            kind = wd.get("kind") if wd.get("kind") in KINDS else "scene"
            if kind == "scene" and wd.get("art") not in ART_KEYS:
                wd = dict(wd, art=ARTS[k][0])
            dapp, dicon, dcat = wk.DEFAULT_APP.get(kind, (ARTS[k][1], APP_ICON.get(wd.get("art"), ARTS[k][2]), ""))
            app, icol, cat = wd.get("app") or dapp, wd.get("icon") or dicon, wd.get("cat", dcat)
            accent = "#ff4f6d" if icol.lower() in ("#14141f", "#0b0b10") else icol
            text = _clip(s["text"], 100)
            words, tot = [], 0
            for x in (s.get("words") or []):  # keep the displayed words within the 100-char budget the card was sized for
                tot += len(x["w"]) + 1
                if tot > 101:
                    break
                words.append(x)
            sub = (f'<span class="w" id="c{i}w0">{html.escape(text)}</span>' if not words else
                   " ".join(f'<span class="w" id="c{i}w{q}">{html.escape(x["w"])}</span>' for q, x in enumerate(words)))
            fs = 44 if len(text) <= 38 else 38 if len(text) <= 60 else 32
            b_html, b_js = _body(kind, wd, i, s["start"], d, text)
            life = round(min(d + .6, dur - s["start"]), 3)  # the card lingers behind the next one (stack)
            dots = "".join(f'<i{(" id=dn%d" % i) if q == i % 5 else ""} class="dot{" on" if q == i % 5 else ""}"></i>' for q in range(5))
            head = f'<div class="ht"><b>{_esc(app, 20)}</b>' + (f'<em>{_esc(cat, 22)}</em>' if cat else "") + '</div>'
            clips.append(
                f'<div id="clip{i}" class="clip" data-start="{s["start"]}" data-duration="{life}" data-track-index="3" data-layout-allow-overlap data-layout-allow-occlusion style="left:90px;top:160px;width:900px;height:{CARD_H + 40}px">'
                f'<div id="sw{i}" style="position:absolute;left:0;top:0;width:900px;height:{CARD_H + 40}px">'
                f'<div id="card{i}" class="wcard" style="height:{CARD_H}px"><div class="shn"><i id="sh{i}"></i></div><div class="head"><span id="ap{i}" class="app" style="background:{icol}"></span>{head}</div>'
                f'<div class="lyric"><div class="lt" style="font-size:{fs}px">{sub}</div></div><div id="bd{i}" class="body">{b_html}</div></div>'
                f'<div class="dots" style="top:{CARD_H + 16}px">{dots}</div></div></div>')
            js.append(f'tl.fromTo("#clip{i}",{{opacity:0,scale:.92,y:150,x:-40,rotation:-5,rotationX:-12,transformPerspective:900,filter:"blur(10px)"}},'
                      f'{{opacity:1,scale:1,y:0,x:0,rotation:0,rotationX:0,filter:"blur(0px)",duration:.45,ease:"back.out(1.15)",transformOrigin:"50% 30%"}},{s["start"]});')
            if i + 1 < len(plan["scenes"]) and plan["scenes"][i + 1]["role"] == "outro":  # collapse into the orb of the end card
                te = round(max(s["end"] - .35, s["start"] + .5), 3)
                js.append(f'tl.to("#clip{i}",{{scale:.08,opacity:0,filter:"blur(6px)",duration:.35,ease:"power3.in",transformOrigin:"50% 50%"}},{te});')
            else:
                te = round(max(s["end"], s["start"] + .5), 3)
                js.append(f'tl.to("#clip{i}",{{opacity:.5,scale:.93,y:-60,filter:"blur(5px)",duration:.4,ease:"power2.out"}},{te});')
                js.append(f'tl.to("#clip{i}",{{opacity:0,duration:.2,ease:"none"}},{round(te + .4, 3)});')
            sg, cur, tsw, n_sw = (1 if i % 2 == 0 else -1), 0.0, s["start"] + .45, 0  # slow sway: the whole card turns left and right
            while tsw < s["end"] + .3:
                tgt = sg * (4 + (n_sw * 3) % 4)
                js.append(f'tl.fromTo("#sw{i}",{{rotationY:{cur},rotation:{round(cur * .25, 2)},transformPerspective:900}},'
                          f'{{rotationY:{tgt},rotation:{round(tgt * .25, 2)},duration:1.3,ease:"sine.inOut",immediateRender:false}},{round(tsw, 3)});')
                cur, sg, tsw, n_sw = tgt, -sg, tsw + 1.3, n_sw + 1
            if prev and prev != "outro":  # a glowing orb flies from the previous card's key object to this card's: the "linked" transition
                (ax, ay), (bx, by) = [(BODY_X + ANCH.get(k, (410, 170))[0], BODY_Y + ANCH.get(k, (410, 170))[1]) for k in (prev, kind)]
                top = min(ay, by) - 80
                for sfx, dl, sz in (("", 0.0, 1.0), ("b", .05, .62), ("c", .1, .4)):
                    r = 28 * sz
                    ox, oy, ex, ey, tp = ax - r, ay - r, bx - r, by - r, top - r
                    tt0 = round(s["start"] - .05 + dl, 3)
                    couriers.append(f'<div id="cr{i}{sfx}" class="cr" style="width:{int(2 * r)}px;height:{int(2 * r)}px;border-radius:{int(r)}px;'
                                    f'background:radial-gradient(circle,#fff 0 22%,{accent} 40%,rgba(255,255,255,0) 72%)"></div>')
                    js.append(f'tl.fromTo("#cr{i}{sfx}",{{x:{ox},y:{oy},opacity:0,scale:.5}},{{opacity:{1 - dl * 2:.2f},scale:1,duration:.1}},{tt0});')
                    js.append(f'tl.fromTo("#cr{i}{sfx}",{{x:{ox}}},{{x:{ex},duration:.45,ease:"power2.inOut",immediateRender:false}},{tt0});')
                    js.append(f'tl.fromTo("#cr{i}{sfx}",{{y:{oy}}},{{y:{tp},duration:.22,ease:"power2.out",immediateRender:false}},{tt0});')
                    js.append(f'tl.to("#cr{i}{sfx}",{{y:{ey},duration:.23,ease:"power2.in"}},{round(tt0 + .22, 3)});')
                    js.append(f'tl.to("#cr{i}{sfx}",{{scale:2.4,opacity:0,duration:.2,ease:"power2.out"}},{round(tt0 + .45, 3)});')
            for q, x in enumerate(words):  # word-by-word: grey -> accent pop -> ink
                t0 = round(x["s"], 3)
                t1 = round(max(words[q + 1]["s"] if q + 1 < len(words) else t0 + .5, t0 + .2), 3)
                js.append(f'tl.fromTo("#c{i}w{q}",{{color:"{GREY}"}},{{color:"{accent}",duration:.08,ease:"none"}},{t0});')
                js.append(f'tl.fromTo("#c{i}w{q}",{{color:"{accent}"}},{{color:"{INK}",duration:.18,ease:"none",immediateRender:false}},{t1});')
                js.append(f'tl.fromTo("#c{i}w{q}",{{scale:1,y:0}},{{scale:1.22,y:-5,duration:.1,yoyo:true,repeat:1,ease:"power2.out",transformOrigin:"50% 100%",immediateRender:false}},{t0});')
            if not words:
                js.append(f'tl.fromTo("#c{i}w0",{{color:"{GREY}"}},{{color:"{INK}",duration:.4}},{round(s["start"] + .1, 3)});')
            js.extend(b_js)
            tsh = s["start"] + .7  # light sweep across the card, repeated
            while tsh < s["end"] - .3:
                js.append(f'tl.fromTo("#sh{i}",{{x:0}},{{x:1300,duration:.9,ease:"power1.inOut",immediateRender:false}},{round(tsh, 3)});')
                tsh += 2.2
            js.append(f'tl.fromTo("#bd{i}",{{y:0}},{{y:5,duration:1.1,yoyo:true,repeat:{max(1, int(d / 1.1))},ease:"sine.inOut",immediateRender:false}},{round(s["start"] + .5, 3)});')
            for bi, t in enumerate(grid[:300]):  # the whole card sways in 3D on every beat, harder on downbeats
                if s["start"] + .5 <= t < s["end"] - .1:
                    k, sg = (1.8 if bi % 4 == 0 else 1.0), (1 if bi % 2 == 0 else -1)
                    js.append(f'tl.fromTo("#ap{i}",{{scale:1.25,rotation:{-10 * sg}}},{{scale:1,rotation:0,duration:.3,ease:"power3.out",immediateRender:false}},{round(t, 3)});')
                    js.append(f'tl.fromTo("#dn{i}",{{scaleX:1.5}},{{scaleX:1,duration:.3,ease:"power3.out",immediateRender:false}},{round(t, 3)});')
                    js.append(f'tl.fromTo("#card{i}",{{rotation:{round(1.1 * k * sg, 2)},rotationY:{round(5 * k * sg, 2)},scale:{round(1 + .022 * k, 3)},transformPerspective:900,immediateRender:false}},'
                              f'{{rotation:0,rotationY:0,scale:1,duration:.34,ease:"power3.out",immediateRender:false}},{round(t, 3)});')
            if "notify" in wd:  # phone-style banner drops from the top over the clock and the player island, then the music shows again
                bn = wd["notify"]
            elif kind in wk.DEFAULT_NOTIFY:
                bn = wk.DEFAULT_NOTIFY[kind]
            elif "toast" in wd:
                bn = wd["toast"]
            else:
                bn = wk.DEFAULT_TOAST.get(kind) or wk.BANNER_POOL[i % len(wk.BANNER_POOL)]
            tb = round(s["start"] + .3, 3)
            bdur = round(min(1.9, s["end"] + .3 - tb), 3)
            if bn and bdur >= .9:
                te2 = round(tb + bdur - .5, 3)  # notification content leaves here; the island is back to music by the clip end
                clips.append(
                    f'<div id="bn{i}" class="clip" data-start="{tb}" data-duration="{bdur}" data-track-index="4" data-layout-allow-overlap data-layout-allow-occlusion style="left:260px;top:44px;width:560px;height:96px">'
                    f'<div id="bnc{i}" class="nc"><div class="ico" style="background:{bn.get("icon", "#34c759")}">{_glyph(bn)}</div>'
                    f'<div class="itxt"><b>{_esc(bn.get("app", ""), 18)}</b><span>{_esc(bn.get("text", ""), 36)}</span></div><span class="now">сейчас</span></div></div>')
                js.append(f'tl.fromTo("#isc",{{opacity:1}},{{opacity:0,duration:.15,ease:"none",immediateRender:false}},{tb});')
                js.append(f'tl.fromTo("#bnc{i}",{{opacity:0}},{{opacity:1,duration:.2,ease:"none"}},{round(tb + .3, 3)});')
                js.append(f'tl.fromTo("#bnc{i}",{{opacity:1}},{{opacity:0,duration:.15,ease:"none",immediateRender:false}},{te2});')
                js.append(f'tl.fromTo("#isc",{{opacity:0}},{{opacity:1,duration:.2,ease:"none",immediateRender:false}},{round(te2 + .3, 3)});')
                js.append(f'tl.fromTo("#card{i}",{{x:-7}},{{x:7,duration:.045,repeat:7,yoyo:true,ease:"none",immediateRender:false}},{round(tb + .3, 3)});')
                js.append(f'tl.to("#card{i}",{{x:0,duration:.06}},{round(tb + .68, 3)});')
        prev = kind
        for q in range(8):  # confetti burst at widget start
            ang = q / 8 * 6.283 + (i % 3) * .3
            clips.append(f'<svg id="bs{i}_{q}" class="sp" style="left:{520 + int(40 * math.cos(ang))}px;top:{460 + int(40 * math.sin(ang))}px;width:30px;height:30px;opacity:0" viewBox="0 0 10 10">'
                         f'<path d="M5 1v8M1 5h8" stroke="{cols[q % 5]}" stroke-width="2" stroke-linecap="round"/></svg>')
            js.append(f'tl.fromTo("#bs{i}_{q}",{{opacity:.9,x:0,y:0,rotation:0}},{{opacity:0,x:{int(330 * math.cos(ang))},y:{int(300 * math.sin(ang))},rotation:{90 + q * 20},duration:.8,ease:"power2.out",immediateRender:false}},{s["start"] + .1:.3f});')
    clips.extend(couriers)
    hook_d = round(min(dur, max(intro, 1.0) + .9), 3)
    clips.append(
        f'<div id="clipHook" class="clip" data-start="0" data-duration="{hook_d}" data-track-index="5" style="left:60px;top:60px;width:960px;height:300px;z-index:60">'
        f'<div id="hook" class="hook" style="font-size:{hfs}px">{hook}</div></div>')
    js.append(f'tl.fromTo("#hook",{{opacity:0,scale:1.3}},{{opacity:1,scale:1,duration:.4,ease:"back.out(1.7)",transformOrigin:"50% 50%"}},0);')
    js.append(f'tl.to("#hook",{{opacity:0,scale:.95,duration:.25,ease:"power2.in"}},{round(hook_d - .27, 3)});')
    hook_html = clips.pop()  # the hook lives in the top black bar, outside the stage
    return f"""<!doctype html>
<html lang="ru"><head><meta charset="utf-8"><meta name="viewport" content="width={w}, height={hgt}">
<script src="https://cdn.jsdelivr.net/npm/gsap@3.12.5/dist/gsap.min.js"></script>
<style>
html,body{{margin:0;background:#000;}}
#root{{position:relative;width:{w}px;height:{hgt}px;overflow:hidden;font-family:'Montserrat',sans-serif;background:#000;}}
#stage{{position:absolute;left:0;top:{OY}px;width:{w}px;height:{SQ}px;background:linear-gradient(160deg,{b1},{b2} 55%,{b3});}}
.bar{{position:absolute;left:0;width:{w}px;background:#000;z-index:50}}
.hook{{width:960px;height:300px;display:flex;align-items:center;justify-content:center;text-align:center;color:#fff;font-weight:900;line-height:1.08;
 overflow-wrap:anywhere;text-shadow:0 0 18px #ff3d9a,0 0 46px #ff3d9a}}
.sp{{position:absolute;opacity:.7}}
.cr{{position:absolute;left:0;top:0;width:56px;height:56px;border-radius:28px;opacity:0;z-index:5}}
.clip{{position:absolute}}
.icredit{{text-align:center;font-weight:900;font-size:58px;color:{INK}}}
.isub{{text-align:center;font-weight:700;font-size:40px;color:#7a7592}}
.fbig{{text-align:center;font-weight:900;font-size:88px;line-height:1.05;letter-spacing:-1px;color:{ta};text-shadow:0 6px 24px rgba(255,255,255,.8)}}
.stat{{position:absolute;font-weight:800;font-size:34px;color:{INK}}}
.batt{{position:absolute;width:62px;height:28px;box-sizing:border-box;border:3px solid {INK};border-radius:9px;overflow:hidden}}
.island{{position:absolute;left:260px;top:44px;width:560px;height:96px;border-radius:48px;background:#0b0b10;display:flex;align-items:center;gap:16px;padding:0 24px 0 20px;box-sizing:border-box}}
.ico{{width:60px;height:60px;border-radius:14px;background:#2a2a38;display:flex;align-items:center;justify-content:center;flex:none}}
.itxt{{display:flex;flex-direction:column;flex:1;min-width:0}}
.itxt b{{color:#fff;font-size:26px;white-space:nowrap}}
.itxt span{{color:#a4a4bb;font-size:21px;font-weight:600;white-space:nowrap}}
.now{{color:#7a7a92;font-size:18px;font-weight:600;flex:none}}
.eqs{{position:relative;width:44px;height:44px;flex:none}}
.eq{{position:absolute;bottom:0;width:8px;height:44px;border-radius:4px;background:{ta};transform-origin:50% 100%}}
.wcard{{position:absolute;left:0;top:0;width:900px;box-sizing:border-box;padding:30px 40px;border-radius:60px;background:rgba(255,255,255,.96);
 box-shadow:0 24px 60px rgba(90,70,160,.22);display:flex;flex-direction:column}}
.head{{display:flex;align-items:center;gap:18px;height:64px}}
.app{{width:56px;height:56px;border-radius:16px;display:inline-block;flex:none}}
.ht{{display:flex;flex-direction:column;line-height:1.1}}
.ht b{{font-size:36px;font-weight:800;color:{INK}}}
.ht em{{font-style:normal;font-size:22px;font-weight:700;color:#7a5cff}}
.lyric{{margin:6px 0 8px;height:128px;display:flex;align-items:center}}
.lt{{flex:1;font-weight:800;line-height:1.22;color:{GREY}}}
.lt .w{{display:inline-block;margin-right:12px}}
.body{{position:relative;width:820px;height:340px;border-radius:36px;overflow:hidden}}
.cart{{width:330px;height:340px;display:block;border-radius:30px;overflow:hidden}}
.row{{display:flex;gap:30px;align-items:center;height:340px}}
.cc{{flex:1;display:flex;flex-direction:column;gap:10px;min-width:0}}
.clab{{font-size:30px;font-weight:700;color:#7a7592}}
.cnum{{position:relative;font-weight:900;color:{INK};line-height:1;white-space:nowrap}}
.cnum small{{font-size:30px;font-weight:800;color:#8a6bff;margin-left:8px}}
.inf{{position:absolute;left:0;top:0;opacity:0}}
.cbar{{height:14px;border-radius:7px;background:rgba(20,20,31,.1);overflow:hidden}}
.cbar i{{display:block;height:14px;border-radius:7px;background:linear-gradient(90deg,{ta},{tb})}}
.pbtn{{align-self:flex-start;margin-top:12px;padding:14px 28px;border-radius:30px;background:#ff4f3d;color:#fff;font-size:30px;font-weight:800;white-space:nowrap}}
.srch{{display:flex;align-items:center;gap:16px;height:90px;border:4px solid {acc};border-radius:45px;padding:0 30px;font-size:40px;font-weight:700;color:{INK};box-sizing:border-box}}
.mag{{width:26px;height:26px;border:5px solid #9a8fb5;border-radius:50%;flex:none;box-sizing:border-box}}
.caret{{width:3px;height:44px;background:{acc};display:block}}
.rbig{{margin-top:44px;text-align:center;font-size:96px;font-weight:900;line-height:1;background:linear-gradient(90deg,{ta},{tb});-webkit-background-clip:text;background-clip:text;color:transparent}}
.rsub{{margin-top:16px;text-align:center;font-size:36px;font-weight:700;color:#9a8fb5}}
.sc{{position:relative;width:820px;height:340px}}
.sbig{{position:absolute;left:30px;top:20px;font-size:84px;font-weight:900;color:#fff;text-shadow:0 4px 18px rgba(0,0,0,.35)}}
.emb{{position:absolute;left:310px;top:50px;width:200px;height:200px}}
.spill{{position:absolute;left:50%;bottom:22px;margin-left:-190px;width:380px;height:64px;border-radius:32px;background:#fff;display:flex;align-items:center;justify-content:center;gap:12px;font-size:30px;font-weight:800;color:{INK};white-space:nowrap}}
.spill i{{width:14px;height:14px;border-radius:7px;background:#ff4f6d;display:block}}
.chat{{display:flex;flex-direction:column;gap:20px;justify-content:center;height:340px}}
.bub{{max-width:640px;padding:22px 32px;border-radius:38px;font-size:38px;font-weight:700;line-height:1.2}}
.bub.her{{align-self:flex-start;background:#eceaf6;color:{INK};border-bottom-left-radius:10px}}
.bub.me{{align-self:flex-end;background:linear-gradient(135deg,{ta},{tb});color:#fff;border-bottom-right-radius:10px}}
.dgrid{{width:820px;height:176px;display:block}}
.chosen{{position:absolute;left:350px;top:28px;width:120px;height:120px;border-radius:60px;background:#ff6b9d;color:#fff;font-size:36px;font-weight:900;display:flex;align-items:center;justify-content:center;opacity:0}}
.dlab{{text-align:center;font-size:28px;font-weight:700;color:#7a7592;margin-top:2px}}
.dnum{{text-align:center;font-size:72px;font-weight:900;color:{INK};line-height:1.05}}
.dsub{{text-align:center;font-size:28px;font-weight:700;color:#9a8fb5}}
.dots{{position:absolute;left:0;width:900px;display:flex;justify-content:center;gap:14px}}
.dot{{width:14px;height:14px;border-radius:7px;background:#b9b4d6;display:block}}
.dot.on{{width:34px;background:{INK}}}
.chip{{position:absolute;left:370px;top:825px;width:340px;height:56px;border-radius:28px;background:rgba(255,255,255,.92);
 display:flex;align-items:center;justify-content:center;gap:12px;font-size:28px;font-weight:800;color:{INK};box-shadow:0 8px 24px rgba(90,70,160,.15)}}
.chip i{{width:30px;height:30px;border-radius:15px;background:conic-gradient({ta},{tb},{ta});display:block}}
.ptitle{{position:absolute;left:60px;top:893px;width:960px;text-align:center;white-space:nowrap;font-weight:800;font-size:44px;color:{INK}}}
.track{{position:absolute;left:160px;top:986px;width:760px;height:8px;border-radius:4px;background:rgba(20,20,31,.15)}}
.thumb{{position:absolute;left:150px;top:980px;width:20px;height:20px;border-radius:10px;background:#fff;box-shadow:0 2px 8px rgba(40,30,80,.3)}}
#fill{{height:8px;border-radius:4px;background:linear-gradient(90deg,{ta},{tb})}}
.tm{{position:absolute;top:1004px;font-size:26px;font-weight:700;color:#6b6585}}
.isc{{display:flex;align-items:center;gap:16px;flex:1;min-width:0;height:100%}}
.nc{{position:absolute;left:0;top:0;width:560px;height:96px;display:flex;align-items:center;gap:16px;padding:0 24px 0 20px;box-sizing:border-box;opacity:0}}
.banner{{width:920px;height:112px;box-sizing:border-box;border-radius:56px;background:rgba(20,20,31,.95);display:flex;align-items:center;gap:20px;padding:0 34px 0 22px;box-shadow:0 18px 44px rgba(20,20,40,.4)}}
.banner .ico{{width:72px;height:72px;border-radius:18px}}
.banner .itxt b{{font-size:30px}}
.banner .itxt span{{font-size:25px}}
.shn{{position:absolute;inset:0;border-radius:60px;overflow:hidden;pointer-events:none}}
.shn i{{position:absolute;top:-50px;left:-260px;width:160px;height:760px;background:linear-gradient(90deg,rgba(255,255,255,0),rgba(190,170,255,.35),rgba(255,255,255,0));transform:skewX(-20deg)}}
.batt i{{display:block;height:100%;width:70%;background:{INK}}}
</style></head>
<body>
<div id="root" data-composition-id="main" data-start="0" data-duration="{dur}" data-width="{w}" data-height="{hgt}" data-fps="{fps}">
<div id="stage">
<div id="flash" style="position:absolute;inset:0;opacity:0;background:radial-gradient(circle at 50% 45%,rgba(255,255,255,.7),rgba(255,255,255,0) 65%)"></div>
<div id="bl1" style="position:absolute;left:-150px;top:-100px;width:700px;height:700px;border-radius:350px;background:radial-gradient(circle,rgba(255,150,190,.5),rgba(255,150,190,0) 70%)"></div>
<div id="bl2" style="position:absolute;left:520px;top:480px;width:700px;height:700px;border-radius:350px;background:radial-gradient(circle,rgba(150,170,255,.45),rgba(150,170,255,0) 70%)"></div>
{sparks}
{chr(10).join(clips)}
</div>
<div class="bar" style="top:0;height:{OY}px"></div><div class="bar" style="top:{OY + SQ}px;height:{hgt - OY - SQ}px"></div>
{hook_html}
</div>
<script>
window.__timelines = window.__timelines || {{}};
const tl = gsap.timeline({{paused:true}});
{chr(10).join(js)}
window.__timelines["main"] = tl;
</script>
</body></html>
"""
