"""Extra widget bodies (820x340) for the "widgets" template, modelled on the animated cards of popular widget-edit videos:
pair, pulse, route, venn, ring, thermo, alert, target, polaroid. Each function returns (html, js); times in js are absolute seconds,
`at(f)` maps a fraction of the scene to an absolute time. All art is own SVG/CSS. Text fits by construction (_esc truncates)."""
import html

HEART = "M12 21.35l-1.45-1.32C5.4 15.36 2 12.28 2 8.5 2 5.42 4.42 3 7.5 3c1.74 0 3.41.81 4.5 2.09C13.09 3.81 14.76 3 16.5 3 19.58 3 22 5.42 22 8.5c0 3.78-3.4 6.86-8.55 11.54L12 21.35z"
NEW_KINDS = ("pair", "pulse", "route", "venn", "ring", "thermo", "alert", "target", "polaroid")
# kind -> (app title, icon colour, category line under the title)
DEFAULT_APP = {
    "pair": ("Двое", "#ff9a6b", "контакты"), "pulse": ("Пульс", "#ff4f6d", "здоровье"), "route": ("Карты", "#2fb86b", "маршрут"),
    "venn": ("Вместе", "#ff4f8b", "общий альбом"), "ring": ("Настроение", "#ffb020", "сегодня"),
    "thermo": ("Здоровье", "#ff4f6d", "температура"), "alert": ("Оповещение", "#ff3b3b", "срочное"),
    "target": ("Прицел", "#14141f", "цель найдена"), "versus": ("Ожидание", "#8a6bff", "сравнение"), "draw": ("Заметки", "#ffb020", "набросок"), "polaroid": ("Фото", "#ff7a3d", "воспоминание"),
}
# island notification shown with the card unless the widget sets "notify": false
DEFAULT_NOTIFY = {
    "route": {"app": "Карты", "text": "Маршрут построен", "icon": "#2fb86b"},
    "thermo": {"app": "Здоровье", "text": "Температура выше нормы", "icon": "#ff4f6d"},
    "alert": {"app": "Оповещение", "text": "Срочно", "icon": "#ff3b3b"},
    "target": {"app": "Прицел", "text": "Цель найдена", "icon": "#14141f"},
}

# small pop-up banner (toast) that flies over the card mid-way, unless the widget sets "toast": false. Generic UI flavour, no facts.
DEFAULT_TOAST = {
    "pair": {"app": "Сообщения", "text": "Новое сообщение", "icon": "#34c759"},
    "pulse": {"app": "Здоровье", "text": "Пульс выше нормы", "icon": "#ff4f6d"},
    "venn": {"app": "Фото", "text": "Общий альбом обновлён", "icon": "#ff4f8b"},
    "ring": {"app": "Настроение", "text": "Уровень растёт", "icon": "#ffb020"},
    "polaroid": {"app": "Фото", "text": "Воспоминание дня", "icon": "#ff7a3d"},
    "versus": {"app": "Напоминание", "text": "Выбор ещё не сделан", "icon": "#8a6bff"},
    "counter": {"app": "Банк", "text": "Баланс изменился", "icon": "#2fb86b"},
    "search": {"app": "Подсказка", "text": "Ответов не найдено", "icon": "#8a6bff"},
}

# generic phone-banner texts used when a card has no specific one (UI flavour only, never facts about the song)
BANNER_POOL = [
    {"app": "Сообщения", "text": "Новое сообщение", "icon": "#34c759"},
    {"app": "Напоминание", "text": "Не забудь послушать до конца", "icon": "#ff9f1a"},
    {"app": "Музыка", "text": "Сейчас играет", "icon": "#ff4f6d"},
    {"app": "Новости", "text": "Есть обновление", "icon": "#3b82f6"},
]


def esc(t, n):
    s = str(t)
    return html.escape(s if len(s) <= n else s[:n - 1].rstrip() + "…")


def _t(x):
    return round(float(x), 3)


def _num(v, default):
    try:
        return float(v)
    except (TypeError, ValueError):
        return float(default)


def _count(i, tag, a, b, t0, dur, fmt, ease="power2.out"):
    """tween a number and write it into #<tag>n<i>; fmt is a JS expression with V standing for the value."""
    v = f"{tag}v{i}"
    return (f'const {v}={{v:{a}}};tl.to({v},{{v:{b},duration:{_t(dur)},ease:"{ease}",onUpdate(){{'
            f'document.getElementById("{tag}n{i}").textContent={fmt.replace("V", v + ".v")};}}}},{_t(t0)});')


