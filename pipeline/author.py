"""Optional Claude step: reads the whisper lines of the chosen fragment and writes the creative part of the spec
(trim to a finished thought, hook, caption, widget cards + island notifications). Everything it returns is validated and
sanitized here; any failure (no CLI, no token, bad JSON, timeout) falls back to the keyword auto-widgets, never aborts the batch.

Needs the `claude` CLI and a login (CLAUDE_CODE_OAUTH_TOKEN in CI, see docs/claude-author.md). One call per video."""
import json
import os
import random
import re
import shutil
import subprocess
import tempfile

from . import svg_safe
from .common import ROOT
from .render_widgets import ART_KEYS, KINDS

KEYS = ("kind", "app", "cat", "cap", "icon", "art", "art2", "label", "label2", "from", "to", "unit", "button", "fill", "inf", "query", "result", "sub",
        "focus", "zoom", "bubble", "msgs", "chosen", "big", "emblem", "pill", "a", "b", "word", "shift", "notify", "toast", "svg", "frames", "motion")
NUM = ("from", "to", "fill", "zoom", "shift")  # `from`/`to` are numbers for most kinds and place names for route
TEXT_LIMIT = 40
HEX = re.compile(r"^#[0-9a-fA-F]{6}$")


STYLES = ("акварель с мягкими разводами", "вырезанная из бумаги аппликация в несколько слоёв", "плоские яркие стикеры",
          "мягкий пастельный минимализм", "киноплакат с крупным силуэтом", "рисунок мелками", "детская книжка с крупными предметами",
          "вечерний город в тёплых огнях", "светлая плоская иллюстрация, как в приложении")  # figurative only: abstract neon/geometry read badly in a card


def variety(rng=None):
    """A different brief on every call (system random, nothing stored): 4 template kinds are banned and the drawings get another style, so
    two videos never come out of the same recipe even when the lines look alike. Only banned kinds that exist in the renderer are named."""
    rng = rng or random.SystemRandom()
    ban = rng.sample([k for k in KINDS if k not in ("draw", "scene")], 4)
    return (f"Для этого ролика НЕ используй виды: {', '.join(ban)}. Стиль всех рисунков `draw` в этом ролике: {rng.choice(STYLES)}. "
            f"Рисуй узнаваемые предметы из жизни (ключ, чашка, дверь, окно, телефон), а не абстрактные фигуры и не неон. Образы необычные, без очевидных (сердце, часы, дождь).")


def build_prompt(entry, lines, cfg):
    tpl = (ROOT / "prompts" / "widgets.md").read_text(encoding="utf-8")
    txt = "\n".join(f'{i} | {l["start"]:.1f}–{l["end"]:.1f} | {l["text"]}' for i, l in enumerate(lines))
    lo, hi = cfg["min_len"], cfg["max_len"] + cfg.get("close_overrun", 8.0)  # the fragment may run over max_len to finish its thought
    avoid = entry.get("avoid_kinds") or []  # kinds the other videos of today's batch already use: ask for different ones
    note = f"Другие ролики сегодня уже используют: {', '.join(avoid)}. Выбирай другие виды и другие art." if avoid else ""
    note = (note + " " + variety()).strip()
    return (tpl.replace("{{ARTIST}}", entry.get("artist", "")).replace("{{TITLE}}", entry.get("title", "")).replace("{{LINES}}", txt)
            .replace("{{AVOID}}", note)
            .replace("{{MIN}}", str(lo)).replace("{{MAX}}", str(hi)).replace("{{TARGET}}", f"{lo + 4}–{lo + 12}"))


def call_claude(prompt, cfg):
    """Run `claude -p` in an empty temp dir (so no project CLAUDE.md is loaded), no tools. Returns the text output."""
    a = cfg.get("author", {})
    cmd = [shutil.which("claude") or "claude", "-p", "--model", a.get("model", "sonnet"), "--output-format", "text",
           "--tools", "", "--no-session-persistence"]
    with tempfile.TemporaryDirectory() as td:
        r = subprocess.run(cmd, input=prompt, capture_output=True, text=True, encoding="utf-8", timeout=a.get("timeout", 240), cwd=td)
    if r.returncode != 0:
        raise RuntimeError(f"claude exit {r.returncode}: {(r.stderr or r.stdout)[-200:]}")
    return r.stdout


def parse_json(text):
    t = text.strip()
    t = re.sub(r"^```(?:json)?\s*|\s*```$", "", t)
    i = t.find("{")
    if i < 0:
        raise ValueError("no JSON object in the answer")
    obj, _ = json.JSONDecoder().raw_decode(t[i:])
    return obj


def _s(v, n=TEXT_LIMIT):
    return str(v).strip()[:n]


def _notify(n):
    if not isinstance(n, dict) or not n.get("text"):
        return None
    icon = n.get("icon") if HEX.match(str(n.get("icon", ""))) else "#34c759"
    return {"app": _s(n.get("app", ""), 18), "text": _s(n["text"], 36), "icon": icon}


