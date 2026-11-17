"""Official-source stage of `songs`: for one song find the artist's own pages (MusicBrainz url-relations: official homepage, free download) and look there for a
full audio file that the PAGE ITSELF declares as CC0 / public domain / CC-BY. Only then it is downloaded (fetch_url gates: host = the page's host, ffprobe, 60-600 s).
Anything else is never downloaded: a page without a license, or a file without a declared license, is saved as a LINK for the owner (song-links.md).
Not touched: streaming/store/social hosts (LINK_ONLY), pages that robots.txt closes, logins, paywalls, DRM. No API key, plain HTTP.
"""
import re
import time
import urllib.robotparser
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse

import requests

from .common import HTTP_LOG, Refused, license_key, license_ok, safe_err
from .sources import _words

UA = {"User-Agent": "vybex-fetch/1.0"}
MB = "https://musicbrainz.org/ws/2/"
REL_TYPES = ("official homepage", "download for free", "free streaming", "bandcamp")  # label sites are not reached (no label lookup)
LINK_ONLY = ("bandcamp.com", "soundcloud.com", "youtube.com", "youtu.be", "spotify.com", "apple.com", "deezer.com", "vk.com", "vk.ru", "tiktok.com",
             "instagram.com", "facebook.com", "yandex.ru", "zvuk.com", "t.me")  # their terms forbid automated download: the page is only noted
AUDIO_EXT = (".mp3", ".wav", ".flac", ".m4a")
MAX_HTML = 1_500_000


def _host_in(host, names):
    host = (host or "").lower()
    return any(host == n or host.endswith("." + n) for n in names)


class _Page(HTMLParser):
    """links (href/src with their text), page <title>, license links"""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.links, self.title, self.lic, self._a, self._t = [], "", "", None, False

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "title":
            self._t = True
        href = a.get("href") or a.get("src") or (a.get("content") if tag == "meta" and a.get("property") in ("og:audio", "og:audio:url") else None)
        if href and tag in ("a", "audio", "source", "meta", "link"):
            if re.search(r"creativecommons\.org/(licenses|publicdomain)/", href) or (tag in ("a", "link") and "license" in (a.get("rel") or "").split()):
                self.lic = self.lic or href
            elif tag in ("a", "audio", "source", "meta"):
                self.links.append([href, ""])
                self._a = self.links[-1] if tag == "a" else None

    def handle_endtag(self, tag):
        if tag == "title":
            self._t = False
        if tag == "a":
            self._a = None

    def handle_data(self, data):
        if self._t:
            self.title += data
        if self._a is not None:
            self._a[1] += data


def _get(url, http, timeout):
    r = http.get(url, timeout=timeout, headers=UA, stream=True)
    HTTP_LOG.append((urlparse(url).hostname, r.status_code))
    return r


def robots_ok(url, http, timeout, cache):
    u = urlparse(url)
    base = f"{u.scheme}://{u.netloc}"
    if base not in cache:
        rp = urllib.robotparser.RobotFileParser()
        try:
            r = _get(base + "/robots.txt", http, timeout)
            if r.status_code in (401, 403):
                rp.disallow_all = True  # closed means closed
            elif r.status_code >= 400:
                rp.allow_all = True
            else:
                rp.parse(r.text.splitlines())
            r.close()
        except requests.RequestException:
            rp.allow_all = True
        cache[base] = rp
    return cache[base].can_fetch(UA["User-Agent"], url)


def scan_page(url, title, http=requests, timeout=15, robots=None):
    """-> {url, license, files: [audio urls whose name/text has the title], note}. Never raises on network errors: the note says what happened."""
    robots = {} if robots is None else robots
    out = {"url": url, "license": "", "files": [], "note": ""}
    try:
        if not robots_ok(url, http, timeout, robots):
            out["note"] = "robots.txt закрывает страницу"
            return out
        r = _get(url, http, timeout)
        if r.status_code >= 400:
            out["note"] = f"HTTP {r.status_code}"
            r.close()
            return out
        if "html" not in (r.headers.get("Content-Type") or "").lower():
            out["note"] = "не HTML"
            r.close()
            return out
        html = r.raw.read(MAX_HTML, decode_content=True).decode(r.encoding or "utf-8", "replace")
        r.close()
    except requests.RequestException as e:
        out["note"] = safe_err(e)
        return out
    p = _Page()
    p.feed(html)
    out["license"] = urljoin(url, p.lic) if p.lic else ""
    tw = set(_words(re.sub(r"[\(\[].*?[\)\]]", " ", title)))
    audio = [(urljoin(url, h), t.strip()) for h, t in p.links if urlparse(h).path.lower().endswith(AUDIO_EXT)]
    out["files"] = [u for u, t in audio if tw and tw <= set(_words(u + " " + t))]
    if not out["files"] and len(audio) == 1 and tw and tw <= set(_words(p.title)):
        out["files"] = [audio[0][0]]  # a page named after the song with exactly one audio file
    out["_inner"] = [urljoin(url, h) for h, t in p.links if tw & set(_words(h + " " + t)) and urlparse(urljoin(url, h)).hostname == urlparse(url).hostname
                     and not urlparse(h).path.lower().endswith(AUDIO_EXT)]
    return out


