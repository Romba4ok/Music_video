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


def _attr_ok(name, value, tag):
    v = value.strip()
    if len(v) > 1500 or re.search(r"javascript|data:|expression|<|>|&", v, re.I):
        return False
    if "url(" in v and not URL.match(v):
        return False
    if name == "transform" or name == "gradientTransform":
        return bool(TRANSFORM.match(v))
    if name == "id":
        return tag in ("linearGradient", "radialGradient") and bool(ID.match(v))
    return True


def _build(el, count):
    tag = _local(el.tag)
    if tag in DROP:
        return ""
    if tag not in TAGS:
        raise ValueError(tag)
    count[0] += 1
    if count[0] > 120:
        raise ValueError("too many elements")
    attrs = "".join(f' {_local(k)}="{html.escape(v.strip(), quote=True)}"' for k, v in el.attrib.items()
                    if _local(k) in ATTRS and _attr_ok(_local(k), v, tag))
    return f"<{tag}{attrs}>" + "".join(_build(c, count) for c in el) + f"</{tag}>"


def clean(svg, max_len=6000):
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
        out = "".join(_build(k, count) for k in kids)
    except (ET.ParseError, ValueError):
        return None
    return out if count[0] else None


def scope(markup, uid):
    """Gradient ids are per picture: prefix them with the card number so two cards never clash."""
    pre = f"dr{uid}_"
    return re.sub(r'url\(#', f'url(#{pre}', re.sub(r' id="', f' id="{pre}', markup))
