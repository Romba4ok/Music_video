"""Claude draws a card picture as SVG (kind "draw"). Whatever it sends is data from outside, so it is rebuilt here from an allowlist:
only basic shapes, gradients and a few presentation attributes survive; text, scripts, styles, links, images, entities and anything
unknown are rejected or dropped. `clean` is used by the author step AND again by the renderer, so a hand-edited spec cannot bypass it."""
import html
import re
import xml.etree.ElementTree as ET

NS = "http://www.w3.org/2000/svg"
TAGS = {"g", "path", "circle", "ellipse", "rect", "line", "polyline", "polygon", "defs", "linearGradient", "radialGradient", "stop"}
DROP = {"text", "tspan", "title", "desc", "metadata"}  # text inside a picture would dodge the contrast/font rules: dropped, not rejected
ATTRS = {"d", "cx", "cy", "r", "rx", "ry", "x", "y", "x1", "y1", "x2", "y2", "width", "height", "points", "fill", "stroke", "stroke-width",
         "stroke-linecap", "stroke-linejoin", "stroke-dasharray", "opacity", "fill-opacity", "stroke-opacity", "fill-rule", "transform", "offset",
         "stop-color", "stop-opacity", "gradientTransform", "gradientUnits", "fx", "fy", "id"}
TRANSFORM = re.compile(r"^(\s*(translate|rotate|scale|skewX|skewY|matrix)\(\s*[-\d.,\s e]+\)\s*)+$")
URL = re.compile(r"^url\(#[\w-]{1,24}\)$")
ID = re.compile(r"^[A-Za-z][\w-]{0,23}$")
MOTIONS = ("float", "pulse", "sway", "drift")


def _local(tag):
    return tag.rsplit("}", 1)[-1]


def _attr_ok(name, value, tag, ids=False):
    v = value.strip()
    if len(v) > 1500 or re.search(r"javascript|data:|expression|<|>|&", v, re.I):
        return False
    if "url(" in v and not URL.match(v):
        return False
    if name == "transform" or name == "gradientTransform":
        return bool(TRANSFORM.match(v))
    if name == "id":
        return (ids or tag in ("linearGradient", "radialGradient")) and bool(ID.match(v))  # ids on shapes only for animated pictures (tweens address them)
    return True


def _build(el, count, ids=False):
    tag = _local(el.tag)
    if tag in DROP:
        return ""
    if tag not in TAGS:
        raise ValueError(tag)
    count[0] += 1
    if count[0] > 120:
        raise ValueError("too many elements")
    attrs = "".join(f' {_local(k)}="{html.escape(v.strip(), quote=True)}"' for k, v in el.attrib.items()
                    if _local(k) in ATTRS and _attr_ok(_local(k), v, tag, ids))
    return f"<{tag}{attrs}>" + "".join(_build(c, count, ids) for c in el) + f"</{tag}>"


def clean(svg, max_len=6000, ids=False):
    """Markup (children of an 800x420 <svg>) -> rebuilt safe markup, or None when it is empty, too big, malformed or uses anything not allowed."""
    s = str(svg or "").strip()
    if not s or len(s) > max_len or "<!" in s or "<?" in s or "&" in s:
        return None
    try:
        root = ET.fromstring(f'<svg xmlns="{NS}">{s}</svg>')
        kids = list(root)
        if len(kids) == 1 and _local(kids[0].tag) == "svg":  # Claude may send the whole <svg ...>...</svg>: take what is inside
            kids = list(kids[0])
        count = [0]
        out = "".join(_build(k, count, ids) for k in kids)
    except (ET.ParseError, ValueError):
        return None
    return out if count[0] else None


def scope(markup, uid):
    """Gradient ids are per picture: prefix them with the card number so two cards never clash."""
    pre = f"dr{uid}_"
    return re.sub(r'url\(#', f'url(#{pre}', re.sub(r' id="', f' id="{pre}', markup))


TW_PROPS = ("x", "y", "rotation", "scale", "scaleX", "scaleY", "opacity", "strokeDashoffset")
TW_EASE = ("none", "power1.out", "power1.inOut", "power2.in", "power2.out", "power2.inOut", "power3.in", "power3.out", "sine.inOut", "back.out(1.7)", "bounce.out")


def _num(v):
    return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) and abs(v) <= 2000 else None


def _props(m):
    return {k: _num(v) for k, v in m.items() if k in TW_PROPS and _num(v) is not None} if isinstance(m, dict) else {}


def clean_tweens(tw, ids, limit=40):
    """Object animation of a drawn picture, from outside data: [{id, at, dur, from{}, to{}, ease, loop, o:[x,y]}] -> a normalised list.
    Only allowlisted props and eases, numbers in range, `id` must be a shape of the picture (`ids`); anything else is dropped. Used by the author AND the renderer."""
    out = []
    for t in [x for x in tw if isinstance(x, dict)][:limit] if isinstance(tw, list) else []:
        to, at, dur = _props(t.get("to")), _num(t.get("at", 0)), _num(t.get("dur", .6))
        if t.get("id") not in ids or not to or at is None or dur is None or at < 0:
            continue
        o = {"id": t["id"], "at": at, "dur": min(max(dur, .05), 8.0), "from": _props(t.get("from")), "to": to,
             "ease": t.get("ease") if t.get("ease") in TW_EASE else "power2.out"}
        if t.get("loop") in (True, "cycle"):
            o["loop"] = t["loop"]
        c = t.get("o")
        if isinstance(c, list) and len(c) == 2 and all(_num(v) is not None for v in c):
            o["o"] = [_num(c[0]), _num(c[1])]
        out.append(o)
    return out
