"""Shared helpers: config, source statuses, license policy, HTTP. No secrets are ever logged."""
import json
import re
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent


class NeedsAuth(Exception):
    """A source works only with credentials/rights the owner has not provided."""


class Refused(Exception):
    """An action was refused by the license/source policy."""


def load_config(path=None):
    return json.loads(Path(path or ROOT / "config.json").read_text(encoding="utf-8"))


def status(source, state, detail=""):
    """state: ok | empty | needs_auth | unavailable | refused"""
    return {"source": source, "state": state, "detail": detail}


def safe_err(e):
    """Error text without URLs/queries (they can contain API keys)."""
    code = getattr(getattr(e, "response", None), "status_code", None)
    return type(e).__name__ + (f" HTTP {code}" if code else "")


def license_key(s):
    """Normalise a license string/URL to 'cc0' | 'pdm' | 'by' | 'by-nc-sa' ... or '' if unknown."""
    s = (s or "").lower().strip()
    if not s:
        return ""
    if "publicdomain/zero" in s or "cc0" in s or "cc-0" in s:
        return "cc0"
    if "publicdomain/mark" in s or s == "pdm":
        return "pdm"
    if "creative commons attribution" in s and "non" not in s and "share" not in s and "no deriv" not in s:
        return "by"
    m = re.search(r"licenses/([a-z\-]+)/", s)
    if m:
        return m.group(1)
    s2 = re.sub(r"^cc[\s\-_]*", "", s)
    m = re.match(r"(by(?:[\s\-_](?:nc|nd|sa))*)(?![a-z])", s2)
    return re.sub(r"[\s_]", "-", m.group(1)) if m else ""


def license_ok(s, allowed):
    """Only licenses in `allowed` (default cc0/pdm/by). NC, ND, SA and unknown are refused."""
    return license_key(s) in set(allowed)


def get_json(url, params=None, headers=None, timeout=20, retries=2):
    last = None
    for _ in range(retries + 1):
        try:
            r = requests.get(url, params=params, headers=headers, timeout=timeout)
            r.raise_for_status()
            return r.json()
        except requests.RequestException as e:
            last = e
    raise last


def parse_name(stem):
    """'Basta_-_Moya_igra_2_79894643' / 'Artist - Title' -> (artist, title); site ids (4+ trailing digits) and underscores dropped."""
    import re
    t = re.sub(r"\s+", " ", stem.replace("_", " ")).strip()
    t = re.sub(r"\s+\d{4,}$", "", t) or t
    artist, sep, title = t.partition(" - ")
    return (artist.strip(), title.strip()) if sep and title.strip() else ("", t)
