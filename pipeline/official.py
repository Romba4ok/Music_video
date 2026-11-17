"""Official-source stage of `songs`: for one song find the artist's own pages (MusicBrainz url-relations: official homepage, free download) and look there for a
full audio file that the PAGE ITSELF declares as CC0 / public domain / CC-BY. Only then it is downloaded (fetch_url gates: host = the page's host, ffprobe, 60-600 s).
Anything else is never downloaded: a page without a license, or a file without a declared license, is saved as a LINK for the owner (song-links.md).
Not touched: streaming/store/social hosts (LINK_ONLY), pages that robots.txt closes, logins, paywalls, DRM. No API key, plain HTTP.
"""
import json
import os
import re
import time
from email.utils import parsedate_to_datetime
from pathlib import Path
import urllib.robotparser
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse

import requests

from .common import HTTP_LOG, Refused, license_key, license_ok, safe_err
from .sources import _words

UA = {"User-Agent": "vybex-fetch/1.0"}
MB = "https://musicbrainz.org/ws/2/"
REL_TYPES = ("official homepage", "download for free", "free streaming", "bandcamp")  # artist level
FREE_TYPES = ("download for free", "free streaming", "official homepage")  # track / release level: where a free file may be offered
COMMERCIAL_TYPES = ("purchase for download", "streaming music", "purchase for mail-order", "bandcamp")  # exact commercial release: only a link
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


def _retry_after(resp):
    """Retry-After header (seconds or an HTTP date) -> seconds, 0 when absent / unreadable; at most 120."""
    v = (getattr(resp, "headers", None) or {}).get("Retry-After")
    if not v:
        return 0.0
    try:
        return min(120.0, max(0.0, float(v)))
    except ValueError:
        try:
            return min(120.0, max(0.0, parsedate_to_datetime(v).timestamp() - time.time()))
        except (TypeError, ValueError):
            return 0.0


class Ctx:
    """State shared by all songs of a run.
    MusicBrainz client: User-Agent `VYBEX/1.0 (<MUSICBRAINZ_CONTACT>)` (no contact configured = plain `VYBEX/1.0`, nothing is invented); requests at least `gap`
    seconds apart (1.5 s, wider after each 429/503, narrower again after successes); a 429/503/timeout is retried up to 3 times, waiting Retry-After when the
    server sends it, otherwise 3 / 6 / 12 s; a request that failed completely adds an extra pause before the next one. All waiting beyond the normal spacing is
    bounded by `budget` seconds per run: when it is used up the rest of the songs get `musicbrainz:unavailable` and are searched again next run. Nothing is
    switched off for good. Successful answers (also empty ones) are cached in memory and, with `cache_file`, on disk for `ttl_days`, so the same recording /
    release / label / artist is never asked twice. Scanned pages are fetched once per run."""

    def __init__(self, gap=1.5, clock=time.monotonic, env=None, cache_file=None, budget=600, ttl_days=30):
        env = os.environ if env is None else env
        self.contact = (env.get("MUSICBRAINZ_CONTACT") or "").strip()
        self.ua = {"User-Agent": f"VYBEX/1.0 ({self.contact})" if self.contact else "VYBEX/1.0"}
        self.base_gap = self.gap = gap
        self.clock, self.budget, self.ttl = clock, budget, ttl_days * 86400
        self.last, self.fails, self.pause = -1e9, 0, 0.0
        self.pages, self.robots, self.cache_file, self.fresh = {}, {}, cache_file, {}
        self.cache = {}
        try:
            for k, v in json.loads(Path(cache_file).read_text(encoding="utf-8")).items():
                if time.time() - v["t"] < self.ttl:
                    self.cache[k] = v
        except (OSError, ValueError, KeyError, TypeError):
            pass  # no cache yet / unreadable: asked again

    def save(self, keep=3000):
        if not self.cache_file or not self.fresh:
            return
        merged = dict(sorted({**self.cache, **self.fresh}.items(), key=lambda kv: kv[1]["t"])[-keep:])
        Path(self.cache_file).parent.mkdir(parents=True, exist_ok=True)
        Path(self.cache_file).write_text(json.dumps(merged, ensure_ascii=False), encoding="utf-8")

    def mb(self, path, params, get_json, sleep):
        k = path + "?" + json.dumps(params, sort_keys=True, ensure_ascii=False)
        if k in self.cache:
            return self.cache[k]["v"]
        err, ra = None, 0.0
        for attempt in range(4):
            back = self.pause if attempt == 0 else (ra or 3.0 * 2 ** (attempt - 1))
            back = min(back, 120.0)
            if back > self.budget:
                raise ConnectionError("MusicBrainz: лимит ожидания запуска исчерпан, песня перепроверится в следующий запуск") from err
            self.budget -= back
            sleep(max(0.0, self.gap - (self.clock() - self.last)) + back)
            self.last, self.pause = self.clock(), 0.0
            try:
                r = get_json(MB + path, {**params, "fmt": "json"}, headers=self.ua, retries=0)
                self.fails, self.gap = 0, max(self.base_gap, self.gap * 0.9)
                self.cache[k] = self.fresh[k] = {"t": time.time(), "v": r}
                return r
            except Exception as e:
                err = e
                resp = getattr(e, "response", None)
                code = getattr(resp, "status_code", 0)
                if code and code not in (429, 503):  # 404 and the like: asking again cannot help
                    raise
                ra = _retry_after(resp)
                self.gap = min(self.gap * 1.5, 4.0)
        self.fails += 1
        self.pause = min(30.0 * self.fails, 120.0)  # the server is not answering: the next request starts after a longer pause
        raise err


