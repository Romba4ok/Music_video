"""Download audio only from allowed sources, or extract audio from local files the owner has rights to.

- direct download: only candidates whose license passed the policy (cc0/pdm/by) or local files
- yt-dlp: only allowlisted domains AND only when the page's own metadata declares an allowed license
- local video -> audio: requires the explicit rights flag; the file is never fetched from anywhere
A `<file>.license.json` sidecar (attribution, license, source) is written next to every download.
"""
import hashlib
import json
import re
import shutil
import subprocess
import time
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.parse import urlparse

import requests

from .common import HTTP_LOG, Refused, license_ok, load_config, safe_err, status

MAX_BYTES = 80 * 1024 * 1024
AUDIO_SUFFIXES = (".mp3", ".wav", ".ogg", ".flac", ".m4a")
AUDIO_CONTENT_TYPES = {
    "audio/mpeg": ".mp3", "audio/mp3": ".mp3", "audio/wav": ".wav", "audio/x-wav": ".wav",
    "application/ogg": ".ogg", "audio/ogg": ".ogg", "audio/flac": ".flac", "audio/x-flac": ".flac",
    "audio/mp4": ".m4a", "audio/x-m4a": ".m4a",
}


def _slug(s):
    return re.sub(r"[^\w\-. ]+", "", s, flags=re.U).strip()[:80] or "track"


def _sidecar(path, data):
    Path(str(path) + ".license.json").write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")


