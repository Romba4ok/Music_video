"""Scenario generation: analysis fragment -> timed lyric cards (deterministic, no LLM tokens).

Cards appear shortly BEFORE their first word and leave after their last word; no overlaps; words carry exact timestamps.
"""
import math

LEAD, HOLD, GAP = 0.25, 0.35, 0.05


def split_words(words, max_words=8):
    n = max(1, math.ceil(len(words) / max_words))
    size = math.ceil(len(words) / n)
    return [words[i:i + size] for i in range(0, len(words), size)]


def _groups(n, widgets):
    """[(first_line, last_line, widget|None, half|None)] covering fragment lines 0..n-1; lines no widget claims get single-line auto groups.
    A long line may carry two widgets with half 0 and 1 (its first and second half of the words): two cards for one line."""
    claimed, halves = {}, {}
    for w in sorted(widgets or [], key=lambda w: (min(w["lines"]), w.get("half") or 0)):
        a, b = min(w["lines"]), min(max(w["lines"]), n - 1)
        h = w.get("half")
        if h in (0, 1) and a == b < n:
            if a not in claimed:
                halves.setdefault(a, {}).setdefault(h, w)
        elif a < n and not any(i in claimed or i in halves for i in range(a, b + 1)):
            claimed.update({i: (a, b, w) for i in range(a, b + 1)})
    out, i = [], 0
    while i < n:
        if i in halves:
            hv = halves[i]
            out += [(i, i, hv[h], h) for h in (0, 1) if h in hv] if len(hv) == 2 else [(i, i, next(iter(hv.values())), None)]
            i += 1
            continue
        a, b, w = claimed.get(i, (i, i, None))
        out.append((a, b, w, None))
        i = b + 1
    return out


def build_scenes(analysis, song, cfg, intro=0.0, widgets=None):
    frag = analysis["fragment"]
    t0 = frag["start"]
    length = frag["end"] - t0
    tail = cfg["tail_sec"]
    thr = cfg["whisper"]["min_confidence"]
    cards = []
    flines = analysis["lines"][frag["first"]: frag["last"] + 1]
    if widgets is None:
        chunks = [(ch, None) for ln in flines for ch in split_words(ln["words"])]
    else:  # one card per widget group: all words of its lines, no 8-word split
        chunks = []
        for a, b, wd, half in _groups(len(flines), widgets):
            ws = [w for ln in flines[a:b + 1] for w in ln["words"]]
            if half is not None:
                if len(ws) < 4:  # too short to show twice: the first half's card takes the whole line
                    if half == 1:
                        continue
                else:
                    ws = ws[:len(ws) // 2] if half == 0 else ws[len(ws) // 2:]
            chunks.append((ws, wd))
    for ch, wd in chunks:
        card = {
            "role": "lyric", "text": " ".join(w["w"] for w in ch),
            "start": round(max(0.0, ch[0]["s"] - t0 - LEAD), 3), "end": round(ch[-1]["e"] - t0 + HOLD, 3),
            "words": [{"w": w["w"], "s": round(w["s"] - t0, 3), "e": round(w["e"] - t0, 3)} for w in ch],
            "low_conf": [i for i, w in enumerate(ch) if w["p"] < thr],
        }
        if wd:
            card["widget"] = wd
        cards.append(card)
    for a, b in zip(cards, cards[1:]):
        if a["end"] > b["start"] - GAP:
            a["end"] = round(max(a["start"] + 0.2, b["start"] - GAP), 3)
    duration = round(length + tail, 2)
    cards[-1]["end"] = round(min(cards[-1]["end"], length + 0.3), 3)
    outro_start = round(max(cards[-1]["end"] + 0.1, length + 0.3), 3)
    outro = {"role": "outro", "text": f'{song["artist"]} — {song["title"]}', "start": outro_start, "end": duration, "words": []}
    beats = [round(b - t0, 3) for b in analysis.get("beats", []) if t0 <= b < t0 + length]
    scenes = cards + [outro]
    intro = round(min(intro, t0), 3)  # intro plays over the song's lead-in: audio starts `intro` earlier, everything else shifts
    if intro:
        for sc in scenes:
            sc["start"], sc["end"] = round(sc["start"] + intro, 3), round(sc["end"] + intro, 3)
            for w in sc["words"]:
                w["s"], w["e"] = round(w["s"] + intro, 3), round(w["e"] + intro, 3)
        beats = [round(b + intro, 3) for b in beats]
    return {"duration": round(duration + intro, 2), "scenes": scenes, "beats": beats, "audio_start": round(t0 - intro, 3),
            "audio_len": round(duration + intro, 2), "intro": intro}