def _wrap(inner, label=""):
    lab = (f'<div style="position:absolute;left:0;top:296px;width:820px;text-align:center;font-weight:700;font-size:30px;color:#7a7592">{esc(label, 36)}</div>'
           if label else "")
    return f'<div style="position:relative;width:820px;height:340px">{inner}{lab}</div>'


def _heart(x, y, k, col="#ff4f6d"):
    return f'<g transform="translate({x} {y}) scale({k})"><path d="{HEART}" fill="{col}"/></g>'


def pair(w, i, s, d, at):
    a, b = esc(w.get("a", "Я"), 5), esc(w.get("b", "Ты"), 5)
    h = (f'<svg viewBox="0 0 820 340" style="position:absolute;left:0;top:0;width:820px;height:340px"><defs>'
         f'<radialGradient id="pa{i}"><stop offset="0" stop-color="#ffc79a"/><stop offset="1" stop-color="#ff7a3d"/></radialGradient>'
         f'<radialGradient id="pb{i}"><stop offset="0" stop-color="#ffa6c4"/><stop offset="1" stop-color="#ff4f8b"/></radialGradient></defs>'
         f'<path d="M262 150H558" stroke="#8a6bff" stroke-width="6" stroke-dasharray="2 16" stroke-linecap="round" fill="none"/>'
         f'<g id="pA{i}" style="transform-origin:150px 150px"><circle cx="150" cy="150" r="100" fill="url(#pa{i})"/>'
         f'<text x="150" y="176" text-anchor="middle" font-size="76" font-weight="900" fill="#14141f">{a}</text></g>'
         f'<g id="pB{i}" style="transform-origin:670px 150px"><circle cx="670" cy="150" r="100" fill="url(#pb{i})"/>'
         f'<text x="670" y="176" text-anchor="middle" font-size="76" font-weight="900" fill="#14141f">{b}</text></g>'
         f'<g id="pH{i}">{_heart(264, 124, 2.2)}</g></svg>')
    j = [f'tl.fromTo("#pA{i}",{{opacity:.4,scale:.88}},{{opacity:1,scale:1.05,duration:.35,ease:"back.out(2)"}},{_t(at(.1))});',
         f'tl.fromTo("#pH{i}",{{opacity:0,x:0}},{{opacity:1,x:240,duration:{_t(d * .38)},ease:"power1.inOut"}},{_t(at(.3))});',
         f'tl.fromTo("#pB{i}",{{opacity:.4,scale:.88}},{{opacity:1,scale:1.05,duration:.35,ease:"back.out(2)"}},{_t(at(.7))});']
    return _wrap(h, w.get("label", "")), j


def pulse(w, i, s, d, at):
    a, b = _num(w.get("from"), 70), _num(w.get("to"), 130)
    ecg = "M0 250H150L185 250L215 215L250 285L285 228L310 250H470L505 250L535 215L570 285L605 228L630 250H820"
    h = (f'<svg viewBox="0 0 820 340" style="position:absolute;left:0;top:0;width:820px;height:340px">'
         f'<path id="pe{i}" d="{ecg}" pathLength="1" stroke="#ff4f6d" stroke-width="9" fill="none" stroke-linecap="round" stroke-linejoin="round" '
         f'stroke-dasharray="1" stroke-dashoffset="1"/>'
         f'<g id="pb{i}" style="transform-origin:190px 110px">{_heart(106, 26, 7)}</g></svg>'
         f'<div id="pn{i}" style="position:absolute;left:420px;top:26px;font-size:140px;font-weight:900;line-height:1;color:#14141f">{int(a)}</div>'
         f'<div style="position:absolute;left:428px;top:176px;font-size:34px;font-weight:800;color:#8a6bff">{esc(w.get("unit", "уд/мин"), 8)}</div>')
    j = [f'tl.fromTo("#pe{i}",{{strokeDashoffset:1}},{{strokeDashoffset:0,duration:{_t(d * .6)},ease:"none"}},{_t(s + .05)});',
         f'tl.fromTo("#pb{i}",{{scale:1}},{{scale:1.16,duration:.2,yoyo:true,repeat:{max(1, int(d / .4))},ease:"sine.inOut"}},{_t(s)});',
         _count(i, "p", int(a), int(b), s, d * .85, "Math.round(V)")]
    return _wrap(h, w.get("label", "")), j


