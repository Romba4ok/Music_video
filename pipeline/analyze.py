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


# phrases whisper invents on silence / music tails (YouTube-subtitle credits etc.); a line that is one of them is not a lyric
HALLUCINATION = re.compile(r"субтитр|редактор|корректор|продолжение следует|подписывайтесь|спасибо за просмотр|dimatorzok", re.I)


def norm(s):
    return re.sub(r"[^\w\s]", "", s.lower(), flags=re.U).strip()


def _pcm16k(path):
    """Decode with ffmpeg (already required) so faster-whisper's PyAV decoder, which breaks across av versions, is not used."""
    import subprocess

    import numpy as np
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", str(path), "-f", "f32le", "-ac", "1", "-ar", "16000", "-"],
                         capture_output=True, check=True).stdout
    return np.frombuffer(raw, dtype=np.float32)


def transcribe(path, cfg, model=None, window=None):
    """Whisper lines with absolute word times. `model` overrides config (the refine pass), `window=(from_sec, to_sec)` transcribes only that slice."""
    from faster_whisper import WhisperModel
    w = cfg["whisper"]
    m = WhisperModel(model or w["model"], device=w["device"], compute_type=w["compute_type"])
    pcm, off = _pcm16k(path), 0.0
    if window:
        off = max(0.0, window[0])
        pcm = pcm[int(off * 16000): int(window[1] * 16000)]
    segs, _ = m.transcribe(pcm, language=cfg["language"], word_timestamps=True, condition_on_previous_text=False)
    lines = []
    for s in segs:
        words = [{"w": x.word.strip(), "s": round(x.start + off, 3), "e": round(x.end + off, 3), "p": round(x.probability, 3)}
                 for x in (s.words or []) if x.word.strip()]
        if words:
            lines.append({"start": words[0]["s"], "end": words[-1]["e"], "text": " ".join(x["w"] for x in words),
                          "words": words})
    return clean_lines(lines, cfg["language"])


def refine_fragment(path, lines, frag, cfg):
    """Second pass: the chosen window (+margin) is transcribed again with the bigger `whisper.refine_model`, and those lines replace the first-pass
    ones. Only recognition output is used, nothing is guessed. Any failure or a suspiciously empty answer keeps the first pass.
    Returns (lines, fragment, note)."""
    w = cfg["whisper"]
    name = w.get("refine_model")
    if not name or name == w["model"] or not frag:
        return lines, frag, ""
    lo, hi = frag["start"] - 0.5, frag["end"] + 0.5
    mid = lambda l: (l["start"] + l["end"]) / 2  # noqa: E731
    margin = w.get("refine_margin", 2.0)
    try:
        new = transcribe(path, cfg, name, (frag["start"] - margin, frag["end"] + margin))
    except Exception as e:  # noqa: BLE001 - model download / memory problems must not stop the song
        return lines, frag, f"refine with {name} failed: {type(e).__name__}: {str(e)[:80]}"
    new = [l for l in new if lo <= mid(l) <= hi]
    old_n = sum(len(l["words"]) for l in lines if lo <= mid(l) <= hi)
    new_n = sum(len(l["words"]) for l in new)
    if not new or new_n < 0.5 * old_n:
        return lines, frag, f"refine with {name} kept the first pass ({new_n} words vs {old_n})"
    out = sorted([l for l in lines if not lo <= mid(l) <= hi] + new, key=lambda l: l["start"])
    first, last = out.index(new[0]), out.index(new[-1])
    f = dict(frag, first=first, last=last, start=out[first]["start"], end=out[last]["end"])
    f["length"] = round(f["end"] - f["start"], 2)
    f["low_ratio"], f["max_gap"] = round(low_ratio(out, f, w["min_confidence"]), 3), round(max_gap(out, f), 1)
    return out, f, f'text refined with {name} (low-confidence {frag.get("low_ratio", 0):.0%} -> {f["low_ratio"]:.0%})'


def clean_lines(lines, lang):
    """Russian recognition sometimes hallucinates Latin tokens ('canceled', 'Вdablo'): drop them; lines left empty vanish."""
    if lang != "ru":
        return lines
    out = []
    for ln in lines:
        ws = [w for w in ln["words"] if not re.search(r"[A-Za-z]", w["w"])]
        if ws and not HALLUCINATION.search(" ".join(w["w"] for w in ws)):
            out.append({"start": ws[0]["s"], "end": ws[-1]["e"], "text": " ".join(w["w"] for w in ws), "words": ws})
    return out