def load_page(url, http, timeout, ctx):
    """-> (parsed page | None, note). One request per URL per run, robots.txt first."""
    if url in ctx.pages:
        return ctx.pages[url]
    p, note = None, ""
    try:
        if not robots_ok(url, http, timeout, ctx.robots):
            note = "robots.txt закрывает страницу"
        else:
            r = _get(url, http, timeout)
            if r.status_code >= 400:
                note = f"HTTP {r.status_code}"
            elif "html" not in (r.headers.get("Content-Type") or "").lower():
                note = "не HTML"
            else:
                html = r.raw.read(MAX_HTML, decode_content=True).decode(r.encoding or "utf-8", "replace")
                p = _Page()
                p.feed(html)
            r.close()
    except requests.RequestException as e:
        note = safe_err(e)
    ctx.pages[url] = (p, note)
    return ctx.pages[url]


def scan_page(url, title, http=requests, timeout=15, ctx=None):
    """-> {url, license, files: [audio urls whose name/text has the title], note, _inner}. Never raises on network errors: the note says what happened."""
    ctx = ctx or Ctx()
    out = {"url": url, "license": "", "files": [], "note": "", "_inner": []}
    p, out["note"] = load_page(url, http, timeout, ctx)
    if p is None:
        return out
    out["license"] = urljoin(url, p.lic) if p.lic else ""
    tw = set(_words(re.sub(r"[\(\[].*?[\)\]]", " ", title)))
    audio = [(urljoin(url, h), t.strip()) for h, t in p.links if urlparse(h).path.lower().endswith(AUDIO_EXT)]
    out["files"] = [u for u, t in audio if tw and tw <= set(_words(u + " " + t))]
    if not out["files"] and len(audio) == 1 and tw and tw <= set(_words(p.title)):
        out["files"] = [audio[0][0]]  # a page named after the song with exactly one audio file
    out["_inner"] = [urljoin(url, h) for h, t in p.links if tw & set(_words(h + " " + t)) and urlparse(urljoin(url, h)).hostname == urlparse(url).hostname
                     and not urlparse(h).path.lower().endswith(AUDIO_EXT)]
    return out


def _rels(rels, types):
    return [(r["type"], r["url"]["resource"]) for r in rels or [] if r.get("type") in types and r.get("url")]


