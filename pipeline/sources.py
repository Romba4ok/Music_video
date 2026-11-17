"""Search for music in sources where use is allowed. Tries sources in config order (fallback chain).

Never touches commercial catalogs. `local` = files the owner placed in audio_dir (owner's responsibility).
Returns (candidates, statuses); statuses say exactly what was unavailable / needs auth.
"""
import json
import math
import os
import re
from dataclasses import asdict, dataclass
from urllib.parse import quote

from .common import ROOT, NeedsAuth, get_json, license_key, parse_name, license_ok, load_config, safe_err, status


@dataclass
class Candidate:
    source: str
    title: str
    artist: str
    url: str = ""
    license: str = ""
    license_url: str = ""
    landing: str = ""
    local_path: str = ""
    rights_declared: bool = False  # local files: owner listed the file in audio/sources.json
    sec: float = 0  # length declared by the source (0 = unknown)

    def attribution(self):
        lic = (self.license or "").upper()
        return f'"{self.title}" by {self.artist} ({self.landing or self.url}) — license: {lic}'

    def dict(self):
        return asdict(self)


def _local(q, n, cfg, env):
    d = ROOT / cfg["audio_dir"]
    meta_file = d / "sources.json"
    meta = json.loads(meta_file.read_text(encoding="utf-8")) if meta_file.exists() else {}
    words = _words(q)
    out = []
    for f in sorted(d.glob("*")) if d.exists() else []:
        if f.suffix.lower() not in (".mp3", ".wav", ".m4a", ".ogg", ".flac", ".mp4", ".mov", ".mkv", ".webm", ".m4v"):
            continue
        artist, title = parse_name(re.sub(r"\s+\[[^\]]+\]$", "", f.stem))
        if len(words) == 1 and words[0] not in _words(f.stem):
            continue
        if len(words) > 1 and words not in (_words(f"{artist} {title}"), _words(f.stem)):
            continue
        lic = meta.get(f.name, {}).get("license", "owner-supplied")
        out.append(Candidate("local", title, artist, license=lic, local_path=str(f),
                             rights_declared=f.name in meta))
    return out[:n]


def _openverse(q, n, cfg, env, *, track=None):
    params = {"license": ",".join(sorted(cfg["licenses_allowed"])), "page_size": n}
    if track is None:
        params["q"] = q
    else:
        params["creator"], params["title"] = track
    data = get_json("https://api.openverse.org/v1/audio/", params)
    return [
        Candidate("openverse", _openverse_title(r), r.get("creator") or "", r.get("url") or "",
                  r.get("license") or "", r.get("license_url") or "", r.get("foreign_landing_url") or "", sec=(r.get("duration") or 0) / 1000)
        for r in data.get("results", []) if r.get("url")
    ]


def _openverse_title(record):
    title = (record.get("title") or "").strip()
    if record.get("source") != "wikimedia_audio":
        return title
    # Wikimedia titles can carry the recording ID or repeat the credited artist.
    title = re.sub(r"\s*\(ISRC\s+[A-Z]{2}[A-Z0-9]{3}\d{7}\)$", "", title, flags=re.I)
    parts = re.split(r"\s+[-–—]\s+", title, maxsplit=1)
    artist = _words(record.get("creator"))
    return parts[1] if len(parts) == 2 and artist and _words(parts[0]) == artist else title


def _jamendo(q, n, cfg, env):
    key = env.get("JAMENDO_CLIENT_ID")
    if not key:
        raise NeedsAuth("set JAMENDO_CLIENT_ID (free key at developer.jamendo.com)")
    data = get_json("https://api.jamendo.com/v3.0/tracks/",
                    {"client_id": key, "format": "json", "limit": max(n, 20), "search": q, "audiodlformat": "mp32"})  # many tracks forbid download: ask for more, filter below
    head = data.get("headers") or {}
    if head.get("status") not in (None, "success"):  # an API-level failure (bad client id, rate limit) is not an empty answer
        print("jamendo:", head.get("status"), head.get("code"), str(head.get("error_message"))[:100].replace(key, "***"), file=__import__("sys").stderr)
        raise RuntimeError("Jamendo API: " + str(head.get("error_message") or head.get("status"))[:80])
    return [
        Candidate("jamendo", r.get("name") or "", r.get("artist_name") or "", r.get("audiodownload") or "",
                  r.get("license_ccurl") or "", r.get("license_ccurl") or "", r.get("shareurl") or "", sec=r.get("duration") or 0)
        for r in data.get("results", []) if r.get("audiodownload_allowed") and r.get("audiodownload")
    ]