def official_pages(artist, title, get_json, sleep=time.sleep):
    """MusicBrainz -> [(relation type, url)] of the artist (and the recording). Empty list = MusicBrainz does not know the artist."""
    want = _words(artist)
    pages = []
    data = get_json(MB + "artist/", {"query": f'artist:"{artist}"', "fmt": "json", "limit": 5}, headers=UA)
    ids = [a["id"] for a in data.get("artists", []) if a.get("score", 0) >= 90 and want and _words(a.get("name")) == want]
    for mbid in ids[:1]:
        sleep(1.1)  # MusicBrainz asks for at most one request per second
        rels = get_json(f"{MB}artist/{mbid}", {"inc": "url-rels", "fmt": "json"}, headers=UA).get("relations", [])
        pages += [(r["type"], r["url"]["resource"]) for r in rels if r.get("type") in REL_TYPES and r.get("url")]
    return ids, pages


def try_song(w, cfg, out, known_sha=(), http=requests, get_json=None, fetch=None, sleep=time.sleep):
    """-> dict {file, detail, links: [(page, note)], reason}. file = downloaded name or None."""
    from . import fetch_url
    from .common import get_json as _gj
    oc = {"max_pages": 6, "timeout": 15, **cfg.get("official", {})}
    get_json, fetch = get_json or _gj, fetch or fetch_url.fetch
    res = {"file": None, "detail": "", "links": [], "reason": ""}
    try:
        ids, pages = official_pages(w["artist"], w["title"], get_json, sleep)
    except Exception as e:
        res["reason"] = f"MusicBrainz не ответил ({safe_err(e)})"
        return res
    if not pages:
        res["reason"] = "MusicBrainz: артист не найден" if not ids else "MusicBrainz: у артиста нет официальных страниц"
        return res
    robots, seen, notes = {}, set(), []
    for rel, page in pages[: oc["max_pages"]]:
        host = urlparse(page).hostname
        if _host_in(host, LINK_ONLY):
            res["links"].append((page, f"{rel}: страница артиста (скачивание автоматом запрещено условиями сайта)"))
            continue
        sleep(1)
        todo = [page]
        while todo and len(seen) < oc["max_pages"] * 2:
            u = todo.pop(0)
            if u in seen:
                continue
            seen.add(u)
            info = scan_page(u, w["title"], http, oc["timeout"], robots)
            notes.append(f'{urlparse(u).hostname}: {info["note"] or "ok"}')
            if info["files"]:
                lic = info["license"]
                if lic and license_ok(lic, cfg["licenses_allowed"]):
                    cfg2 = {**cfg, "direct_urls": {**cfg.get("direct_urls", {}), "allowed_hosts": [urlparse(info["files"][0]).hostname]}}
                    try:
                        name, _, why = fetch(info["files"][0], w["artist"], w["title"], out, cfg2, license=lic, known_sha=known_sha)
                        res.update(file=name, detail=f"official {u}: {why}")
                        return res
                    except (Refused, RuntimeError, OSError) as e:
                        notes.append(f"файл не принят: {str(e)[:100]}")
                else:
                    res["links"].append((info["files"][0], f"файл найден на {urlparse(u).hostname}, но страница не объявляет разрешённую лицензию ({license_key(lic) or 'нет'})"))
            elif u == page:
                todo += info.get("_inner", [])[:3]  # links of the artist's page that carry the song title: the song page, one level deep
            elif not info["note"]:
                res["links"].append((u, "страница песни найдена, файла для скачивания на ней нет"))
    res["reason"] = "официальные страницы проверены: " + "; ".join(notes[:6]) if notes else "официальные страницы только на сайтах, где автоскачивание запрещено"
    return res


def save_links(path, rows, today):
    """rows (song, page, note) -> md table `song-links.md` next to the memory; one row per (song, page), the first date is kept."""
    from pathlib import Path
    path = Path(path)
    old = {}
    if path.exists():
        for ln in path.read_text(encoding="utf-8").splitlines():
            c = [x.strip() for x in ln.strip().strip("|").split("|")]
            if len(c) >= 4 and re.match(r"\d{4}-\d{2}-\d{2}", c[0]):
                old[(c[1], c[2])] = c
    for song, page, note in rows:
        old.setdefault((song, page), [today, song, page, " ".join(note.replace("|", "/").split())])
    head = "# Ссылки на страницы песен (найдены автоматически, файл не скачан)\n\n| дата | песня | страница | примечание |\n|---|---|---|---|\n"
    path.write_text(head + "".join("| " + " | ".join(c[:4]) + " |\n" for c in sorted(old.values())), encoding="utf-8")