def identify(w, ctx, get_json, sleep):
    """MusicBrainz -> exact recording / release / label / artist pages of the wanted song.
    -> {"known": bool, "pages": [(rel, url)] where a free file may be offered, "commercial": [(note, url)] exact commercial links, "facts": str}"""
    ask = lambda path, params: ctx.mb(path, params, get_json, sleep)
    artist = w["artist"]
    want, tw = _words(artist), set(_words(w["title"]))
    res = {"known": False, "pages": [], "commercial": [], "facts": ""}
    # 1) the exact recording -> its release and label (a Cyrillic title may be missing in MusicBrainz: then only the artist is known)
    rec = None
    for r in ask("recording/", {"query": f'recording:"{w["title"]}" AND artist:"{artist}"', "limit": 5}).get("recordings", []):
        names = _words(" ".join(c.get("name", "") for c in r.get("artist-credit", []) if isinstance(c, dict)))
        if r.get("score", 0) >= 90 and tw <= set(_words(r.get("title"))) and any(x in names for x in want if len(x) > 2):
            rec = r
            break
    if rec:
        res["known"] = True
        rels = ask(f'recording/{rec["id"]}', {"inc": "url-rels"}).get("relations", [])
        res["pages"] += _rels(rels, FREE_TYPES)
        res["commercial"] += [(f"{t}: запись", u) for t, u in _rels(rels, COMMERCIAL_TYPES)]
        rel = next((x for x in rec.get("releases", []) if x.get("status") == "Official"), (rec.get("releases") or [None])[0])
        if rel:
            rd = ask(f'release/{rel["id"]}', {"inc": "labels+url-rels"})
            labels = [li["label"] for li in rd.get("label-info", []) if li.get("label")]
            res["facts"] = f'релиз «{rd.get("title", "")}» {rd.get("date", "")}, лейбл: {", ".join(l.get("name", "") for l in labels) or "не указан"}'
            res["pages"] += _rels(rd.get("relations"), FREE_TYPES)
            res["commercial"] += [(f"{t}: релиз", u) for t, u in _rels(rd.get("relations"), COMMERCIAL_TYPES)]
            for lab in labels[:1]:
                res["pages"] += _rels(ask(f'label/{lab["id"]}', {"inc": "url-rels"}).get("relations"), ("official homepage", "download for free"))
            if not res["commercial"]:
                res["commercial"].append((f"релиз в MusicBrainz ({res['facts']})", f'https://musicbrainz.org/release/{rel["id"]}'))
    # 2) the artist's own pages
    ids = [a["id"] for a in ask("artist/", {"query": f'artist:"{artist}"', "limit": 5}).get("artists", []) if a.get("score", 0) >= 90 and _words(a.get("name")) == want]
    if ids:
        res["known"] = True
        res["pages"] += _rels(ask(f"artist/{ids[0]}", {"inc": "url-rels"}).get("relations", []), REL_TYPES)
    return res


def try_song(w, cfg, out, known_sha=(), http=requests, get_json=None, fetch=None, sleep=time.sleep, ctx=None):
    """-> dict {file, detail, links: [(page, note)], reason}. file = downloaded name or None."""
    from . import fetch_url
    from .common import get_json as _gj
    oc = {"max_pages": 6, "timeout": 15, **cfg.get("official", {})}
    get_json, fetch, ctx = get_json or _gj, fetch or fetch_url.fetch, ctx or Ctx()
    res = {"file": None, "detail": "", "links": [], "reason": ""}
    try:
        info = identify(w, ctx, get_json, sleep)
    except Exception as e:
        res["reason"] = f"musicbrainz:unavailable ({safe_err(e)})"
        return res
    if not info["known"]:
        res["reason"] = "MusicBrainz: ни записи, ни артиста"
        return res
    res["links"] += [(u, f"коммерческий релиз, {n}") for n, u in info["commercial"]]
    seen, notes, pages = set(), [], []
    for rel, u in info["pages"]:
        if u not in pages:
            pages.append(u)
    for page in pages[: oc["max_pages"]]:
        if _host_in(urlparse(page).hostname, LINK_ONLY):
            res["links"].append((page, "официальная страница (скачивание автоматом запрещено условиями сайта)"))
            continue
        todo = [page]
        while todo and len(seen) < oc["max_pages"] * 2:
            u = todo.pop(0)
            if u in seen:
                continue
            seen.add(u)
            sc = scan_page(u, w["title"], http, oc["timeout"], ctx)
            notes.append(f'{urlparse(u).hostname}: {sc["note"] or "ok"}')
            if sc["files"]:
                lic = sc["license"]
                if lic and license_ok(lic, cfg["licenses_allowed"]):
                    cfg2 = {**cfg, "direct_urls": {**cfg.get("direct_urls", {}), "allowed_hosts": [urlparse(sc["files"][0]).hostname]}}
                    try:
                        name, _, why = fetch(sc["files"][0], w["artist"], w["title"], out, cfg2, license=lic, known_sha=known_sha)
                        res.update(file=name, detail=f"official {u}: {why}")
                        return res
                    except (Refused, RuntimeError, OSError) as e:
                        notes.append(f"файл не принят: {str(e)[:100]}")
                else:
                    res["links"].append((sc["files"][0], f"файл найден на {urlparse(u).hostname}, но страница не объявляет разрешённую лицензию ({license_key(lic) or 'нет'})"))
            elif u == page:
                todo += sc["_inner"][:3]  # links of that page that carry the song title: the track page, one level deep
            elif not sc["note"]:
                res["links"].append((u, "страница трека найдена, файла для скачивания на ней нет"))
    res["links"] = list(dict.fromkeys(res["links"]))
    res["reason"] = (info["facts"] + "; " if info["facts"] else "") + ("проверено: " + "; ".join(notes[:6]) if notes else "официальных страниц для автоскачивания нет")
    return res


def save_links(path, rows, today):
    """rows (song, page, note) -> md table `song-links.md` next to the memory; one row per (song, page), the first date is kept."""
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
