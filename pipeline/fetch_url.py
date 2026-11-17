"""Direct-URL audio download: one https/http link -> verified audio file in the out dir (Drive upload and the memory are done by the workflow / `songs`).

Gates, in this order (any failure = Refused with the reason, nothing is saved):
  1. rights: a license in `licenses_allowed` (cc0 / pdm / by) given for this link, OR rights=owner together with the standing owner declaration
     VYBEX_OWNER_DECLARES_RIGHTS=1 (a link the owner wrote into queue.md);
  2. host allowlist `direct_urls.allowed_hosts` (config.json), re-checked on EVERY redirect hop, so a redirect cannot leave the list;
  3. HTTP: timeouts, retries on 5xx/connection errors, 3xx followed by hand (max `max_redirects`), size cap, not text/html;
  4. ffprobe: the container really is mp3/wav/flac/m4a (a renamed HTML/exe is refused), has an audio stream, decodes, duration within min_sec..max_sec;
  5. duplicates: the same sha256 (or the same artist+title) is never saved twice.
No authentication, paywall, DRM or access limit is bypassed: a link that needs any of these simply fails.

python -m pipeline url <URL> --artist A --title T [--license by | --rights owner] [--out out/fetched] [--state out/songs-memory.md]
"""
import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path
from urllib.parse import unquote, urljoin, urlparse

import requests

from . import download
from .common import Refused, license_ok, load_config, parse_name, safe_err
from .fetch_songs import key, load_memory, save_memory, to_mp3

EXT_BY_TYPE = {"audio/mpeg": ".mp3", "audio/mp3": ".mp3", "audio/wav": ".wav", "audio/x-wav": ".wav", "audio/wave": ".wav", "audio/flac": ".flac",
               "audio/x-flac": ".flac", "audio/mp4": ".m4a", "audio/x-m4a": ".m4a", "audio/aac": ".m4a", "application/octet-stream": ""}
FORMAT_OF = {".mp3": "mp3", ".wav": "wav", ".flac": "flac", ".m4a": "mp4"}  # substring of ffprobe format_name
DEFAULTS = {"allowed_hosts": [], "min_sec": 60, "max_sec": 600, "max_mb": 80, "timeout": 30, "max_redirects": 5, "retries": 2}


class Duplicate(Refused):
    """The same file (sha256) or song is already saved: not an error, nothing is written."""


def host_allowed(host, allowed):
    host = (host or "").lower()
    return any(host == d.lower() or host.endswith("." + d.lower()) for d in allowed)


def _check_hop(url, allowed):
    u = urlparse(url)
    if u.scheme not in ("http", "https"):
        raise Refused(f"схема {u.scheme!r} не поддерживается (только http/https)")
    if not host_allowed(u.hostname, allowed):
        raise Refused(f"хост {u.hostname!r} не в списке direct_urls.allowed_hosts")
    return u


def _open(url, dc, http):
    """Follow redirects by hand; every hop must pass the allowlist. -> streaming response."""
    cur = url
    for _ in range(dc["max_redirects"] + 1):
        _check_hop(cur, dc["allowed_hosts"])
        last = None
        for _try in range(dc["retries"] + 1):
            try:
                r = http.get(cur, stream=True, timeout=dc["timeout"], allow_redirects=False, headers={"User-Agent": "vybex-fetch/1.0"})
                if r.status_code >= 500:
                    last = RuntimeError(f"HTTP {r.status_code}")
                    r.close()
                    continue
                break
            except (requests.Timeout, requests.ConnectionError) as e:
                last = e
        else:
            raise RuntimeError(f"не удалось скачать: {type(last).__name__} {str(last)[:80]}")
        if 300 <= r.status_code < 400 and r.headers.get("Location"):
            cur = urljoin(cur, r.headers["Location"])
            r.close()
            continue
        if r.status_code in (401, 403):
            raise Refused(f"HTTP {r.status_code}: нужен вход или доступ закрыт (не обходится)")
        r.raise_for_status()
        return r
    raise Refused(f"больше {dc['max_redirects']} перенаправлений")


def _format_name(path):
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=format_name", "-of", "json", str(path)], capture_output=True, text=True, encoding="utf-8", errors="replace")
    try:
        return json.loads(r.stdout or "{}")["format"]["format_name"]
    except (ValueError, KeyError):
        return ""


