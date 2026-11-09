"""Automatic QA. Each check returns (state, name, detail); state is PASS | FAIL | SKIP (SKIP is never 'verified')."""
import json
import re
import subprocess

PALETTES = {"cold", "warm", "dusk", "contrast"}
METAPHORS = {"breakup", "loneliness", "love", "nostalgia", "money", "time", "inner"}


def max_total(cfg):
    """Longest allowed video: max_len, plus what a fragment may run over to finish its thought (close_overrun) and the intro + tail around it."""
    return cfg["max_len"] + cfg.get("close_overrun", 8.0) + 4


def validate_spec(spec, cfg):
    errs = []
    for k in ("id", "mode", "song", "metaphor", "palette", "caption", "hashtags", "ai_label"):
        if k not in spec:
            errs.append(f"missing {k}")
    if errs:
        return errs
    if spec["mode"] not in ("with_audio", "tiktok", "commentary"):
        errs.append("mode must be with_audio|tiktok|commentary")
    if spec["metaphor"] not in METAPHORS:
        errs.append(f"metaphor not in {sorted(METAPHORS)}")
    if spec["palette"] not in PALETTES:
        errs.append(f"palette not in {sorted(PALETTES)}")
    if len(spec["caption"]) > 150:
        errs.append("caption > 150 chars")
    tags = spec["hashtags"]
    if not (3 <= len(tags) <= 5) or not all(t.startswith("#") for t in tags):
        errs.append("hashtags: 3-5 items starting with #")
    if spec["ai_label"] is not True:
        errs.append("ai_label must be true")
    from .widgets_plan import KINDS
    for w in spec.get("widgets") or []:
        ln = w.get("lines")
        if not (isinstance(ln, list) and ln and all(isinstance(x, int) and x >= 0 for x in ln)) or w.get("kind", "scene") not in KINDS:
            errs.append(f"widget invalid (lines=[int..], kind in {list(KINDS)}): {str(w)[:80]}")
    if spec["mode"] == "commentary":
        sc = spec.get("scenes") or []
        if not sc:
            errs.append("commentary needs scenes")
        t = 0
        for s in sc:
            if abs(s["start"] - t) > 1e-6:
                errs.append("scenes not contiguous")
                break
            t = s["start"] + s["dur"]
        if sc and not (cfg["min_len"] <= round(t) <= max_total(cfg)):
            errs.append("total duration outside min_len..max_len")
    return errs


def _run(cmd):
    r = subprocess.run(cmd, capture_output=True, text=True)
    return (r.stdout or "") + (r.stderr or "")


def probe(path):
    out = _run(["ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json", str(path)])
    return json.loads(out)


def loudness(path):
    out = _run(["ffmpeg", "-nostats", "-i", str(path), "-af", "ebur128=peak=true", "-f", "null", "-"])
    tail = out[out.rfind("Summary:"):]
    i = re.search(r"I:\s+(-?[\d.]+) LUFS", tail)
    p = re.search(r"Peak:\s+(-?[\d.]+) dBFS", tail)
    return (float(i.group(1)) if i else None, float(p.group(1)) if p else None)


def black_frames(path):
    out = _run(["ffmpeg", "-nostats", "-i", str(path), "-vf", "blackdetect=d=0.3:pix_th=0.05", "-an", "-f", "null", "-"])
    return [float(m) for m in re.findall(r"black_start:([\d.]+)", out)]


PIC = (780, 280, 150, 740)  # w, h, x, y of the picture area inside every card (video pixels), well inside the 820x340 body
STATIC_MAX = 0.25  # share of cards allowed to sit still; a picture that does not change for 0.5 s is "frame by frame" for the viewer
STILL_DIFF = 3.0  # mean grey-level change (0-255) over 0.5 s below which a card picture counts as still


def _grey(video, t):
    w, h, x, y = PIC
    r = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{t:.2f}", "-i", str(video), "-frames:v", "1", "-vf", f"crop={w}:{h}:{x}:{y},scale=195:70,format=gray",
                        "-f", "rawvideo", "-"], capture_output=True)
    return r.stdout


def motion_levels(video, cards):
    """Mean grey-level change of each card's picture between two frames 0.5 s apart (one second into the card). None = card too short to tell."""
    out = []
    for c in cards:
        t = c["start"] + min(1.0, max(0.3, c["end"] - c["start"] - 0.7))  # one second in, earlier on a short card
        if c["end"] - t < 0.6:
            out.append(None)
            continue
        a, b = _grey(video, t), _grey(video, t + 0.5)
        out.append(sum(abs(x - y) for x, y in zip(a, b)) / max(1, min(len(a), len(b))) if a and b else None)
    return out