def route(w, i, s, d, at):
    A, B = esc(w.get("from", "Старт"), 12), esc(w.get("to", "Цель"), 12)
    wa, wb = 34 + 17 * len(A), 34 + 17 * len(B)

    def pin(x, y, col, tag):
        return (f'<g id="{tag}{i}"><g transform="translate({x} {y})"><path d="M0 0C-28 -36 -28 -76 0 -76C28 -76 28 -36 0 0Z" fill="{col}"/>'
                f'<circle cx="0" cy="-50" r="11" fill="#fff"/></g></g>')

    def lab(x, y, wd, txt, tag):
        return (f'<g id="{tag}{i}"><rect x="{x - wd // 2}" y="{y}" width="{wd}" height="46" rx="23" fill="#fff" stroke="#dcd8ee" stroke-width="2"/>'
                f'<text x="{x}" y="{y + 32}" text-anchor="middle" font-size="26" font-weight="800" fill="#14141f">{txt}</text></g>')
    h = (f'<svg viewBox="0 0 820 340" style="position:absolute;left:0;top:0;width:820px;height:340px">'
         f'<rect width="820" height="340" fill="#e8eefc"/><path d="M0 225C200 180 400 265 820 190" stroke="#bcd4f5" stroke-width="46" fill="none"/>'
         f'<rect x="470" y="232" width="150" height="80" rx="22" fill="#cdecd0"/>'
         + "".join(f'<path d="{p}" stroke="#fff" stroke-width="10"/>' for p in ("M0 96H820", "M0 312H820", "M205 0V340", "M565 0V340"))
         + f'<path id="rt{i}" d="M130 252C250 252 300 130 440 150S600 122 660 112" pathLength="1" stroke="#3b82f6" stroke-width="13" fill="none" '
           f'stroke-linecap="round" stroke-dasharray="1" stroke-dashoffset="1"/>'
         + pin(130, 252, "#ff4f6d", "pa") + lab(130, 128, wa, A, "la") + pin(660, 112, "#ff8a2d", "pb") + lab(660, 128, wb, B, "lb") + '</svg>')
    j = [f'tl.fromTo("#pa{i}",{{opacity:0,y:-60}},{{opacity:1,y:0,duration:.45,ease:"bounce.out"}},{_t(s + .05)});',
         f'tl.fromTo("#la{i}",{{opacity:0,y:10}},{{opacity:1,y:0,duration:.3}},{_t(s + .2)});',
         f'tl.fromTo("#rt{i}",{{strokeDashoffset:1}},{{strokeDashoffset:0,duration:{_t(d * .5)},ease:"power1.inOut"}},{_t(at(.12))});',
         f'tl.fromTo("#pb{i}",{{opacity:0,y:-60}},{{opacity:1,y:0,duration:.45,ease:"bounce.out"}},{_t(at(.62))});',
         f'tl.fromTo("#lb{i}",{{opacity:0,y:10}},{{opacity:1,y:0,duration:.3}},{_t(at(.7))});']
    return f'<div style="position:relative;width:820px;height:340px">{h}</div>', j


def venn(w, i, s, d, at):
    a, b = int(_num(w.get("from"), 1)), int(_num(w.get("to"), 3))
    h = (f'<svg viewBox="0 0 820 340" style="position:absolute;left:0;top:0;width:820px;height:340px">'
         f'<g id="vA{i}"><circle cx="230" cy="170" r="120" fill="#ff9a6b" opacity=".92"/></g>'
         f'<g id="vB{i}"><circle cx="590" cy="170" r="120" fill="#ff4f8b" opacity=".82"/></g>'
         f'<g id="vH{i}" style="transform-origin:410px 170px">{_heart(366, 126, 3.7, "#fff")}</g></svg>'
         f'<div id="vn{i}" style="position:absolute;right:24px;top:10px;font-size:64px;font-weight:900;color:#ff4f6d;line-height:1">×{a}</div>')
    j = [f'tl.fromTo("#vA{i}",{{x:0}},{{x:{int(w.get("shift", 110))},duration:{_t(d * .5)},ease:"power2.inOut"}},{_t(s + .15)});',
         f'tl.fromTo("#vB{i}",{{x:0}},{{x:-{int(w.get("shift", 110))},duration:{_t(d * .5)},ease:"power2.inOut"}},{_t(s + .15)});',
         f'tl.fromTo("#vH{i}",{{opacity:0,scale:.3}},{{opacity:1,scale:1,duration:.4,ease:"back.out(2.2)"}},{_t(at(.62))});',
         _count(i, "v", a, b, at(.5), d * .35, '"×"+Math.round(V)', "none")]
    return _wrap(h, w.get("label", "")), j