def fetch(url, artist, title, out, cfg=None, license="", rights="", http=requests, known_sha=(), env=None, check=None):
    """-> (file name, sha256, detail). Raises Refused (policy / not audio) or RuntimeError (network)."""
    cfg = cfg or load_config()
    dc = {**DEFAULTS, **cfg.get("direct_urls", {})}
    env = os.environ if env is None else env
    if not (license and license_ok(license, cfg["licenses_allowed"])) and not (rights == "owner" and env.get("VYBEX_OWNER_DECLARES_RIGHTS") == "1"):
        raise Refused("нет подтверждения прав: нужна лицензия CC0/PD/CC-BY для ссылки или rights=owner с декларацией владельца")
    out = Path(out)
    tmp = out / "_tmp"
    tmp.mkdir(parents=True, exist_ok=True)
    r = _open(url, dc, http)
    try:
        ctype = (r.headers.get("Content-Type") or "").split(";")[0].strip().lower()
        if ctype.startswith("text/") or "html" in ctype or "json" in ctype:
            raise Refused(f"это не аудио (Content-Type {ctype})")
        if int(r.headers.get("Content-Length") or 0) > dc["max_mb"] * 1024 * 1024:
            raise Refused(f"файл больше {dc['max_mb']} МБ")
        ext = Path(unquote(urlparse(url).path)).suffix.lower()
        if ext not in FORMAT_OF:
            ext = EXT_BY_TYPE.get(ctype, "")
        if ext not in FORMAT_OF:
            raise Refused(f"тип файла не mp3/wav/flac/m4a (расширение/тип: {ext or ctype or 'нет'})")
        raw, sha, size = tmp / f"download{ext}", hashlib.sha256(), 0
        with open(raw, "wb") as f:
            for chunk in r.iter_content(65536):
                size += len(chunk)
                if size > dc["max_mb"] * 1024 * 1024:
                    raise Refused(f"файл больше {dc['max_mb']} МБ")
                sha.update(chunk)
                f.write(chunk)
    finally:
        r.close()
    digest = sha.hexdigest()
    if digest in known_sha or digest[:16] in known_sha:
        raw.unlink(missing_ok=True)
        raise Duplicate("такой файл (sha256) уже скачан")
    fmt = _format_name(raw)
    if FORMAT_OF[ext] not in fmt:
        raise Refused(f"содержимое не {ext[1:]} (ffprobe: {fmt or 'не распознано'})")
    path, _ = (check or download.check_audio)(raw, min_sec=dc["min_sec"], max_sec=dc["max_sec"], fixdir=tmp / "fix")
    name = f'{download._slug(artist)} - {download._slug(title)}.mp3'
    to_mp3(path, out / name)
    (out / (name + ".license.json")).write_text(json.dumps({
        "attribution": f'"{title}" by {artist} ({url})' if license else "", "license": license or "owner-declared", "source": url,
        "rights": rights or "license", "sha256": digest, "direct_url": True}, ensure_ascii=False, indent=1), encoding="utf-8")
    return name, digest, f"url {urlparse(url).hostname} sha256:{digest[:16]}"


def main(argv):
    ap = argparse.ArgumentParser(prog="pipeline url")
    ap.add_argument("url")
    ap.add_argument("--artist", required=True)
    ap.add_argument("--title", required=True)
    ap.add_argument("--license", default="", help="license of this link: cc0 | pdm | by (or a creativecommons URL)")
    ap.add_argument("--rights", default="", choices=["", "owner"], help="owner = you declare the rights (needs VYBEX_OWNER_DECLARES_RIGHTS=1)")
    ap.add_argument("--out", default="out/fetched")
    ap.add_argument("--state", default="out/songs-memory.md", help="memory md table (songs.md): duplicates are skipped, the result is written")
    a = ap.parse_args(argv)
    st = load_memory(a.state)
    k = key(a.artist, a.title)
    shas = {m.group(1) for r in st["done"].values() for m in [re.search(r"sha256:([0-9a-f]{16})", r["detail"])] if m}
    if k in st["done"]:
        print(json.dumps({"state": "duplicate", "detail": "песня уже в памяти (songs.md)"}, ensure_ascii=False))
        return 0
    try:
        name, digest, detail = fetch(a.url, a.artist, a.title, a.out, license=a.license, rights=a.rights, known_sha=shas)
        st["done"][k] = {"status": "downloaded", "date": time.strftime("%Y-%m-%d", time.gmtime()), "song": f"{a.artist} - {a.title}", "file": name, "detail": detail}
        st["skipped"].pop(k, None)
        save_memory(a.state, st)
        print(json.dumps({"state": "ok", "file": name, "detail": detail}, ensure_ascii=False))
        return 0
    except Duplicate as e:
        print(json.dumps({"state": "duplicate", "detail": str(e)}, ensure_ascii=False))
        return 0
    except (Refused, RuntimeError, requests.RequestException) as e:
        print(json.dumps({"state": "refused", "detail": str(e) if isinstance(e, (Refused, RuntimeError)) else safe_err(e)}, ensure_ascii=False))
        return 1
    finally:
        shutil.rmtree(Path(a.out) / "_tmp", ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