def file_sha256(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def stream_audio(open_response, path, max_bytes, retries=2):
    """Retry transient failures of the HTTP request or its body, starting from byte zero."""
    for attempt in range(retries + 1):
        response = None
        try:
            with open_response() as response:
                response.raise_for_status()
                content_type = response.headers.get("Content-Type", "").split(";", 1)[0].strip().lower()
                if content_type.startswith("text/") or "html" in content_type or "json" in content_type:
                    raise Refused(f"response is not audio: {content_type}")
                if (response.headers.get("Content-Length") or "").isdigit() and int(response.headers["Content-Length"]) > max_bytes:
                    raise Refused("file too large")
                size = 0
                digest = hashlib.sha256()
                with path.open("wb") as output:
                    for chunk in response.iter_content(65536):
                        size += len(chunk)
                        if size > max_bytes:
                            raise Refused("file too large")
                        digest.update(chunk)
                        output.write(chunk)
                if not size:
                    raise Refused("empty audio response")
                return digest.hexdigest()
        except requests.RequestException as exc:
            code = getattr(exc.response, "status_code", 0)
            transient = code in (408, 500, 502, 503, 504) or isinstance(
                exc, (requests.Timeout, requests.ConnectionError, requests.exceptions.ChunkedEncodingError)
            )
            if not transient or attempt == retries or (response is not None and response.headers.get("Retry-After")):
                raise
            time.sleep(2 ** attempt)


def download(c, dest_dir, cfg=None, http=requests, *, download_only=False):
    cfg = cfg or load_config()
    dest = Path(dest_dir)
    dest.mkdir(parents=True, exist_ok=True)
    if c.source == "local":
        out = dest / Path(c.local_path).name
        if Path(c.local_path).resolve() != out.resolve():
            shutil.copy2(c.local_path, out)
        return ensure_audio(out, rights_confirmed=c.rights_declared)
    if not download_only and not license_ok(c.license or c.license_url, cfg["licenses_allowed"]):
        raise Refused(f"license not allowed: {c.license!r}")
    if urlparse(c.url).scheme != "https":
        raise Refused("only https downloads")
    suffix = ".mp3"

    def open_response():
        nonlocal suffix
        host = urlparse(c.url).hostname
        try:
            response = http.get(c.url, stream=True, timeout=30, headers={"User-Agent": "vybex-fetch/1.0"})
        except requests.RequestException as exc:
            HTTP_LOG.append((host, type(exc).__name__))
            raise
        HTTP_LOG.append((host, response.status_code))
        content_type = response.headers.get("Content-Type", "").split(";", 1)[0].strip().lower()
        url_suffix = Path(urlparse(getattr(response, "url", None) or c.url).path).suffix.lower()
        if url_suffix == ".oga":
            url_suffix = ".ogg"
        suffix = AUDIO_CONTENT_TYPES.get(content_type, url_suffix if url_suffix in AUDIO_SUFFIXES else ".mp3")
        return response

    with TemporaryDirectory(dir=dest) as staging:
        partial = Path(staging) / "download.part"
        digest = stream_audio(open_response, partial, MAX_BYTES)
        staged = partial.rename(Path(staging) / f"{_slug(c.artist)} - {_slug(c.title)}{suffix}")
        metadata = {"attribution": c.attribution(), "license": c.license,
                    "source": c.landing or c.url, "sha256": digest}
        if download_only:
            metadata.update(usage_rights="not_evaluated", download_only=True, analysis_only=True)
        _sidecar(staged, metadata)
        return publish_audio(staged, staged, dest)


def publish_audio(raw, validated, dest):
    """Move the usable file and its source metadata out of the staging directory."""
    dest.mkdir(parents=True, exist_ok=True)
    final = dest / (raw.stem + validated.suffix)
    validated.replace(final)
    side = Path(str(raw) + ".license.json")
    if side.exists():
        side.replace(Path(str(final) + ".license.json"))
    return final


def download_first(cands, dest_dir, cfg=None, http=requests):
    """Return the first usable audio file and the outcomes of the candidates tried."""
    cfg = cfg or load_config()
    dest = Path(dest_dir)
    dest.mkdir(parents=True, exist_ok=True)
    sts = []
    for c in cands:
        try:
            if c.source == "local":
                p = download(c, dest, cfg, http)
                check_audio(p, min_sec=cfg.get("min_len", 20))
            else:
                with TemporaryDirectory(dir=dest) as staging:
                    raw = download(c, staging, cfg, http)
                    digest = file_sha256(raw)
                    checked, _ = check_audio(raw, min_sec=cfg.get("min_len", 20), fixdir=Path(staging) / "fixed")
                    duplicate = find_duplicate(dest, raw, digest)
                    if duplicate:
                        if duplicate.stem != raw.stem:
                            raise Refused("same audio already saved under another name")
                        p = duplicate
                    else:
                        p = publish_audio(raw, checked, dest)
            sts.append(status(c.source, "ok", c.title))
            return p, sts
        except (Refused, BadAudio) as e:
            sts.append(status(c.source, "refused", str(e)))
        except Exception as e:
            sts.append(status(c.source, "unavailable", safe_err(e)))
    return None, sts


def find_duplicate(dest, raw, digest):
    """Find bytes already saved, including the original digest of a repaired download."""
    size = raw.stat().st_size
    for path in dest.iterdir():
        if path.suffix.lower() not in AUDIO_SUFFIXES or not path.is_file():
            continue
        side = Path(str(path) + ".license.json")
        try:
            if json.loads(side.read_text(encoding="utf-8")).get("sha256") == digest:
                return path
        except (OSError, ValueError, AttributeError):
            pass
        if path.stat().st_size == size and file_sha256(path) == digest:
            return path
    return None


def ytdlp_download(url, dest_dir, cfg=None, ydl_cls=None):
    cfg = cfg or load_config()
    host = (urlparse(url).hostname or "").lower()
    if not any(host == d or host.endswith("." + d) for d in cfg["sources"]["ytdlp_allowed_domains"]):
        raise Refused(f"domain not allowlisted: {host}")
    if ydl_cls is None:
        from yt_dlp import YoutubeDL as ydl_cls
    dest = Path(dest_dir)
    dest.mkdir(parents=True, exist_ok=True)
    with ydl_cls({"quiet": True, "skip_download": True, "noplaylist": True}) as y:
        info = y.extract_info(url, download=False)
    lic = info.get("license") or ""
    if not license_ok(lic, cfg["licenses_allowed"]):
        raise Refused(f"page does not declare an allowed license (got {lic!r})")
    opts = {"quiet": True, "noplaylist": True, "format": "bestaudio/best",
            "outtmpl": str(dest / "%(id)s.%(ext)s")}
    with ydl_cls(opts) as y:
        info = y.extract_info(url, download=True)
        path = Path(y.prepare_filename(info))
    _sidecar(path, {"attribution": f'"{info.get("title")}" by {info.get("uploader")} ({info.get("webpage_url")})',
                    "license": lic, "source": info.get("webpage_url")})
    return ensure_audio(path, rights_confirmed=True)  # license verified above


VIDEO_EXT = {".mp4", ".mov", ".mkv", ".webm", ".m4v", ".avi"}


def extract_local_audio(video, dest_dir, rights_confirmed=False):
    """ffmpeg: audio track of a LOCAL video file. Needs the explicit rights flag.
    If the video has a license sidecar (from a verified download) it is carried over to the audio file."""
    if not rights_confirmed:
        raise Refused("pass rights_confirmed=True (--i-have-rights): you must have the right to use this file")
    video = Path(video)
    if not video.is_file():
        raise FileNotFoundError(video)
    dest = Path(dest_dir)
    dest.mkdir(parents=True, exist_ok=True)
    out = dest / (video.stem + ".m4a")
    r = subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(video), "-vn", "-c:a", "aac", "-b:a", "192k", str(out)],
                       capture_output=True, text=True)
    if r.returncode or not out.exists():
        raise RuntimeError("ffmpeg could not extract an audio track: " + (r.stderr or "")[-200:])
    side = Path(str(video) + ".license.json")
    data = json.loads(side.read_text(encoding="utf-8")) if side.exists() else \
        {"license": "owner-supplied", "source": str(video), "rights_confirmed": True}
    data["extracted_from"] = video.name
    _sidecar(out, data)
    return out


