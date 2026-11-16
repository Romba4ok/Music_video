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
    import subprocess

    import librosa
    import numpy as np
    # ffmpeg decodes (it is already required by check_audio): librosa's own mp3 reader (libsndfile) gives up on files with >64 KB of junk before the
    # first frame, e.g. a big cover in the ID3 tag, and then the whole song fails after check_audio had accepted it
    pcm = subprocess.run(["ffmpeg", "-v", "error", "-i", str(path), "-vn", "-ac", "1", "-ar", "22050", "-f", "f32le", "-"], capture_output=True, check=True).stdout
    y, sr = np.frombuffer(pcm, dtype=np.float32), 22050
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


def _best_popular(lines, popular):
    """`popular` may hold several candidate lines separated by '||' (TikTok analysis): the one that matches the transcript best wins."""
    best = (None, 0.0, popular.split("||")[0].strip())
    for p in (x.strip() for x in popular.split("||") if x.strip()):
        i, r = _match_popular(lines, p)
        if (i is not None, r) > (best[0] is not None, best[1]):
            best = (i, r, p)
    return best


OPEN_WORDS = {"и", "а", "но", "что", "как", "чтобы", "если", "когда", "пока", "я", "ты", "мы", "он", "она", "в", "на", "с", "к", "от", "не", "ни", "же", "бы", "по", "за", "из", "у", "о", "для"}
CONT_WORDS = {"и", "а", "но", "да", "или", "что", "как", "чтобы", "когда", "пока", "если", "ведь", "зато", "потому"}  # a line that starts so continues the previous one


def _close_kind(lines, j, chorus):
    """How well line j ends a thought: 'strong' (end of the song / a repeated chorus block / sentence mark + pause / a pause of 2 s+),
    'weak' (a plain pause of 1 s+) or None (open: ends on a comma or a hanging word, or the next line goes on with «и», «а», «но»...).
    A pause alone proves nothing: a song pauses in the middle of a sentence (instrumental gap between «…хлопнет дверь» and «И дрогнут провода»)."""
    if j + 1 >= len(lines) or any(b["last"] == j for b in chorus):
        return "strong"
    t, pause = lines[j]["text"].strip(), lines[j + 1]["start"] - lines[j]["end"]
    last, nxt = (norm(t).split() or [""])[-1], (norm(lines[j + 1]["text"]).split() or [""])[0]
    if t[-1:] in ".!?…" and pause >= .6:
        return "strong"
    if t.endswith(",") or last in OPEN_WORDS:
        return "strong" if pause >= 4.0 else None
    if nxt in CONT_WORDS and pause < 4.0:
        return None
    return "strong" if pause >= 2.0 else "weak" if pause >= 1.0 else None


def _close_thought(lines, first, last, anchor, min_len, limit, chorus, lookahead=12.0):
    """Move the end to where the thought is finished. Forward (the video may be up to `limit` s long) to the nearest closing line; a weak
    closing is dropped for a strong one that follows within `lookahead` s. Nothing closes in reach -> back to the last closing line that keeps
    min_len and the popular line; otherwise unchanged."""
    def length(b):
        return lines[b]["end"] - lines[first]["start"]
    j, weak = last, None
    while j < len(lines):
        k = _close_kind(lines, j, chorus)
        if k == "strong":
            return j
        if k == "weak" and weak is None:
            weak = j
        if weak is not None and lines[j]["end"] - lines[weak]["end"] > lookahead:
            return weak
        if j + 1 < len(lines) and length(j + 1) <= limit:
            j += 1
            continue
        break
    if weak is not None:
        return weak
    for k in range(min(j, len(lines) - 1), max(first, anchor) - 1, -1):
        if length(k) >= min_len and _close_kind(lines, k, chorus):
            return k
    return last


def pick_fragment(lines, popular_line="", min_len=30, max_len=60, gap=0.6, chorus=None, anchor_idx=None, overrun=0.0):
    """Window of whole lines containing the most popular line (else the top chorus). Ends on a phrase boundary."""
    if not lines:
        return None
    chorus = chorus if chorus is not None else find_chorus(lines)
    anchor, reason = None, ""
    file_pin = popular_line.startswith("=")
    pin = file_pin  # '=text' (from 'Artist - Title [text].mp3'): the fragment starts exactly at that line
    popular_line = popular_line.lstrip("=").strip()
    if anchor_idx is not None:  # a candidate window that starts exactly at this line (used when looking for a more reliable window)
        anchor, reason, pin = anchor_idx, "matched candidate line", True
    elif popular_line:
        anchor, ratio, popular_line = _best_popular(lines, popular_line)
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
    owner_pin = file_pin and pin  # the owner chose the start in the file name: the end is not moved either
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
    while (not owner_pin and first > 0 and (norm(lines[first]["text"]).split() or [""])[0] in CONT_WORDS  # starts on «И…», «А…»: the sentence began one line earlier
           and lines[first]["start"] - lines[first - 1]["end"] < 4.0 and length(first - 1, last) <= max_len + overrun):
        first -= 1
    # stop at a phrase boundary: extend (within max_len) until the pause after the last line is >= gap
    while last + 1 < len(lines) and lines[last + 1]["start"] - lines[last]["end"] < gap and length(first, last + 1) <= max_len:
        last += 1
    if not owner_pin:  # no start typed by the owner: end where the thought is finished, not where the clock ran out (may run `overrun` s past max_len)
        last = _close_thought(lines, first, last, anchor, min_len, max_len + overrun, chorus)
    return {"first": first, "last": last, "start": lines[first]["start"], "end": lines[last]["end"], "end_kind": _close_kind(lines, last, chorus),
            "length": round(length(first, last), 2), "reason": reason + ("; start pinned by file name" if pin else ""), "pinned": pin}


