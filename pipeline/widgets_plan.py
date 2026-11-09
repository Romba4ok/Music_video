"""Resolve the scenario (script_gen output + spec) into the props of the Remotion composition `Widgets` (remotion/src/widgets).

Pure function, no randomness beyond a per-song seed: kinds, default apps/icons/notifications and the keyword fallback are decided here;
the React side only draws. Drawn pictures (kind "draw") are re-cleaned here, so a hand-edited spec cannot bypass `svg_safe`.
"""
import re
import zlib

from . import svg_safe
from . import widget_kinds as wk

PAL = {  # spec palette -> (bg1, bg2, bg3, accent, title gradient a, b)
    "dusk": ("#ffe6f1", "#e9e2ff", "#dbeafe", "#6a5cff", "#ff4f8b", "#a47bff"),
    "cold": ("#e0f0ff", "#e3e8ff", "#f1e4ff", "#3b6cff", "#2f8bff", "#8a6bff"),
    "warm": ("#fff0e0", "#ffe3ec", "#f3e6ff", "#ff5a2d", "#ff7a3d", "#ff3d8b"),
    "contrast": ("#e0fff3", "#e0f0ff", "#efe6ff", "#14956f", "#1fb98a", "#3b8bff"),
}
DARK_BG = ("#15102b", "#241a4a", "#1a1540")
KINDS = ("scene", "counter", "search", "camera", "chat", "dots", "versus", "draw") + wk.NEW_KINDS  # draw = a picture Claude drew as SVG

# (art key, default app title, icon colour, stems that pick this art for a line)
ARTS = [
    ("sunset", "Закат", "#ff9a6b", ("закат", "солнц", "рассвет", "свет", "лучи")),
    ("map", "Локатор", "#3b8bff", ("дорог", "путь", "иду", "идти", "город", "домой", "улиц", "куда", "где")),
    ("pulse", "Пульс", "#ff4f6d", ("сердц", "любо", "люби", "боль", "чувств", "душ", "дыш")),
    ("clock", "Часы", "#8a6bff", ("врем", "час", "год", "день", "секунд", "вчера", "завтра", "когда", "жизн")),
    ("rain", "Погода", "#4a6a9a", ("дожд", "слез", "плак", "гроз", "холод", "ветер")),
    ("moon", "Ночь", "#3a3f8f", ("ноч", "звезд", "луна", "сон", "спа", "тьм", "темн", "один")),
    ("phone", "Звонки", "#34c759", ("звон", "телефон", "трубк", "номер", "сообщен", "смс", "написал", "позвон")),
    ("window", "Дом", "#ffb020", ("окн", "дома", "комнат", "квартир", "двер", "стен", "подъезд", "кухн", "одиноч")),
    ("flame", "Огонь", "#ff5a2d", ("огон", "горит", "горел", "пламя", "жар", "пепел", "сжег", "сожг", "дым")),
    ("lock", "Замок", "#5b5bd6", ("клетк", "замок", "тюрьм", "решетк", "решётк", "цепи", "свобод", "заперт", "плен")),
    ("bird", "Небо", "#2f8bff", ("неб", "птиц", "крыль", "высот", "вверх", "облак", "полет", "полёт", "лечу", "летать", "взлет")),
    ("wave", "Море", "#14b8a6", ("море", "моря", "морск", "волн", "океан", " вод", "тону", "берег", "корабл")),
]
ART_KEYS = [a[0] for a in ARTS] + ["eye", "city", "coins"]  # 15 pictures a scene card can show (the SVGs live in remotion/src/arts.generated.ts)
APP_ICON = {a[0]: a[2] for a in ARTS} | {"eye": "#2f8bff", "city": "#5b5bd6", "coins": "#ffb020"}
HOLD_MAX = 4.5  # s a card stays after its line ends when the vocal pauses (analysis refuses windows with a longer pause: whisper.max_gap_sec)
MAX_CARDS = 14

AUTO = [  # (stems, widget): meaning-by-keyword fallback when the spec has no hand-written widget for a line (first match wins)
    (("смерт", "убил", "оруж", "убий", "пуля", "кровь", "опасн"), {"kind": "alert", "word": "ОПАСНО"}),
    (("люб", "сердц"), {"kind": "pulse", "from": 72, "to": 128}),
    (("вместе", "двое", "рядом", "с тобой", "тобой", "мы "), {"kind": "pair", "a": "Я", "b": "Ты"}),
    (("год", "лет", "помн", "раньше", "прошл", "вчера"), {"kind": "polaroid", "from": 2019, "to": 2026, "label": "тогда и сейчас"}),
    (("холод", "боль", "болел", "болен", "мерз", "темпер"), {"kind": "thermo"}),
    (("путь", "дорог", "иду", "идти", "домой", "город", "шаг"), {"kind": "route", "from": "Откуда", "to": "Куда"}),
    (("цель", "стрел", "враг", "бой"), {"kind": "target"}),
    (("деньг", "бабк", "рубл", "тенге", "куш", "монет", "богат", "нищ"), {"kind": "counter", "art": "coins", "label": "баланс", "from": 1000, "to": 0, "unit": "₸"}),
    (("?", "почему", "зачем", "кто ", "как ", "что ж"), {"kind": "search"}),
    (("глаз", "смотр", "взгляд", "вижу", "видел", "видишь"), {"kind": "camera"}),
    ((" или ", "выбор", "либо", "решил"), {"kind": "versus"}),
    (("сказал", "говорил", "спросил", "ответ", "слов", "молч"), {"kind": "chat"}),
]
INK = "#14141f"
WORST_BG = "#feadbe"  # saturated pink: the brightest thing a title text can sit on (an accent orb over the card)


