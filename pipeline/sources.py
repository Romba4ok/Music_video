"""Search for music in sources where use is allowed. Tries sources in config order (fallback chain).

Never touches commercial catalogs. `local` = files the owner placed in audio_dir (owner's responsibility).
Returns (candidates, statuses); statuses say exactly what was unavailable / needs auth.
"""
import json
import os
import re
from dataclasses import asdict, dataclass
from urllib.parse import quote

from .common import ROOT, NeedsAuth, get_json, parse_name, license_ok, load_config, safe_err, status


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
    words = [w for w in re.split(r"\W+", q.lower()) if w]
    out = []
    for f in sorted(d.glob("*")) if d.exists() else []:
        if f.suffix.lower() not in (".mp3", ".wav", ".m4a", ".ogg", ".flac", ".mp4", ".mov", ".mkv", ".webm", ".m4v"):
            continue
        if words and not all(w in f.stem.lower() for w in words):
            continue
        artist, title = parse_name(f.stem)
        lic = meta.get(f.name, {}).get("license", "owner-supplied")
        out.append(Candidate("local", title, artist, license=lic, local_path=str(f),
                             rights_declared=f.name in meta))
    return out[:n]


def _openverse(q, n, cfg, env):
    data = get_json("https://api.openverse.org/v1/audio/", {"q": q, "license_type": "commercial", "page_size": n})
    return [
        Candidate("openverse", r.get("title") or "", r.get("creator") or "", r.get("url") or "",
                  r.get("license") or "", r.get("license_url") or "", r.get("foreign_landing_url") or "", sec=(r.get("duration") or 0) / 1000)
        for r in data.get("results", []) if r.get("url")
    ]


def _jamendo(q, n, cfg, env):
    key = env.get("JAMENDO_CLIENT_ID")
    if not key:
        raise NeedsAuth("set JAMENDO_CLIENT_ID (free key at developer.jamendo.com)")
    data = get_json("https://api.jamendo.com/v3.0/tracks/",
                    {"client_id": key, "format": "json", "limit": n, "search": q, "audiodlformat": "mp32"})
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


# a remix/cover/preview of the wanted song is a different recording: refused unless the wanted title itself says so
_BAD = ("remix", "cover", "karaoke", "instrumental", "live", "slowed", "sped", "nightcore", "8d", "preview", "ремикс", "кавер", "минус")


def _words(s):
    return [w for w in re.split(r"[\W_]+", (s or "").lower()) if w]


def matches(artist, title, c, sec=0):
    """Is candidate `c` the wanted recording? Title words all present, an artist word present, no remix/cover marks, length within 15% when both known."""
    tw = _words(re.sub(r"[\(\[].*?[\)\]]", " ", title))
    ct, ca = _words(c.title), _words(c.artist)
    if not tw or not set(tw) <= set(ct):
        return False
    aw = [w for w in _words(artist) if len(w) > 2]  # a one/two-letter artist name cannot be checked
    if aw and not any(w in ca + ct for w in aw):
        return False
    if any(b in ca + ct and b not in _words(title) for b in _BAD):
        return False
    return not (sec and c.sec and abs(c.sec - sec) > 0.15 * sec)


def search(q, cfg=None, env=None, n=5, searchers=None):
    cfg = cfg or load_config()
    env = os.environ if env is None else env
    searchers = searchers or SEARCHERS
    allowed = cfg["licenses_allowed"]
    found, statuses = [], []
    for name in cfg["sources"]["order"]:
        fn = searchers.get(name)
        if not fn:
            statuses.append(status(name, "unavailable", "unknown source"))
            continue
        try:
            res = fn(q, n, cfg, env)
        except NeedsAuth as e:
            statuses.append(status(name, "needs_auth", str(e)))
            continue
        except Exception as e:  # network/API failure: fall through to the next source
            statuses.append(status(name, "unavailable", safe_err(e)))
            continue
        ok = [c for c in res if c.source == "local" or license_ok(c.license or c.license_url, allowed)]
        statuses.append(status(name, "ok" if ok else "empty", f"{len(ok)}/{len(res)} allowed"))
        found += ok
        if len(found) >= n:
            break
    return found[:n], statuses


if __name__ == "__main__":
    import sys
    c, s = search(" ".join(sys.argv[1:]) or "piano")
    print(json.dumps({"candidates": [x.dict() for x in c], "statuses": s}, ensure_ascii=False, indent=1))