def ensure_audio(path, rights_confirmed=False):
    """Any legally obtained file -> audio. Video containers are converted with ffmpeg, audio files pass through."""
    path = Path(path)
    if path.suffix.lower() in VIDEO_EXT:
        return extract_local_audio(path, path.parent, rights_confirmed)
    return path


class BadAudio(Exception):
    """The file is not usable audio (unreadable, no audio stream, too short, or damaged beyond repair)."""


def _decode_report(path):
    """(duration_from_container, decoded_seconds, decoder_error_lines) via ffprobe + a full ffmpeg decode to nowhere."""
    pr = subprocess.run(["ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json", str(path)],
                        capture_output=True, text=True, encoding="utf-8", errors="replace")
    try:
        info = json.loads(pr.stdout or "{}")
    except ValueError:
        info = {}
    if pr.returncode or not info.get("streams"):
        raise BadAudio("ffprobe cannot read the file: " + ((pr.stderr or "").strip()[-150:] or "no streams"))
    if not any(s.get("codec_type") == "audio" for s in info["streams"]):
        raise BadAudio("no audio stream")
    try:
        dur = float(info["format"]["duration"])
    except (KeyError, TypeError, ValueError):
        raise BadAudio("container has no duration") from None
    dr = subprocess.run(["ffmpeg", "-v", "error", "-nostats", "-i", str(path), "-vn", "-progress", "pipe:1", "-f", "null", "-"],
                        capture_output=True, text=True, encoding="utf-8", errors="replace")
    done = [int(x.split("=")[1]) for x in (dr.stdout or "").splitlines() if x.startswith("out_time_us=") and x.split("=")[1].lstrip("-").isdigit()]
    errs = [ln for ln in (dr.stderr or "").splitlines() if ln.strip()]
    if dr.returncode:
        raise BadAudio("ffmpeg cannot decode the file: " + (errs[-1][-150:] if errs else f"exit {dr.returncode}"))
    return dur, (max(done) / 1e6 if done else 0.0), errs


def check_audio(path, min_sec=20.0, max_sec=1500.0, fixdir=None):
    """Validate an audio file before it is analysed. Returns (usable_path, notes).
    - unreadable / no audio / shorter than min_sec / longer than max_sec -> BadAudio
    - decoder complaints (e.g. 'Illegal Audio-MPEG-Header', 'Header missing') but >= 95% of the track decodes -> accepted, noted
    - less than 95% decodes -> one re-encode with ffmpeg (bad frames dropped) into fixdir; the copy must pass the same test."""
    path = Path(path)
    dur, got, errs = _decode_report(path)
    notes = [f"{len(errs)} decoder warning(s): {errs[0][-110:]}"] if errs else []
    if got < 0.95 * dur:
        fixdir = Path(fixdir or Path(__file__).resolve().parent.parent / "out" / "audio-fixed")
        fixdir.mkdir(parents=True, exist_ok=True)
        fixed = fixdir / (path.stem + ".fixed.m4a")
        r = subprocess.run(["ffmpeg", "-y", "-v", "error", "-err_detect", "ignore_err", "-i", str(path), "-vn", "-c:a", "aac", "-b:a", "192k", str(fixed)],
                           capture_output=True, text=True, encoding="utf-8", errors="replace")
        if r.returncode or not fixed.exists():
            raise BadAudio(f"damaged ({got:.0f}s of {dur:.0f}s decode) and ffmpeg could not repair it")
        try:
            dur2, got2, _ = _decode_report(fixed)
        except BadAudio as e:
            raise BadAudio(f"damaged and the repaired copy is bad too: {e}") from None
        if got2 < 0.95 * dur2:
            raise BadAudio(f"damaged beyond repair ({got:.0f}s of {dur:.0f}s decode)")
        notes.append(f"damaged file ({got:.0f}s of {dur:.0f}s decoded): re-encoded to {fixed.name}")
        side = Path(str(path) + ".license.json")
        if side.exists():
            shutil.copy2(side, str(fixed) + ".license.json")
        path, dur = fixed, dur2
    if dur < min_sec:
        raise BadAudio(f"track is {dur:.0f}s, shorter than the {min_sec:.0f}s a clip needs")
    if dur > max_sec:
        raise BadAudio(f"track is {dur:.0f}s, longer than {max_sec:.0f}s (probably not a single song)")
    return path, notes


if __name__ == "__main__":
    import argparse
    import sys
    ap = argparse.ArgumentParser()
    ap.add_argument("what", choices=["url", "video"])
    ap.add_argument("target")
    ap.add_argument("--dest", default="accounts/main/audio")
    ap.add_argument("--i-have-rights", action="store_true")
    a = ap.parse_args()
    try:
        p = ytdlp_download(a.target, a.dest) if a.what == "url" else extract_local_audio(a.target, a.dest, a.i_have_rights)
        print("OK", p)
    except Refused as e:
        print("REFUSED", e)
        sys.exit(2)
