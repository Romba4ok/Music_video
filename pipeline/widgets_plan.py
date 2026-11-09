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
KINDS = ("draw",) + wk.SCENE_KINDS  # draw = a picture Claude drew as SVG with tweens; the rest are the animated scenes
HOLD_MAX = 4.5  # s a card stays after its line ends when the vocal pauses (analysis refuses windows with a longer pause: whisper.max_gap_sec)
MAX_CARDS = 16

AUTO = [  # (stems, kind): meaning-by-keyword choice for a line that has no (usable) widget; first unused match wins
    (("дожд", "слез", "плак", "солнц", "свет", "радост", "грусть", "печал", "холод"), "weather"),
    (("звон", "телефон", "сообщ", "написал", "ответ", "молч", "жду", "ждал", "трубк"), "typing"),
    (("весн", "начал", "рост", "расти", "надежд", "цвет", "утр", "рассвет", "лучик"), "bloom"),
    (("вместе", "двое", "рядом", "тобой", "мы ", "люблю", "любим", "любов"), "duo"),
    (("дыш", "вдох", "выдох", "сердц", "волн", "дрож"), "breath"),
    (("тон", "вод", "глубин", "море", "утону", "падаю", "дно"), "deep"),
    (("откр", "свобод", "замок", "тайн", "секрет", "не бо", "храбр", "решил"), "unlock"),
    (("ноч", "сон", "звезд", "мечт", "темн", "луна", "небо", "грёз", "грез"), "night"),
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


def _auto(text, prev, count=None, seed=0):
    """A scene kind for a line without a usable widget: the first keyword match that is not the previous card and not used twice yet; with no
    match the scenes rotate by `seed`, so different videos (and different lines) do not all land on the same picture."""
    t, count = text.lower(), count or {}
    hit = [k for stems, k in AUTO if k != prev and count.get(k, 0) < 2 and any(x in t for x in stems)]
    if hit:
        return hit[0]
    pool = [k for k in wk.SCENE_KINDS if k != prev and count.get(k, 0) == 0] or [k for k in wk.SCENE_KINDS if k != prev]
    return pool[seed % len(pool)]


def _glyph(bn):
    a = (str(bn.get("app", "")) + str(bn.get("glyph", ""))).lower()
    return ("bubble" if any(x in a for x in ("сообщ", "чат", "бесед")) else "heart" if any(x in a for x in ("здоров", "пульс", "фото", "любов"))
            else "pin" if "карт" in a else "lines" if any(x in a for x in ("журнал", "напомин", "заметк", "новост", "выбор")) else "bell")


def _draw(w, i):
    """(widget for the renderer, ok). A drawn picture is re-cleaned here; an unusable one is replaced by a scene picked by meaning."""
    svg = svg_safe.clean(w.get("svg"), 9000, ids=isinstance(w.get("tw"), list))
    if not svg:
        return {k: v for k, v in w.items() if k not in ("svg", "tw")}, False
    scoped = svg_safe.scope(svg, i)
    out = {k: v for k, v in w.items() if k not in ("svg", "tw", "frames")}
    out["frames"] = [scoped]  # the renderer draws one picture; the list form is kept for its layer group
    tw = svg_safe.clean_tweens(w["tw"], set(re.findall(rf'id="dr{i}_([\w-]+)"', scoped))) if isinstance(w.get("tw"), list) else []
    out["anim"] = len(tw) >= 2
    if out["anim"]:
        out["tw"] = tw
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
    kind_count, prev, out = {}, "", []
    for k, s in enumerate(raw):
        nxt = raw[k + 1]["start"] if k + 1 < len(raw) else s["end"]
        end = max(s["end"], min(nxt, s["end"] + HOLD_MAX, dur))  # hold the card through vocal gaps: never an empty stage
        if end - s["start"] <= 0:
            continue
        i = len(out)
        if s["role"] == "outro":
            out.append({"i": i, "role": "outro", "start": s["start"], "end": end, "text": "", "kind": "draw", "w": {}, "app": "", "icon": "#000000", "cat": "", "notify": None})
            prev = "outro"
            continue
        wd = dict(s.get("widget") or {})
        kind = wd.get("kind") if wd.get("kind") in KINDS else None
        if kind == "draw":
            wd, ok = _draw(wd, i)
            kind = "draw" if ok else None
        if kind is None:  # no widget, a retired kind from an old spec, or an unusable drawing: a scene by meaning
            wd = {k2: v for k2, v in wd.items() if k2 in ("cap", "notify", "toast", "label", "who", "status", "err", "app", "cat", "icon")}
            kind = _auto(s["text"], prev, kind_count, seed + i)
        kind_count[kind] = kind_count.get(kind, 0) + 1
        dapp, dicon, dcat = wk.DEFAULT_APP[kind]
        if "notify" in wd:
            bn = wd["notify"]
        elif "toast" in wd:
            bn = wd["toast"]
        else:
            bn = wk.BANNER_POOL[i % len(wk.BANNER_POOL)]
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
