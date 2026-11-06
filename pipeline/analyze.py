"""Audio analysis: lyrics with word timestamps (faster-whisper), beats (librosa), chorus + fragment choice.

Heavy libs are imported lazily. `find_chorus` and `pick_fragment` are pure and unit-tested.
Lyrics come ONLY from recognition of the supplied audio, never from memory; low-confidence words are flagged later.
"""
import difflib
import json
import re
import sys
from pathlib import Path

from .common import ROOT, load_config


def norm(s):
    return re.sub(r"[^\w\s]", "", s.lower(), flags=re.U).strip()


def _pcm16k(path):
    """Decode with ffmpeg (already required) so faster-whisper's PyAV decoder, which breaks across av versions, is not used."""
    import subprocess

    import numpy as np
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", str(path), "-f", "f32le", "-ac", "1", "-ar", "16000", "-"],
                         capture_output=True, check=True).stdout
    return np.frombuffer(raw, dtype=np.float32)


def transcribe(path, cfg):
    from faster_whisper import WhisperModel
    w = cfg["whisper"]
    model = WhisperModel(w["model"], device=w["device"], compute_type=w["compute_type"])
    segs, _ = model.transcribe(_pcm16k(path), language=cfg["language"], word_timestamps=True,
                               condition_on_previous_text=False)
    lines = []
    for s in segs:
        words = [{"w": x.word.strip(), "s": round(x.start, 3), "e": round(x.end, 3), "p": round(x.probability, 3)}
                 for x in (s.words or []) if x.word.strip()]
        if words:
            lines.append({"start": words[0]["s"], "end": words[-1]["e"], "text": " ".join(x["w"] for x in words),
                          "words": words})
    return clean_lines(lines, cfg["language"])


def clean_lines(lines, lang):
    """Russian recognition sometimes hallucinates Latin tokens ('canceled', 'Вdablo'): drop them; lines left empty vanish."""
    if lang != "ru":
        return lines
    out = []
    for ln in lines:
        ws = [w for w in ln["words"] if not re.search(r"[A-Za-z]", w["w"])]
        if ws:
            out.append({"start": ws[0]["s"], "end": ws[-1]["e"], "text": " ".join(w["w"] for w in ws), "words": ws})
    return out


def refragment(analysis, cfg, popular_line=""):
    """Re-clean saved lines and recompute chorus + fragment without running whisper again."""
    lines = clean_lines(analysis["lines"], cfg["language"])
    chorus = find_chorus(lines)
    frag = pick_fragment(lines, popular_line, cfg["min_len"], cfg["max_len"], chorus=chorus)
    return dict(analysis, lines=lines, fragment=frag)


def beats(path):
    import librosa
    y, sr = librosa.load(str(path), sr=22050, mono=True)
    tempo, bt = librosa.beat.beat_track(y=y, sr=sr)
    return {"bpm": round(float(getattr(tempo, "item", lambda: tempo)()), 1), "beats": [round(float(t), 3) for t in
            librosa.frames_to_time(bt, sr=sr)], "duration": round(len(y) / sr, 2)}


def find_chorus(lines, thr=0.8):
    """Blocks of consecutive lines whose text repeats elsewhere. Returns candidates, best first."""
    texts = [norm(l["text"]) for l in lines]
    cluster = []
    reps = []  # representative text per cluster
    for t in texts:
        for ci, r in enumerate(reps):
            if difflib.SequenceMatcher(None, t, r).ratio() >= thr:
                cluster.append(ci)
                break
        else:
            reps.append(t)
            cluster.append(len(reps) - 1)
    count = {c: cluster.count(c) for c in set(cluster)}
    rep = [count[c] >= 2 and len(texts[i]) > 3 for i, c in enumerate(cluster)]
    blocks, i = [], 0
    while i < len(lines):
        if rep[i]:
            j = i
            while j + 1 < len(lines) and rep[j + 1]:
                j += 1
            blocks.append({"first": i, "last": j, "start": lines[i]["start"], "end": lines[j]["end"],
                           "repeats": max(count[cluster[k]] for k in range(i, j + 1)), "text": lines[i]["text"]})
            i = j + 1
        else:
            i += 1
    blocks.sort(key=lambda b: (-(b["last"] - b["first"] + 1) * b["repeats"], b["start"]))
    return blocks


