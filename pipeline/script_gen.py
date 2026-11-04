"""Scenario generation: analysis fragment -> timed lyric cards (deterministic, no LLM tokens).

Cards appear shortly BEFORE their first word and leave after their last word; no overlaps; words carry exact timestamps.
"""
import math

LEAD, HOLD, GAP = 0.25, 0.35, 0.05


def split_words(words, max_words=8):
    n = max(1, math.ceil(len(words) / max_words))
    size = math.ceil(len(words) / n)
    return [words[i:i + size] for i in range(0, len(words), size)]


def build_scenes(analysis, song, cfg):
    frag = analysis["fragment"]
    t0 = frag["start"]
    length = frag["end"] - t0
    tail = cfg["tail_sec"]
    thr = cfg["whisper"]["min_confidence"]
    cards = []
    for ln in analysis["lines"][frag["first"]: frag["last"] + 1]:
        for ch in split_words(ln["words"]):
            cards.append({
                "role": "lyric", "text": " ".join(w["w"] for w in ch),
                "start": round(max(0.0, ch[0]["s"] - t0 - LEAD), 3), "end": round(ch[-1]["e"] - t0 + HOLD, 3),
                "words": [{"w": w["w"], "s": round(w["s"] - t0, 3), "e": round(w["e"] - t0, 3)} for w in ch],
                "low_conf": [i for i, w in enumerate(ch) if w["p"] < thr],
            })
    for a, b in zip(cards, cards[1:]):
        if a["end"] > b["start"] - GAP:
            a["end"] = round(max(a["start"] + 0.2, b["start"] - GAP), 3)
    duration = round(length + tail, 2)
    cards[-1]["end"] = round(min(cards[-1]["end"], length + 0.3), 3)
    outro_start = round(max(cards[-1]["end"] + 0.1, length + 0.3), 3)
    outro = {"role": "outro", "text": f'{song["artist"]} — {song["title"]}', "start": outro_start, "end": duration, "words": []}
    beats = [round(b - t0, 3) for b in analysis.get("beats", []) if t0 <= b < t0 + length]
    return {"duration": duration, "scenes": cards + [outro], "beats": beats, "audio_start": t0, "audio_len": duration}