def ensure_min_len(lines, frag, cfg):
    """A fragment shorter than `min_len` is a video that QA will refuse after a full render (12.6 s of lyrics + 2.5 s end card = 15.1 s < 20 s).
    Every way to such a window is closed here: the window grows over neighbouring REAL lines, forward first (a pinned start stays), then backward
    (a pin is moved only when nothing else is left, and the reason says so), never past max_len + close_overrun. If the song has no more lyrics in reach
    the fragment is returned unchanged with `short` set: the caller adds real audio around it (script_gen.fit_duration) or refuses the song."""
    if not frag:
        return frag
    min_len, limit = cfg["min_len"], cfg["max_len"] + cfg.get("close_overrun", 8.0)
    first, last = frag["first"], frag["last"]

    def length(a, b):
        return lines[b]["end"] - lines[a]["start"]

    if length(first, last) >= min_len:
        return frag
    moved_start = False
    while length(first, last) < min_len:
        if last + 1 < len(lines) and length(first, last + 1) <= limit:
            last += 1
        elif first > 0 and length(first - 1, last) <= limit:
            first -= 1
            moved_start = True
        else:
            break
    if (first, last) == (frag["first"], frag["last"]):
        return dict(frag, short=True, reason=frag.get("reason", "") + f"; shorter than min_len ({frag['length']:.1f}s < {min_len}s) and no more lyrics in reach")
    new = dict(frag, first=first, last=last, start=lines[first]["start"], end=lines[last]["end"], length=round(length(first, last), 2))
    new["pinned"] = bool(frag.get("pinned")) and not moved_start
    new["short"] = new["length"] < min_len
    new["reason"] = frag.get("reason", "") + f"; extended to lines {first}..{last} ({new['length']:.1f}s) to reach min_len {min_len}s" + ("; pinned start moved" if moved_start and frag.get("pinned") else "")
    thr = cfg["whisper"]["min_confidence"]
    new["low_ratio"], new["max_gap"] = round(low_ratio(lines, new, thr), 3), round(max_gap(lines, new), 1)
    return new


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
    over = cfg.get("close_overrun", 8.0)
    base = pick_fragment(lines, popular_line, cfg["min_len"], cfg["max_len"], chorus=chorus, overrun=over)
    if not base:
        return None
    base = ensure_min_len(lines, base, cfg)
    base["low_ratio"], base["max_gap"] = round(low_ratio(lines, base, thr), 3), round(max_gap(lines, base), 1)
    if (base["low_ratio"] <= limit and base["max_gap"] <= gap_limit) or base.get("pinned"):  # a start pinned in the file name is the owner's choice
        return base
    best = None
    for i in sorted(range(len(lines)), key=lambda k: abs(k - base["first"])):
        c = pick_fragment(lines, "", cfg["min_len"], cfg["max_len"], chorus=chorus, anchor_idx=i, overrun=over)
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
    w, refined = cfg["whisper"], False
    if popular_line and frag and "moved to line" in frag.get("reason", ""):
        # the window with the popular line was too unsure for the small model: the big one may read it reliably, so try that before giving the line up
        base = pick_fragment(lines, popular_line, cfg["min_len"], cfg["max_len"], chorus=chorus, overrun=cfg.get("close_overrun", 8.0))
        l2, f2, n2 = refine_fragment(path, lines, base, cfg) if base else (lines, None, "")
        if (f2 and "refined" in n2 and f2.get("low_ratio", 1) <= w.get("max_low_ratio", 0.15) and f2.get("max_gap", 0) <= w.get("max_gap_sec", 5.0)):
            lines, frag, note, refined = l2, dict(f2, pinned=False), n2 + "; the popular line is reliable after the second pass", True
    if not refined:
        lines, frag, note = refine_fragment(path, lines, frag, cfg)
    if note:
        frag["reason"] += "; " + note
    frag = ensure_min_len(lines, frag, cfg)  # the second recognition pass can drop edge lines and shorten the window
    low = sum(1 for l in lines for w in l["words"] if w["p"] < cfg["whisper"]["min_confidence"])
    nwords = sum(len(l["words"]) for l in lines)
    summary = {"bpm": b["bpm"], "audio_duration": b["duration"], "lines": len(lines), "words": nwords,
               "low_confidence_words": low, "popular_line_found": bool(frag and "matched" in frag["reason"]),
               "fragment": frag and {k: frag[k] for k in ("start", "end", "length", "reason", "low_ratio", "short") if k in frag},
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