def ring(w, i, s, d, at):
    a, b = _num(w.get("from"), 0), _num(w.get("to"), 100)
    h = (f'<svg viewBox="0 0 820 340" style="position:absolute;left:0;top:0;width:820px;height:340px">'
         f'<g transform="rotate(-90 410 150)"><circle cx="410" cy="150" r="115" pathLength="100" fill="none" stroke="#f1e6d6" stroke-width="30"/>'
         f'<circle id="rg{i}" cx="410" cy="150" r="115" pathLength="100" fill="none" stroke="#ff9f1a" stroke-width="30" stroke-linecap="round" '
         f'stroke-dasharray="100" stroke-dashoffset="{100 - a:g}"/></g></svg>'
         f'<div id="rn{i}" style="position:absolute;left:0;top:96px;width:820px;text-align:center;font-size:84px;font-weight:900;line-height:1;color:#14141f">{int(a)}%</div>')
    j = [f'tl.fromTo("#rg{i}",{{strokeDashoffset:{100 - a:g}}},{{strokeDashoffset:{100 - b:g},duration:{_t(d * .7)},ease:"power2.out"}},{_t(s + .1)});',
         _count(i, "r", int(a), int(b), s + .1, d * .7, 'Math.round(V)+"%"')]
    return _wrap(h, w.get("label", "")), j


def thermo(w, i, s, d, at):
    a, b = _num(w.get("from"), 36.6), _num(w.get("to"), 38.9)
    h = (f'<svg viewBox="0 0 820 340" style="position:absolute;left:0;top:0;width:820px;height:340px">'
         f'<rect x="212" y="18" width="58" height="236" rx="29" fill="#ece6f7"/><circle cx="241" cy="272" r="44" fill="#ff4f6d"/>'
         f'<rect id="tm{i}" x="223" y="52" width="36" height="220" rx="18" fill="#ff4f6d" style="transform-origin:241px 270px"/>'
         + "".join(f'<path d="M{440 + k * 52} 270v22M{429 + k * 52} 281h22" stroke="#4a8bff" stroke-width="5" stroke-linecap="round"/>' for k in range(4))
         + f'</svg><div style="position:absolute;left:330px;top:70px;font-size:132px;font-weight:900;line-height:1;color:#14141f">'
           f'<span id="tn{i}">{a:.1f}</span><small style="font-size:60px;color:#ff4f6d">{esc(w.get("unit", "°"), 3)}</small></div>')
    j = [f'tl.fromTo("#tm{i}",{{scaleY:.25}},{{scaleY:1,duration:{_t(d * .7)},ease:"power2.out"}},{_t(s + .1)});',
         _count(i, "t", a, b, s + .1, d * .7, "V.toFixed(1)")]
    return _wrap(h, w.get("label", "")), j


def alert(w, i, s, d, at):
    word = esc(w.get("word", "ОПАСНО").upper(), 14)
    h = (f'<div id="aw{i}" style="position:absolute;left:0;top:10px;width:820px;text-align:center;font-size:68px;font-weight:900;line-height:1.1;color:#ff3b3b">{word}</div>'
         f'<svg viewBox="0 0 820 340" style="position:absolute;left:0;top:0;width:820px;height:340px">'
         f'<circle id="ag{i}" cx="410" cy="200" r="90" fill="#ff4f3d" opacity=".16"/>'
         f'<g id="at{i}" style="transform-origin:410px 200px"><path d="M410 118L486 244H334Z" fill="#ff4f3d" stroke="#ff4f3d" stroke-width="16" stroke-linejoin="round"/>'
         f'<text x="410" y="230" text-anchor="middle" font-size="80" font-weight="900" fill="#fff">!</text></g></svg>'
         f'<div style="position:absolute;left:0;top:284px;width:820px;height:36px;border-radius:18px;'
         f'background:repeating-linear-gradient(-45deg,#14141f 0 18px,#ffd400 18px 36px)"></div>')
    j = [f'tl.fromTo("#aw{i}",{{opacity:0,scale:1.9,transformOrigin:"50% 50%"}},{{opacity:1,scale:1,duration:.4,ease:"back.out(2)"}},{_t(at(.25))});',
         f'tl.fromTo("#at{i}",{{x:-7}},{{x:7,duration:.07,yoyo:true,repeat:{max(3, int(d / .14))},ease:"none"}},{_t(s + .1)});',
         f'tl.fromTo("#ag{i}",{{scale:.8}},{{scale:1.6,duration:.5,yoyo:true,repeat:{max(1, int(d / .5))},ease:"sine.inOut",transformOrigin:"50% 50%"}},{_t(s)});']
    return f'<div style="position:relative;width:820px;height:340px">{h}</div>', j


