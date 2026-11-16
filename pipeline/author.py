"""Optional Claude step in TWO calls per video: (1) the SCENARIO (prompts/scenario.md): from the whole song's meaning it writes the story arc, trim, hook,
caption, mood and one idea per card; (2) the BUILD (prompts/widgets.md): it draws every card exactly as the scenario says. The build is rejected unless it
follows the scenario card by card. Everything returned is validated and sanitized here; any failure (no CLI, no token, bad JSON, timeout) falls back to the
keyword auto-widgets, never aborts the batch. The scenario is kept in spec["scenario"].

Needs the `claude` CLI and a login (CLAUDE_CODE_OAUTH_TOKEN in CI, see docs/claude-author.md)."""
import json
import os
import random
import re
import shutil
import subprocess
import tempfile

from . import svg_safe
from .common import ROOT
from .widgets_plan import KINDS

KEYS = ("kind", "app", "cat", "cap", "icon", "big", "chips", "svg", "tw", "motion", "notify", "toast")
TEXT_LIMIT = 40
HEX = re.compile(r"^#[0-9a-fA-F]{6}$")


STYLES = ("акварель с мягкими разводами", "вырезанная из бумаги аппликация в несколько слоёв", "плоские яркие стикеры",
          "мягкий пастельный минимализм", "киноплакат с крупным силуэтом", "рисунок мелками", "детская книжка с крупными предметами",
          "вечерний город в тёплых огнях", "светлая плоская иллюстрация, как в приложении")  # figurative only: abstract neon/geometry read badly in a card


def variety(rng=None):
    """A different brief on every call (system random, nothing stored): the drawings get another style, so two videos never come out of the same
    recipe even when the lines look alike."""
    rng = rng or random.SystemRandom()
    return (f"Стиль всех рисунков `draw` в этом ролике: {rng.choice(STYLES)}. "
            f"Рисуй узнаваемые предметы из жизни (ключ, чашка, дверь, окно, телефон), а не абстрактные фигуры и не неон. Образы необычные, без очевидных (сердце, часы, дождь).")


def song_text(all_lines, limit=2500):
    """Plain text of the whole song for the theme (no times; neighbouring repeats dropped, clipped): the cards still follow the fragment only."""
    out, prev = [], None
    for l in all_lines or []:
        t = str(l.get("text", "")).strip()
        if t and t != prev:
            out.append(t)
        prev = t
    return "\n".join(out)[:limit] or "(нет)"


def render_scenario(sc):
    """The scenario as plain text: given to the build prompt and saved next to the video (scenario-N.txt)."""
    cards = "\n".join(f'{i} | строки {c["lines"]}' + (f' половина {c["half"]}' if "half" in c else "") + f' | {c["kind"]} | {c["idea"]} | подпись: {c.get("cap", "")}'
                      for i, c in enumerate(sc["cards"]))
    return (f'О чём песня: {sc["about"]}\nПуть песни: ' + " → ".join(sc.get("arc") or []) + f'\nХук: {sc.get("hook", "")}\n'
            f'Настроение: {sc.get("mood", "")}\nКарточки (номер | строки | вид | идея | подпись):\n{cards}')


def build_scenario_prompt(entry, lines, cfg, song_lines=None):
    """Stage 1: lines are the whole picked fragment (before trim)."""
    return _fill("scenario.md", entry, lines, cfg, song_lines)


def build_prompt(entry, lines, cfg, song_lines=None, scenario=None):
    """Stage 2: lines are the fragment AFTER the scenario's trim; `scenario` is the checked dict from check_scenario."""
    return _fill("widgets.md", entry, lines, cfg, song_lines, render_scenario(scenario) if scenario else "")