def _clip(text, n):
    return text if len(text) <= n else text[:n - 1].rstrip() + "…"


def _rgb(h):
    h = str(h).strip().lstrip("#")
    h = "".join(c * 2 for c in h) if len(h) == 3 else h
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4)) if len(h) == 6 and all(c in "0123456789abcdefABCDEF" for c in h) else None


def _lum(c):
    v = [x / 255 / 12.92 if x / 255 <= .03928 else ((x / 255 + .055) / 1.055) ** 2.4 for x in c]
    return .2126 * v[0] + .7152 * v[1] + .0722 * v[2]


def contrast(a, b):
    la, lb = _lum(_rgb(a)), _lum(_rgb(b))
    return (max(la, lb) + .05) / (min(la, lb) + .05)


def readable(col, bg=WORST_BG, need=3.1):
    """Same hue, darkened until it reads on `bg` with at least `need`:1. Unparseable -> INK."""
    c = _rgb(col)
    if c is None:
        return INK
    k = _rgb(INK)
    for step in range(21):
        h = "#%02x%02x%02x" % tuple(round(x + (y - x) * step / 20) for x, y in zip(c, k))
        if contrast(h, bg) >= need:
            return h
    return INK


def _pick(text, idx, used=(), seed=0):
    """Index into ARTS for a line: the first picture whose stems occur in the text and that this video has not shown yet; when all of
    those are taken (or none match) a fresh one is rotated in, so a video does not repeat a picture and different songs start elsewhere."""
    t = text.lower()
    fresh = [k for k, a in enumerate(ARTS) if a[0] not in used and any(x in t for x in a[3])]
    if fresh:
        return fresh[0]
    pool = [k for k, a in enumerate(ARTS) if a[0] not in used] or list(range(len(ARTS)))
    return pool[(seed + idx) % len(pool)]


def _auto(text, prev, count=None, seed=0):
    """Keyword fallback. A kind is skipped when it was the previous card or the video already used it twice; among the rest `alert` wins,
    otherwise `seed` rotates the choice so different videos (and different lines) do not all land on the same widget."""
    t, count = text.lower(), count or {}
    ok = [wd for stems, wd in AUTO if wd["kind"] != prev and count.get(wd["kind"], 0) < 2 and any(x in t for x in stems)]
    if not ok:
        return {}
    return dict(ok[0] if ok[0]["kind"] == "alert" else ok[seed % len(ok)])


def _glyph(bn):
    a = (str(bn.get("app", "")) + str(bn.get("glyph", ""))).lower()
    return ("bubble" if any(x in a for x in ("сообщ", "чат", "бесед")) else "heart" if any(x in a for x in ("здоров", "пульс", "фото", "любов"))
            else "pin" if "карт" in a else "lines" if any(x in a for x in ("журнал", "напомин", "заметк", "новост", "выбор")) else "bell")


def _draw(w, i):
    """(widget for the renderer, ok). A drawn picture is re-cleaned here; an unusable one falls back to a template picture."""
    anim = isinstance(w.get("tw"), list) and bool(w.get("svg"))  # one picture whose shapes are moved by tweens (not a slideshow of frames)
    frames = ([m for m in [svg_safe.clean(w.get("svg"), 9000, ids=True)] if m] if anim else
              [m for m in (svg_safe.clean(x) for x in (w.get("frames") or [])[:8]) if m][:5] or [m for m in [svg_safe.clean(w.get("svg"))] if m])
    if not frames:
        return {k: v for k, v in w.items() if k not in ("svg", "kind", "frames", "tw")}, False
    scoped = [svg_safe.scope(m, i if len(frames) == 1 else f"{i}f{k}") for k, m in enumerate(frames)]
    out = {k: v for k, v in w.items() if k not in ("svg", "tw", "frames")}
    out["frames"] = scoped
    out["anim"] = anim
    if anim:
        out["tw"] = svg_safe.clean_tweens(w["tw"], set(re.findall(rf'id="dr{i}_([\w-]+)"', scoped[0])))
    return out, True