def target(w, i, s, d, at):
    lab = esc(w.get("label", "ЦЕЛЬ НАЙДЕНА").upper(), 20)
    cross = "".join(f'<path d="{p}" stroke="#fff" stroke-width="6" stroke-linecap="round"/>' for p in ("M410 36V104", "M410 236V304", "M276 170H344", "M476 170H544"))
    h = (f'<div style="position:absolute;inset:0;background:#15111f"></div><div id="tr{i}" style="position:absolute;inset:0;background:#ff1744;opacity:0"></div>'
         f'<svg viewBox="0 0 820 340" style="position:absolute;left:0;top:0;width:820px;height:340px">'
         f'<g id="tc{i}" style="transform-origin:410px 170px"><circle cx="410" cy="170" r="96" fill="none" stroke="#fff" stroke-width="6"/>{cross}</g>'
         f'<g id="th{i}" style="transform-origin:410px 170px">{_heart(364, 124, 3.8)}</g></svg>'
         f'<div style="position:absolute;left:28px;bottom:22px;font-size:28px;font-weight:800;color:#fff;letter-spacing:1px">{lab}</div>')
    j = [f'tl.fromTo("#tc{i}",{{scale:2.4,rotation:120,opacity:0}},{{scale:1,rotation:0,opacity:1,duration:.55,ease:"power3.out"}},{_t(s + .1)});',
         f'tl.fromTo("#th{i}",{{scale:1}},{{scale:1.18,duration:.18,yoyo:true,repeat:{max(1, int(d / .36))},ease:"sine.inOut"}},{_t(s + .3)});',
         f'tl.fromTo("#tr{i}",{{opacity:0}},{{opacity:.4,duration:.4}},{_t(at(.6))});']
    return f'<div style="position:relative;width:820px;height:340px">{h}</div>', j


def polaroid(w, i, s, d, at):
    a, b = int(_num(w.get("from"), 2023)), int(_num(w.get("to"), 2026))
    h = (f'<svg viewBox="0 0 820 340" style="position:absolute;left:0;top:0;width:820px;height:340px">'
         f'<g id="pl{i}" style="transform-origin:165px 170px"><rect x="40" y="16" width="250" height="308" rx="16" fill="#fff" stroke="#e6e1f5" stroke-width="3"/>'
         f'<rect x="58" y="34" width="214" height="226" rx="9" fill="#2b2b4a"/><circle cx="165" cy="124" r="40" fill="#8c8cb8"/>'
         f'<path d="M92 260Q165 160 238 260Z" fill="#8c8cb8"/></g></svg>'
         f'<div id="yn{i}" style="position:absolute;left:360px;top:70px;font-size:124px;font-weight:900;line-height:1;color:#c2410c">{a}</div>'
         f'<div style="position:absolute;left:368px;top:206px;font-size:38px;font-weight:700;color:#7a7592">{esc(w.get("label", ""), 22)}</div>')
    j = [f'tl.fromTo("#pl{i}",{{rotation:-14,scale:.8,opacity:0}},{{rotation:-5,scale:1,opacity:1,duration:.5,ease:"back.out(1.6)"}},{_t(s + .05)});',
         _count(i, "y", a, b, s + .15, d * .7, "Math.round(V)", "power1.inOut")]
    return f'<div style="position:relative;width:820px;height:340px">{h}</div>', j


BUILD = {"pair": pair, "pulse": pulse, "route": route, "venn": venn, "ring": ring, "thermo": thermo, "alert": alert, "target": target, "polaroid": polaroid}
