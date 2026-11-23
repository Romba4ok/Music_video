"""Check downloaded audio against the requested song before it leaves staging."""
import json
import re
import subprocess
from difflib import SequenceMatcher
from functools import lru_cache

import requests

from . import sources
from .analyze import HALLUCINATION, _pcm16k
from .common import Refused, get_json


@lru_cache(maxsize=128)
def _references(artist, title):
    lead, track, _ = sources.split_credits(artist, title)
    rows = get_json("https://lrclib.net/api/search", {"artist_name": lead, "track_name": track},
                    timeout=6, retries=1)
    if not isinstance(rows, list):
        raise ValueError("unexpected lyrics service response")
    texts = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        candidate = sources.Candidate("lrclib", row.get("trackName") or "", row.get("artistName") or "")
        lyrics = row.get("plainLyrics")
        if sources.matches(artist, title, candidate, collaborations=True) and isinstance(lyrics, str) and lyrics.strip():
            texts.append(lyrics)
    return tuple(dict.fromkeys(texts))


def _check_tags(path, artist, title):
    try:
        result = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format_tags=artist,title",
                                 "-of", "json", str(path)], capture_output=True, timeout=15)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise Refused("identity:unavailable (could not read audio metadata)") from exc
    if result.returncode:
        raise Refused("identity: unreadable audio metadata")
    tags = {k.lower(): v for k, v in json.loads(result.stdout).get("format", {}).get("tags", {}).items()}
    tagged_title = tags.get("title") or title
    if tagged_title != title:
        # These catalogs append their domain to the ID3 title, including on original recordings.
        tagged_title = re.sub(r"\s+\((?:muzlap|muzvoy)\.com\)\s*\Z", "", tagged_title, flags=re.I)
    embedded = sources.Candidate("tags", tagged_title, tags.get("artist") or artist)
    if not sources.matches(artist, title, embedded, collaborations=True):
        raise Refused("identity: embedded artist, guests or title differ from the requested recording")


@lru_cache(maxsize=1)
def _model():
    from faster_whisper import WhisperModel
    return WhisperModel("small", device="cpu", compute_type="int8")


def _samples(path, language):
    pcm = _pcm16k(path)
    size = min(len(pcm), 30 * 16000)
    for fraction in (0.25, 0.68):
        start = int((len(pcm) - size) * fraction)
        segments, _ = _model().transcribe(pcm[start:start + size], language=language, beam_size=1,
                                          condition_on_previous_text=False)
        yield " ".join(s.text for s in segments if s.avg_logprob >= -1 and s.no_speech_prob < 0.6
                       and not HALLUCINATION.search(s.text))


def _overlap(sample, reference, hook=False):
    ref = sources._words(reference)
    blocks = SequenceMatcher(None, sources._words(sample), ref, autojunk=False).get_matching_blocks()
    if hook:
        return len(set(ref)) >= 4 and any(b.size == len(ref) for b in blocks)
    words = [word for b in blocks if b.size >= 3 for word in ref[b.b:b.b + b.size]]
    return len(words) >= 8 and len(set(words)) >= 6


def verify(path, artist, title, hook="", language=None):
    _check_tags(path, artist, title)
    hooks = [line for line in hook.split("||") if len(set(sources._words(line))) >= 4]
    lookup_failed = False
    try:
        texts = _references(artist, title)
    except (requests.RequestException, ValueError):
        if not hooks:
            raise Refused("lyrics:unavailable (reference lookup failed)") from None
        lookup_failed = True
        texts = ()
    if not texts and not hooks:
        raise Refused("lyrics: no reference for the requested artist and title")
    try:
        for sample in _samples(path, language):
            if any(_overlap(sample, line, hook=True) for line in hooks):
                return "queue lyrics matched"
            if any(_overlap(sample, text) for text in texts):
                return "LRCLIB lyrics matched"
    except (OSError, RuntimeError, ValueError, subprocess.SubprocessError, ImportError) as exc:
        raise Refused(f"lyrics:unavailable (transcription failed: {type(exc).__name__})") from exc
    if lookup_failed:
        raise Refused("lyrics:unavailable (reference lookup failed and queue line was not confirmed)")
    raise Refused("lyrics: sampled vocals did not confirm the requested song")