def sanitize_widgets(widgets, n_lines):
    """Keep only known keys/kinds, clip text, clamp indices, drop overlaps. Returns a list safe for spec["widgets"]."""
    out, used = [], set()
    for w in widgets if isinstance(widgets, list) else []:
        if not isinstance(w, dict):
            continue
        ln = sorted({int(x) for x in (w.get("lines") or []) if isinstance(x, (int, float)) and 0 <= int(x) < n_lines})
        if not ln or used & set(ln) or w.get("kind") not in KINDS:
            continue
        o = {"lines": ln, "kind": w["kind"]}
        for k in KEYS[1:]:
            v = w.get(k)
            if v in (None, ""):
                continue
            if k in ("notify", "toast"):
                nv = _notify(v)
                if nv:
                    o[k] = nv
            elif k == "svg":
                if w["kind"] == "draw":
                    sv = svg_safe.clean(v)
                    if sv:
                        o[k] = sv
            elif k == "frames":  # a drawn card is a short film: up to 5 pictures that follow each other about once a second
                if w["kind"] == "draw" and isinstance(v, list):
                    fr = [x for x in (svg_safe.clean(m) for m in v[:8]) if x][:5]
                    if fr:
                        o[k] = fr
            elif k == "motion":
                if v in svg_safe.MOTIONS:
                    o[k] = v
            elif k == "msgs":
                ms = [{"from": "me" if m.get("from") == "me" else "her", "text": _s(m.get("text", ""), 46)} for m in v if isinstance(m, dict)][:3]
                if ms:
                    o[k] = ms
            elif k in ("art", "art2"):
                if v in ART_KEYS:
                    o[k] = v
            elif k == "icon":
                if HEX.match(str(v)):
                    o[k] = v
            elif k == "emblem":
                if v in ("crown", "heart", "star"):
                    o[k] = v
            elif k == "inf":
                o[k] = bool(v)
            elif k in NUM and not (w["kind"] == "route" and k in ("from", "to")):
                try:
                    x = float(v)
                    o[k] = x if k in ("fill", "zoom") or x != int(x) else int(x)  # thermo needs 36.6, pulse needs 70
                except (TypeError, ValueError, OverflowError):
                    pass
            else:
                o[k] = _s(v)
        if o["kind"] == "draw" and "svg" not in o and "frames" not in o:
            o["kind"] = "scene"  # the drawing was missing or not allowed: show a template picture instead
        used |= set(ln)
        out.append(o)
    return out


def apply_result(res, analysis, spec, cfg):
    """Validate the Claude answer and apply it. Returns (analysis, spec, note). Raises ValueError when nothing usable."""
    fr = analysis["fragment"]
    lines = analysis["lines"][fr["first"]: fr["last"] + 1]
    a, b, note = 0, len(lines) - 1, []
    tr = None if fr.get("pinned") else res.get("trim")  # the owner pinned the start in the file name: no trimming
    if isinstance(tr, dict):
        try:
            f, t = int(tr["from"]), int(tr["to"])
            ln = lines[t]["end"] - lines[f]["start"]
            if 0 <= f <= t < len(lines) and cfg["min_len"] <= ln <= cfg["max_len"] + cfg.get("close_overrun", 8.0):
                a, b = f, t
                note.append(f"trim {f}..{t}")
        except (KeyError, TypeError, ValueError, IndexError):
            pass
    n = b - a + 1
    wd = sanitize_widgets(res.get("widgets"), n)
    if not wd:
        raise ValueError("no valid widgets in the answer")
    new_spec = dict(spec, widgets=wd)
    hook = _s(res.get("hook", ""), 36).upper()
    if hook:
        new_spec["hook"] = hook
    cap = _s(res.get("caption", ""), 150)
    if cap:
        new_spec["caption"] = cap
    new_an = analysis
    if (a, b) != (0, len(lines) - 1):
        first, last = fr["first"] + a, fr["first"] + b
        L = analysis["lines"]
        new_an = dict(analysis, fragment=dict(fr, first=first, last=last, start=L[first]["start"], end=L[last]["end"],
                                              length=round(L[last]["end"] - L[first]["start"], 2), reason=fr.get("reason", "") + "; trimmed by author"))
    return new_an, new_spec, ", ".join(note) or "no trim"


def author(entry, analysis, spec, cfg, runner=call_claude):
    """-> (analysis, spec, status). Never raises: status 'claude: ...' on success, 'fallback: reason' / 'off' otherwise."""
    a = cfg.get("author", {})
    if os.environ.get("VYBEX_NO_AUTHOR") or not a.get("enabled") or not analysis.get("fragment"):
        return analysis, spec, "off"
    if runner is call_claude and not shutil.which("claude"):
        return analysis, spec, "fallback: claude CLI not installed"
    fr = analysis["fragment"]
    lines = analysis["lines"][fr["first"]: fr["last"] + 1]
    err = None
    for attempt in range(1, a.get("attempts", 3) + 1):  # a bad answer / rate limit gets a fresh brief (new variety) instead of keyword cards
        try:
            res = parse_json(runner(build_prompt(entry, lines, cfg), cfg))
            an, sp, note = apply_result(res, analysis, spec, cfg)
            return an, sp, f"claude: {len(sp['widgets'])} cards, {note}" + (f", attempt {attempt}" if attempt > 1 else "")
        except subprocess.TimeoutExpired as e:  # a slow Claude will not be faster the second time
            err = e
            break
        except Exception as e:  # noqa: BLE001 - the batch must go on with auto widgets
            err = e
    return analysis, spec, f"fallback: {type(err).__name__}: {str(err)[:120]}"