def _match_popular(lines, popular, min_ratio=0.6):
    """Best line index for the popular line (also tries pairs of adjacent lines)."""
    p = norm(popular)
    best, bi = 0, None
    for i, l in enumerate(lines):
        for t in (norm(l["text"]), norm(l["text"] + " " + lines[i + 1]["text"]) if i + 1 < len(lines) else ""):
            if not t:
                continue
            r = difflib.SequenceMatcher(None, p, t).ratio()
            if p and p in t:
                r = max(r, 0.95)
            if r > best + 1e-9:
                best, bi = r, i
    return (bi, round(best, 2)) if best >= min_ratio else (None, round(best, 2))


def pick_fragment(lines, popular_line="", min_len=30, max_len=60, gap=0.6, chorus=None):
    """Window of whole lines containing the most popular line (else the top chorus). Ends on a phrase boundary."""
    if not lines:
        return None
    chorus = chorus if chorus is not None else find_chorus(lines)
    anchor, reason = None, ""
    pin = popular_line.startswith("=")  # '=text' (from 'Artist - Title [text].mp3'): the fragment starts exactly at that line
    popular_line = popular_line.lstrip("=").strip()
    if popular_line:
        anchor, ratio = _match_popular(lines, popular_line)
        if pin:  # a line that itself begins with the phrase wins over a pair match that only contains it
            anchor = next((i for i, l in enumerate(lines) if norm(l["text"]).startswith(norm(popular_line))), anchor)
        reason = f"popular_line matched (ratio {ratio})" if anchor is not None else f"popular_line not found (best {ratio})"
    if anchor is None and chorus:
        anchor = chorus[0]["first"]
        reason = (reason + "; " if reason else "") + "top chorus candidate"
    if anchor is None:
        anchor = 0
        reason = (reason + "; " if reason else "") + "no chorus found, starting at first line"
    first = anchor
    pin = pin and "matched" in reason  # phrase not found -> normal automatic choice
    for b in ([] if pin else chorus):  # start at the beginning of the chorus block that contains the anchor
        if b["first"] <= anchor <= b["last"]:
            first = b["first"]
            break
    last = max(first, anchor)

    def length(a, b):
        return lines[b]["end"] - lines[a]["start"]

    while length(first, last) < min_len and (last + 1 < len(lines) or first > 0):
        if last + 1 < len(lines) and length(first, last + 1) <= max_len:
            last += 1
        elif first > 0 and not pin and length(first - 1, last) <= max_len:
            first -= 1
        else:
            break
    # stop at a phrase boundary: extend (within max_len) until the pause after the last line is >= gap
    while last + 1 < len(lines) and lines[last + 1]["start"] - lines[last]["end"] < gap and length(first, last + 1) <= max_len:
        last += 1
    return {"first": first, "last": last, "start": lines[first]["start"], "end": lines[last]["end"],
            "length": round(length(first, last), 2), "reason": reason + ("; start pinned by file name" if pin else ""), "pinned": pin}


def analyze(path, popular_line="", cfg=None):
    cfg = cfg or load_config()
    lines = transcribe(path, cfg)
    b = beats(path)
    chorus = find_chorus(lines)
    frag = pick_fragment(lines, popular_line, cfg["min_len"], cfg["max_len"], chorus=chorus)
    low = sum(1 for l in lines for w in l["words"] if w["p"] < cfg["whisper"]["min_confidence"])
    nwords = sum(len(l["words"]) for l in lines)
    summary = {"bpm": b["bpm"], "audio_duration": b["duration"], "lines": len(lines), "words": nwords,
               "low_confidence_words": low, "popular_line_found": bool(frag and "matched" in frag["reason"]),
               "fragment": frag and {k: frag[k] for k in ("start", "end", "length", "reason")},
               "chorus_candidates": [{"start": c["start"], "end": c["end"], "repeats": c["repeats"], "text": c["text"][:60]}
                                     for c in chorus[:3]]}
    return {"summary": summary, "lines": lines, "beats": b["beats"], "fragment": frag}


def main():
    """python -m pipeline.analyze out/<date>   (reads songs.json: [{artist,title,audio,popular_line}])"""
    d = Path(sys.argv[1])
    cfg = load_config()
    songs = json.loads((d / "songs.json").read_text(encoding="utf-8"))
    for n, s in enumerate(songs, 1):
        a = analyze(ROOT / s["audio"], s.get("popular_line", ""), cfg)
        (d / f"analysis-{n}.json").write_text(json.dumps(a, ensure_ascii=False), encoding="utf-8")
        print(f"analysis-{n}: " + json.dumps(a["summary"], ensure_ascii=False))


if __name__ == "__main__":
    main()