def refragment(analysis, cfg, popular_line=""):
    """Re-clean saved lines and recompute chorus + fragment without running whisper again."""
    lines = clean_lines(analysis["lines"], cfg["language"])
    chorus = find_chorus(lines)
    return dict(analysis, lines=lines, fragment=pick_reliable(lines, popular_line, cfg, chorus))


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


def pick_fragment(lines, popular_line="", min_len=30, max_len=60, gap=0.6, chorus=None, anchor_idx=None):
    """Window of whole lines containing the most popular line (else the top chorus). Ends on a phrase boundary."""
    if not lines:
        return None
    chorus = chorus if chorus is not None else find_chorus(lines)
    anchor, reason = None, ""
    pin = popular_line.startswith("=")  # '=text' (from 'Artist - Title [text].mp3'): the fragment starts exactly at that line
    popular_line = popular_line.lstrip("=").strip()
    if anchor_idx is not None:  # a candidate window that starts exactly at this line (used when looking for a more reliable window)
        anchor, reason, pin = anchor_idx, "matched candidate line", True
    elif popular_line:
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


def low_ratio(lines, frag, thr):
    """Share of words in the fragment that whisper recognised with probability < thr (the same measure QA uses)."""
    ws = [w for ln in lines[frag["first"]: frag["last"] + 1] for w in ln["words"]]
    return sum(1 for w in ws if w["p"] < thr) / max(1, len(ws))


def max_gap(lines, frag):
    """Longest pause between two neighbouring lines inside the fragment (an instrumental break shows as an empty screen)."""
    return max((lines[k + 1]["start"] - lines[k]["end"] for k in range(frag["first"], frag["last"])), default=0.0)


def pick_reliable(lines, popular_line, cfg, chorus=None):
    """pick_fragment, but when the chosen window has too many low-confidence words, look for another window of the same song
    (nearest to the first choice) that stays under the limit. Words are never replaced or guessed: nothing fits -> the first choice is
    returned with `low_ratio` above the limit, and the caller refuses the song instead of rendering text the recogniser was unsure about."""
    thr, limit, gap_limit = cfg["whisper"]["min_confidence"], cfg["whisper"].get("max_low_ratio", 0.15), cfg["whisper"].get("max_gap_sec", 5.0)
    chorus = chorus if chorus is not None else find_chorus(lines)
    base = pick_fragment(lines, popular_line, cfg["min_len"], cfg["max_len"], chorus=chorus)
    if not base:
        return None
    base["low_ratio"], base["max_gap"] = round(low_ratio(lines, base, thr), 3), round(max_gap(lines, base), 1)
    if (base["low_ratio"] <= limit and base["max_gap"] <= gap_limit) or base.get("pinned"):  # a start pinned in the file name is the owner's choice
        return base
    best = None
    for i in sorted(range(len(lines)), key=lambda k: abs(k - base["first"])):
        c = pick_fragment(lines, "", cfg["min_len"], cfg["max_len"], chorus=chorus, anchor_idx=i)
        if c["length"] < cfg["min_len"]:
            continue
        c["low_ratio"], c["max_gap"] = round(low_ratio(lines, c, thr), 3), round(max_gap(lines, c), 1)
        if c["low_ratio"] <= limit and c["max_gap"] <= gap_limit:
            best = c
            break
    if best:
        best["pinned"] = False
        best["reason"] = (f'{base["reason"]}; moved to line {best["first"]}: first choice had {base["low_ratio"]:.0%} low-confidence words '
                          f'(limit {limit:.0%}) and a {base["max_gap"]:.0f}s pause (limit {gap_limit:.0f}s)')
        return best
    base["reason"] += f'; no window within limits: {base["low_ratio"]:.0%} low-confidence words (limit {limit:.0%}), {base["max_gap"]:.0f}s pause (limit {gap_limit:.0f}s)'
    return base


def analyze(path, popular_line="", cfg=None):
    cfg = cfg or load_config()
    lines = transcribe(path, cfg)
    b = beats(path)
    chorus = find_chorus(lines)
    frag = pick_reliable(lines, popular_line, cfg, chorus)
    lines, frag, note = refine_fragment(path, lines, frag, cfg)
    if note:
        frag["reason"] += "; " + note
    low = sum(1 for l in lines for w in l["words"] if w["p"] < cfg["whisper"]["min_confidence"])
    nwords = sum(len(l["words"]) for l in lines)
    summary = {"bpm": b["bpm"], "audio_duration": b["duration"], "lines": len(lines), "words": nwords,
               "low_confidence_words": low, "popular_line_found": bool(frag and "matched" in frag["reason"]),
               "fragment": frag and {k: frag[k] for k in ("start", "end", "length", "reason", "low_ratio")},
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