def run_checks(spec, video, plan, cfg):
    res = []
    add = lambda ok, name, d="": res.append(("PASS" if ok else "FAIL", name, d))
    skip = lambda name, why: res.append(("SKIP", name, why))
    errs = validate_spec(spec, cfg)
    add(not errs, "spec_valid", "; ".join(errs))
    info = probe(video)
    v = next((s for s in info["streams"] if s["codec_type"] == "video"), {})
    a = next((s for s in info["streams"] if s["codec_type"] == "audio"), None)
    num, den = (v.get("r_frame_rate", "0/1").split("/") + ["1"])[:2]
    fps = float(num) / float(den or 1)
    add((v.get("width"), v.get("height")) == (cfg["width"], cfg["height"]) and abs(fps - cfg["fps"]) < .1 and v.get("codec_name") == "h264",
        "media_format", f'{v.get("width")}x{v.get("height")} {fps:.2f}fps {v.get("codec_name")}')
    dur = float(info["format"]["duration"])
    exp = plan["duration"]
    add(cfg["min_len"] <= dur <= max_total(cfg) and abs(dur - exp) <= 0.25, "duration", f"{dur:.2f}s (expected {exp}s, {cfg['min_len']}-{max_total(cfg):g})")
    if spec["mode"] == "with_audio":
        if a is None:
            add(False, "audio", "no audio track")
        else:
            adur = float(a.get("duration") or dur)
            lufs, peak = loudness(video)
            ok = a["codec_name"] == "aac" and abs(adur - dur) <= 0.15 and lufs is not None and abs(lufs - cfg["target_lufs"]) <= 2.5 \
                and peak is not None and peak <= cfg["max_true_peak"] + 0.3
            add(ok, "audio", f"aac={a['codec_name']} len_diff={abs(adur - dur):.2f}s lufs={lufs} peak={peak}")
    else:
        skip("audio", f"{spec['mode']} mode: no audio in the file (sound is added in TikTok)")
        if a is not None:
            add(False, "no_embedded_audio", "this mode must not contain audio")
    bl = black_frames(video)
    add(not bl, "no_black_frames", f"black at {bl[:3]}" if bl else "")
    cards = [s for s in plan["scenes"] if s["role"] == "lyric"]
    overlap = [i for i, (x, y) in enumerate(zip(plan["scenes"], plan["scenes"][1:])) if x["end"] > y["start"] + 1e-6]
    add(not overlap, "no_card_overlap", f"cards {overlap[:5]}" if overlap else "")
    from .widgets_plan import HOLD_MAX
    empty = [(round(x["end"] + HOLD_MAX, 1), round(y["start"], 1)) for x, y in zip(plan["scenes"], plan["scenes"][1:]) if y["start"] - x["end"] - HOLD_MAX > 0.4]
    add(not empty, "no_empty_stage", f"no card between {empty[:3]} (s)" if empty else "")  # a card is held HOLD_MAX s past its line; a longer pause leaves the stage bare
    if spec["mode"] in ("with_audio", "tiktok") and cards:
        words = sum(len(c["words"]) for c in cards)
        low = sum(len(c["low_conf"]) for c in cards)
        ratio = low / max(1, words)
        limit = cfg["whisper"].get("max_low_ratio", 0.15)
        add(ratio <= limit, "lyrics_confidence", f"{low}/{words} low-confidence words ({ratio:.0%}); limit {limit:.0%}")
        short = [i for i, c in enumerate(cards) if c["end"] - c["start"] < 0.5]
        add(not short, "cards_readable", f"too short: {short[:5]}" if short else "")
    else:
        skip("lyrics_confidence", "no lyrics (commentary)")
    if cards:
        lv = motion_levels(video, cards)
        known = [x for x in lv if x is not None]
        still = [i for i, x in enumerate(lv) if x is not None and x < STILL_DIFF]
        add(not known or len(still) <= STATIC_MAX * len(known), "cards_move",
            f"{len(still)}/{len(known)} card pictures nearly still (cards {still[:6]}); levels {[None if x is None else round(x, 1) for x in lv]}")
    return res