def _fill(name, entry, lines, cfg, song_lines, scenario=""):
    tpl = (ROOT / "prompts" / name).read_text(encoding="utf-8")
    txt = "\n".join(f'{i} | {l["start"]:.1f}–{l["end"]:.1f} | {l["text"]}' for i, l in enumerate(lines))
    lo, hi = cfg["min_len"], cfg["max_len"] + cfg.get("close_overrun", 8.0)  # the fragment may run over max_len to finish its thought
    note = variety()
    rt = entry.get("recent_themes") or []
    theme = (f"Последние ролики были {'тёмные' if rt[-1] == 'dark' else 'светлые'}: если песня позволяет, сделай этот {'светлым' if rt[-1] == 'dark' else 'тёмным'} для разнообразия."
             if len(rt) >= 2 and rt[-1] == rt[-2] else "")
    return (tpl.replace("{{ARTIST}}", entry.get("artist", "")).replace("{{TITLE}}", entry.get("title", "")).replace("{{LINES}}", txt)
            .replace("{{AVOID}}", note).replace("{{THEME}}", theme).replace("{{SONG}}", song_text(song_lines)).replace("{{SCENARIO}}", scenario)
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


def _trim(res, fr, lines, cfg):
    """-> (a, b, note): the author's trim `from`..`to` when it is valid and keeps the length in range, else the whole fragment."""
    a, b, note = 0, len(lines) - 1, ""
    tr = None if fr.get("pinned") else res.get("trim")  # the owner pinned the start in the file name: no trimming
    if isinstance(tr, dict):
        try:
            f, t = int(tr["from"]), int(tr["to"])
            ln = lines[t]["end"] - lines[f]["start"]
            if 0 <= f <= t < len(lines) and cfg["min_len"] <= ln <= cfg["max_len"] + cfg.get("close_overrun", 8.0):
                a, b, note = f, t, f"trim {f}..{t}" if (f, t) != (0, len(lines) - 1) else ""
        except (KeyError, TypeError, ValueError, IndexError):
            pass
    return a, b, note


def check_scenario(res, fr, lines, cfg):
    """Validate the stage-1 answer -> a clean scenario dict (about, arc, trim, hook, caption, mood, cards). Raises ValueError when unusable."""
    a, b, _ = _trim(res, fr, lines, cfg)
    n, cards = b - a + 1, []
    for c in res.get("cards") if isinstance(res.get("cards"), list) else []:
        ln = sorted({int(x) for x in (c.get("lines") or []) if isinstance(x, (int, float))}) if isinstance(c, dict) else []
        if not ln or ln[0] < 0 or ln[-1] >= n or c.get("kind") not in KINDS or not str(c.get("idea", "")).strip():
            continue  # a card without lines in range, a known kind or an idea is not part of the scenario
        o = {"lines": ln, "kind": c["kind"], "idea": _s(c["idea"], 260), "cap": _s(c.get("cap", ""), 26)}
        if len(ln) == 1 and c.get("half") in (0, 1):
            o["half"] = c["half"]
        cards.append(o)
    if len(cards) < 3:
        raise ValueError("the scenario has fewer than 3 usable cards")
    arc = [_s(x, 90) for x in res.get("arc") or [] if isinstance(x, str) and x.strip()][:3]
    if not res.get("about") or len(arc) < 2:
        raise ValueError("the scenario needs `about` and an `arc` of the whole song")
    sc = {"about": _s(res["about"], 140), "arc": arc, "trim": {"from": a, "to": b}, "cards": cards,
          "hook": _s(res.get("hook", ""), 36).upper(), "caption": _s(res.get("caption", ""), 150)}
    if res.get("mood") in ("dark", "light"):
        sc["mood"] = res["mood"]
    return sc


def follows_scenario(widgets, sc):
    """The build must be the scenario card by card (same lines, half, kind), or it is not 'built from the scenario'. Raises ValueError otherwise."""
    got = [(tuple(w.get("lines") or ()), w.get("half"), w.get("kind")) for w in widgets if isinstance(w, dict)]
    want = [(tuple(c["lines"]), c.get("half"), c["kind"]) for c in sc["cards"]]
    if got != want:
        raise ValueError(f"the build does not follow the scenario ({len(got)} cards vs {len(want)}, first difference at "
                         f"{next((i for i, (g, w) in enumerate(zip(got, want)) if g != w), min(len(got), len(want)))})")


def sanitize_widgets(widgets, n_lines, texts=None):
    """Keep only known keys/kinds, clip text, clamp indices, drop overlaps. Returns a list safe for spec["widgets"].
    `texts` is kept for callers; a dropped card's lines get an automatic scene."""
    out, used, split = [], set(), {}
    for w in widgets if isinstance(widgets, list) else []:
        if not isinstance(w, dict):
            continue
        ln = sorted({int(x) for x in (w.get("lines") or []) if isinstance(x, (int, float)) and 0 <= int(x) < n_lines})
        half = w.get("half") if len(ln) == 1 and w.get("half") in (0, 1) else None  # one long line shown as two cards (half 0 and 1)
        if not ln or w.get("kind") not in KINDS or ((used | set(split)) & set(ln) if half is None else (ln[0] in used or half in split.get(ln[0], ()))):
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
                    sv = svg_safe.clean(v, 4500, ids=True) if isinstance(w.get("tw"), list) else svg_safe.clean(v)  # an animated picture keeps the ids its tweens address
                    if sv:
                        o[k] = sv
            elif k == "tw":  # object animation of the drawn picture (`svg_safe.clean_tweens`); fewer than 2 tweens is not an animation: the picture then floats like a still
                if w["kind"] == "draw" and "svg" in o:
                    tw = svg_safe.clean_tweens(v, set(re.findall(r'id="([\w-]+)"', o["svg"])), 30)
                    if len(tw) >= 2:
                        o[k] = tw
            elif k == "chips":  # up to two short phrase pills on a drawn card
                ch = [_s(c, 22) for c in v if isinstance(c, str) and c.strip()][:2] if isinstance(v, list) else []
                if ch:
                    o[k] = ch
            elif k == "motion":
                if v in svg_safe.MOTIONS:
                    o[k] = v
            elif k == "icon":
                if HEX.match(str(v)):
                    o[k] = v
            else:
                o[k] = _s(v)
        if o["kind"] == "draw" and "svg" not in o:
            continue  # the drawing was missing or not allowed: the lines get a scene picked by meaning (widgets_plan)
        if half is None:
            used |= set(ln)
        else:
            split.setdefault(ln[0], set()).add(half)
            o["half"] = half
        out.append(o)
    return out


def apply_result(res, analysis, spec, cfg):
    """Validate the Claude answer and apply it. Returns (analysis, spec, note). Raises ValueError when nothing usable."""
    fr = analysis["fragment"]
    lines = analysis["lines"][fr["first"]: fr["last"] + 1]
    a, b, note = _trim(res, fr, lines, cfg)
    n = b - a + 1
    wd = sanitize_widgets(res.get("widgets"), n, [l["text"] for l in lines[a:b + 1]])
    if not wd:
        raise ValueError("no valid widgets in the answer")
    new_spec = dict(spec, widgets=wd)
    hook = _s(res.get("hook", ""), 36).upper()
    if hook:
        new_spec["hook"] = hook
    if res.get("about"):
        new_spec["about"] = _s(res["about"], 140)  # one sentence on what the whole fragment is about: the theme every card follows
    if res.get("mood") in ("dark", "light"):
        new_spec["theme"] = res["mood"]
    cap = _s(res.get("caption", ""), 150)
    if cap:
        new_spec["caption"] = cap
    new_an = analysis
    if (a, b) != (0, len(lines) - 1):
        first, last = fr["first"] + a, fr["first"] + b
        L = analysis["lines"]
        new_an = dict(analysis, fragment=dict(fr, first=first, last=last, start=L[first]["start"], end=L[last]["end"],
                                              length=round(L[last]["end"] - L[first]["start"], 2), reason=fr.get("reason", "") + "; trimmed by author"))
    return new_an, new_spec, note or "no trim"


def author(entry, analysis, spec, cfg, runner=call_claude):
    """-> (analysis, spec, status). Never raises: status 'claude: ...' on success, 'fallback: reason' / 'off' otherwise."""
    a = cfg.get("author", {})
    if os.environ.get("VYBEX_NO_AUTHOR") or not a.get("enabled") or not analysis.get("fragment"):
        return analysis, spec, "off"
    if runner is call_claude and not shutil.which("claude"):
        return analysis, spec, "fallback: claude CLI not installed"
    fr = analysis["fragment"]
    lines = analysis["lines"][fr["first"]: fr["last"] + 1]
    err, sc = None, None
    for attempt in range(1, a.get("attempts", 3) + 1):  # a bad answer / rate limit gets a fresh brief (new variety) instead of keyword cards
        try:
            if sc is None:  # the scenario is kept across attempts: only the drawing step is redone when it fails
                sc = check_scenario(parse_json(runner(build_scenario_prompt(entry, lines, cfg, analysis.get("lines")), cfg)), fr, lines, cfg)
            sub = lines[sc["trim"]["from"]: sc["trim"]["to"] + 1]
            built = parse_json(runner(build_prompt(entry, sub, cfg, analysis.get("lines"), sc), cfg))
            follows_scenario(built.get("widgets") or [], sc)
            res = dict({k: v for k, v in sc.items() if k != "cards"}, widgets=built["widgets"])
            an, sp, note = apply_result(res, analysis, spec, cfg)
            sp["scenario"] = sc
            return an, sp, f"claude: scenario {len(sc['cards'])} cards -> {len(sp['widgets'])} built, {note}" + (f", attempt {attempt}" if attempt > 1 else "")
        except subprocess.TimeoutExpired as e:  # a slow Claude will not be faster the second time
            err = e
            break
        except Exception as e:  # noqa: BLE001 - the batch must go on with auto widgets
            err = e
    return analysis, spec, f"fallback: {type(err).__name__}: {str(err)[:120]}"