def _archive(q, n, cfg, env):
    """Internet Archive: only items whose own `licenseurl` is set (the policy filter in search() decides), then its public file list."""
    data = get_json("https://archive.org/advancedsearch.php",
                    {"q": f"({q}) AND mediatype:audio AND licenseurl:*", "fl[]": ["identifier", "title", "creator", "licenseurl"], "rows": n, "output": "json"})
    out = []
    for d in data.get("response", {}).get("docs", []):
        lic = d.get("licenseurl") or ""
        lic = lic[0] if isinstance(lic, list) else lic
        if not license_ok(lic, cfg["licenses_allowed"]):  # skip the per-item file request for items that will be refused anyway
            continue
        creator = d.get("creator") or ""
        creator = creator[0] if isinstance(creator, list) else creator
        for f in get_json(f"https://archive.org/metadata/{d['identifier']}").get("files", []):
            if f.get("source") == "original" and str(f.get("name", "")).lower().endswith((".mp3", ".flac", ".ogg", ".wav")):
                out.append(Candidate("archive", f.get("title") or d.get("title") or "", f.get("creator") or creator,
                                     f"https://archive.org/download/{d['identifier']}/{quote(f['name'])}", lic, lic,
                                     f"https://archive.org/details/{d['identifier']}", sec=float(f.get("length") or 0) if str(f.get("length") or "0").replace(".", "", 1).isdigit() else 0))
    return out


def _ccmixter(q, n, cfg, env):
    """ccMixter public JSON query API: no key, no login. Every upload carries its own license URL (the policy filter in search() decides)."""
    out = []
    for d in get_json("https://ccmixter.org/api/query", {"f": "json", "search": q, "search_type": "all", "limit": n}):
        for f in d.get("files") or []:
            fi = f.get("file_format_info") or {}
            if fi.get("default-ext") == "mp3" and f.get("download_url"):
                m, _, s = str(fi.get("ps") or "0:0").partition(":")
                out.append(Candidate("ccmixter", d.get("upload_name") or "", d.get("user_real_name") or d.get("user_name") or "", f["download_url"],
                                     d.get("license_url") or "", d.get("license_url") or "", d.get("file_page_url") or "",
                                     sec=int(m) * 60 + int(s) if m.isdigit() and s.isdigit() else 0))
                break
    return out


def _soundcloud(q, n, cfg, env):
    """Official API; only tracks whose uploader enabled downloads. UNVERIFIED against the live API (no client id here)."""
    key = env.get("SOUNDCLOUD_CLIENT_ID")
    if not key:
        raise NeedsAuth("set SOUNDCLOUD_CLIENT_ID (SoundCloud API app)")
    data = get_json("https://api.soundcloud.com/tracks", {"q": q, "limit": n, "access": "playable", "client_id": key})
    return [Candidate("soundcloud", r.get("title") or "", (r.get("user") or {}).get("username") or "", f"{r['download_url']}?client_id={key}",
                      r.get("license") or "", "", r.get("permalink_url") or "", sec=(r.get("duration") or 0) / 1000)
            for r in data if r.get("downloadable") and r.get("download_url")]


SEARCHERS = {"local": _local, "openverse": _openverse, "jamendo": _jamendo, "archive": _archive, "ccmixter": _ccmixter, "soundcloud": _soundcloud}


def _words(s):
    return re.findall(r"[^\W_]+", (s or "").casefold().replace("ё", "е").replace("'", "").replace("’", ""))


