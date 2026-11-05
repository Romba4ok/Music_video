"""Search for music in sources where use is allowed. Tries sources in config order (fallback chain).

Never touches commercial catalogs. `local` = files the owner placed in audio_dir (owner's responsibility).
Returns (candidates, statuses); statuses say exactly what was unavailable / needs auth.
"""
import json
import os
import re
from dataclasses import asdict, dataclass

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
                  r.get("license") or "", r.get("license_url") or "", r.get("foreign_landing_url") or "")
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
                  r.get("license_ccurl") or "", r.get("license_ccurl") or "", r.get("shareurl") or "")
        for r in data.get("results", []) if r.get("audiodownload_allowed") and r.get("audiodownload")
    ]


SEARCHERS = {"local": _local, "openverse": _openverse, "jamendo": _jamendo}


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