def snap_to_beats(scenes, beats, tol):
    """A card that changes lands on the nearest beat when one is within `tol` seconds (the cut then feels like part of the music).
    Order and gaps are kept: a card never moves before the previous one has lived 0.5 s or past 0.3 s before its own end."""
    if not beats or tol <= 0:
        return scenes
    out = [dict(x) for x in scenes]
    for i in range(1, len(out)):
        s = out[i]
        if s["role"] == "outro":
            continue
        b = min(beats, key=lambda x: abs(x - s["start"]))
        if abs(b - s["start"]) <= tol and out[i - 1]["start"] + 0.5 < b < s["end"] - 0.3:
            s["start"] = round(b, 3)
            out[i - 1]["end"] = round(min(out[i - 1]["end"], b - 0.05), 3)
    return out


def resolve(plan, spec, cfg):
    """-> props dict for the Remotion `Widgets` composition (JSON-serialisable)."""
    dur = plan["duration"]
    b1, b2, b3, acc, ta, tb = PAL[spec["palette"]]
    dark = spec.get("theme") == "dark"  # night mood: dark glowing background, light text outside the (still white) cards
    song = spec["song"]
    artist, title = song.get("artist", ""), song["title"]
    handle = (cfg.get("handle") or "vybex").strip().lstrip("@")
    seed = zlib.crc32(f"{artist}{title}".encode("utf-8")) % 997  # per song: two songs do not pick the same pictures for the same kind of line
    raw = snap_to_beats(plan["scenes"], plan.get("beats", []), cfg.get("beat_snap_sec", 0.18))
    n_cards = min(MAX_CARDS, sum(1 for x in raw if x["role"] != "outro")) or 1
    art_index = {a[0]: n for n, a in enumerate(ARTS)}
    used_arts, kind_count, prev, out = [], {}, "", []
    for k, s in enumerate(raw):
        nxt = raw[k + 1]["start"] if k + 1 < len(raw) else s["end"]
        end = max(s["end"], min(nxt, s["end"] + HOLD_MAX, dur))  # hold the card through vocal gaps: never an empty stage
        if end - s["start"] <= 0:
            continue
        i = len(out)
        if s["role"] == "outro":
            out.append({"i": i, "role": "outro", "start": s["start"], "end": end, "text": "", "kind": "scene", "w": {}, "app": "", "icon": "#000000", "cat": "", "notify": None})
            prev = "outro"
            continue
        wd = dict(s.get("widget") or _auto(s["text"], prev, kind_count, seed + i))
        kind = wd.get("kind") if wd.get("kind") in KINDS else "scene"
        a = art_index.get(wd.get("art"))
        if a is None:
            a = _pick(s["text"], i, used_arts, seed)
        if kind == "draw":
            wd, ok = _draw(wd, i)
            if not ok:
                kind = "scene"  # unusable drawing -> a template picture, the video still renders
        if kind == "scene" and wd.get("art") not in ART_KEYS:
            wd["art"] = ARTS[a][0]
        kind_count[kind] = kind_count.get(kind, 0) + 1
        if wd.get("art") in ART_KEYS:
            used_arts.append(wd["art"])
        dapp, dicon, dcat = wk.DEFAULT_APP.get(kind, (ARTS[a][1], APP_ICON.get(wd.get("art"), ARTS[a][2]), ""))
        if "notify" in wd:
            bn = wd["notify"]
        elif kind in wk.DEFAULT_NOTIFY:
            bn = wk.DEFAULT_NOTIFY[kind]
        elif "toast" in wd:
            bn = wd["toast"]
        else:
            bn = wk.DEFAULT_TOAST.get(kind) or wk.BANNER_POOL[i % len(wk.BANNER_POOL)]
        notify = {"app": str(bn.get("app", "")), "text": str(bn.get("text", "")), "icon": str(bn.get("icon", "#34c759")), "glyph": _glyph(bn)} if isinstance(bn, dict) and bn else None
        out.append({"i": i, "role": "lyric", "start": s["start"], "end": end, "text": _clip(s["text"], 100), "kind": kind, "w": wd,
                    "app": wd.get("app") or dapp, "icon": wd.get("icon") or dicon, "cat": wd.get("cat", dcat), "notify": notify})
        prev = kind
    ost = next((x["start"] for x in out if x["role"] == "outro"), dur)
    hook = _clip(str(spec.get("hook") or "О чём эта строка?").upper(), 36)
    return {
        "fps": cfg["fps"], "width": cfg["width"], "height": cfg["height"], "duration": dur, "dark": dark, "alternate": bool(cfg.get("alternate_theme")),
        "pal": {"b": list(DARK_BG if dark else (b1, b2, b3)), "alt": list((b1, b2, b3) if dark else DARK_BG), "acc": acc, "ta": ta, "tb": tb, "taReadable": readable(ta)},
        "artist": artist, "title": title, "credit": f"автор: {handle}", "series": str(cfg.get("series", ""))[:24], "hook": hook, "hookD": round(min(dur, 1.9), 3), "ostart": ost, "nCards": n_cards,
        "hasCap": any((x["w"] or {}).get("cap") for x in out if x["role"] != "outro"), "scenes": out,
    }