def matches(artist, title, c, sec=0):
    """Match the artist and title independently, with a duration tolerance when known."""
    aw, tw = _words(artist), _words(title)
    if not aw or not tw or aw != _words(c.artist) or tw != _words(c.title):
        return False
    if not sec or not c.sec:
        return True
    try:
        actual, expected = float(c.sec), float(sec)
    except (TypeError, ValueError):
        return False
    return math.isfinite(actual) and math.isfinite(expected) and abs(actual - expected) <= 0.15 * expected


STATS = {}  # per source for the run report: queries / candidates / allowed (license ok) / matched (title+artist+length) / downloaded


def bump(name, **kw):
    s = STATS.setdefault(name, {"queries": 0, "candidates": 0, "allowed": 0, "matched": 0, "downloaded": 0})
    for k, v in kw.items():
        s[k] += v


def search_batches(q, cfg, env=None, n=5, searchers=None, *, track=None, download_only=False):
    """Yield each source's allowed candidates and status in configured order."""
    env = os.environ if env is None else env
    searchers = searchers or SEARCHERS
    allowed = cfg["licenses_allowed"]
    for name in cfg["sources"]["order"]:
        fn = searchers.get(name)
        if not fn:
            yield [], status(name, "unavailable", "unknown source")
            continue
        try:
            if fn is _openverse and track:
                res = fn(q, n, cfg, env, track=track)
            else:
                res = fn(q, n, cfg, env)
        except NeedsAuth as e:
            yield [], status(name, "needs_auth", str(e))
            continue
        except Exception as e:  # network/API failure: fall through to the next source
            bump(name, queries=1)
            yield [], status(name, "unavailable", safe_err(e))
            continue
        ok = [c for c in res if download_only or c.source == "local" or license_ok(c.license or c.license_url, allowed)]
        bump(name, queries=1, candidates=len(res), allowed=len(ok))
        yield ok, status(name, "ok" if ok else "empty", f"{len(ok)}/{len(res)} allowed")


def search(q, cfg=None, env=None, n=5, searchers=None):
    found, statuses = [], []
    for ok, st in search_batches(q, cfg or load_config(), env, n, searchers):
        statuses.append(st)
        found += ok
        if len(found) >= n:
            break
    return found[:n], statuses


def probe(q="piano", cfg=None, env=None, searchers=None):
    """One test query to EVERY configured source (no early stop): what each one answers. -> [{source, state, candidates, allowed, example}]"""
    cfg = cfg or load_config()
    env = os.environ if env is None else env
    out = []
    for name in cfg["sources"]["order"]:
        if name == "local":
            continue
        try:
            res = (searchers or SEARCHERS)[name](q, 5, cfg, env)
        except NeedsAuth as e:
            out.append({"source": name, "state": "needs_auth", "candidates": 0, "allowed": 0, "example": str(e)[:80]})
            continue
        except Exception as e:
            out.append({"source": name, "state": "unavailable", "candidates": 0, "allowed": 0, "example": safe_err(e)})
            continue
        ok = [c for c in res if license_ok(c.license or c.license_url, cfg["licenses_allowed"])]
        ex = next(iter(ok or res), None)
        out.append({"source": name, "state": "ok" if res else "empty", "candidates": len(res), "allowed": len(ok),
                    "example": f'"{ex.title}" by {ex.artist}, {int(ex.sec)} s, {license_key(ex.license or ex.license_url) or ex.license or "?"}' if ex else ""})
    return out


if __name__ == "__main__":
    import sys
    if sys.argv[1:2] == ["--probe"]:
        for r in probe(" ".join(sys.argv[2:]) or "piano"):
            print(f'{r["source"]:11} {r["state"]:12} candidates {r["candidates"]}, license allowed {r["allowed"]}  {r["example"]}')
        sys.exit(0)
    c, s = search(" ".join(sys.argv[1:]) or "piano")
    print(json.dumps({"candidates": [x.dict() for x in c], "statuses": s}, ensure_ascii=False, indent=1))
