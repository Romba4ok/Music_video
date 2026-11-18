"""Public HTML song discovery and local audio inspection without API credentials.

python -m pipeline.catalog_audio --artist "Artist" --title "Title"
python -m pipeline.catalog_audio --queue accounts/main/queue.md
python -m pipeline.catalog_audio --inspect path/to/audio.mp3
"""

import argparse
import json
import os
import re
import sys
import time
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlencode, urljoin, urlsplit

import requests

from . import download, fetch_songs, fetch_url, sources
from .batch import parse_queue
from .common import HTTP_LOG, ROOT, Refused, load_config, safe_err
from .public_catalog import read_public_html


SITES = {
    "hitmo": ("https://ru.hitmoz.org", "/search"),
    "sefon": ("https://sefon.pro", "/search/"),
    "mp3pm": ("https://mp3.pm", "/"),
    "muzlap": ("https://muzlap.com", "/"),
    "muztop": ("https://muz-top.me", "/"),
    "spaces": ("https://spaces.im", "/music-online/"),
    "hitparad": ("https://hitparad.fm", "/"),
}
DOWNLOAD_HOSTS = {
    "hitmo": ("ru.hitmoz.org", "deliciousoranges.com"),
    "sefon": ("sefon.pro",),
    "mp3pm": ("mp3.pm",),
    "muzlap": ("muzlap.com",),
    "muztop": ("muz-top.me",),
    "spaces": ("spaces.im", "spac.me"),
    "hitparad": ("hitparad.fm",),
}
UA = "vybex-fetch/1.0"
VOID_TAGS = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}


class TrackHTML(HTMLParser):
    """Read published metadata and download anchors, excluding player previews."""

    def __init__(self, site, page):
        super().__init__(convert_charrefs=True)
        self.site, self.page = site, page
        self.stack, self.card, self.results = [], None, []
        self.depth = 0

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        classes = (attrs.get("class") or "").split()
        if self.site == "hitmo" and tag == "li" and attrs.get("data-musmeta"):
            self.finish()
            try:
                data = json.loads(attrs["data-musmeta"])
                artist, title = data["artist"], data["title"]
                if isinstance(artist, str) and isinstance(title, str):
                    self.card = {"artist": [artist], "title": [title], "text": [], "url": "", "landing": ""}
            except (ValueError, KeyError, TypeError):
                pass
            self.depth = len(self.stack)
        elif self.site == "sefon" and "mp3" in classes and attrs.get("data-mp3_id"):
            self.finish()
            self.card = {"artist": [], "title": [], "text": [], "url": "", "landing": ""}
            self.depth = len(self.stack)
        elif self.site == "mp3pm" and "cplayer-sound-item" in classes:
            self.finish()
            target = urljoin(self.page, attrs.get("data-download-url") or "")
            self.card = {"artist": [], "title": [], "text": [], "url": target if (
                urlsplit(target).scheme == "https" and urlsplit(target).path.startswith("/download/")
            ) else "", "landing": ""}
            self.depth = len(self.stack)
        elif self.site == "muzlap" and "js-item" in classes and attrs.get("data-track"):
            self.finish()
            target = urljoin(self.page, attrs["data-track"])
            self.card = {"artist": [attrs.get("data-artist", "")], "title": [attrs.get("data-title", "")],
                         "text": [], "url": target if urlsplit(target).scheme == "https" else "", "landing": ""}
            self.depth = len(self.stack)
        if self.card and tag == "a":
            href = attrs.get("href") or ""
            target = urljoin(self.page, href)
            if urlsplit(target).scheme == "https":
                if self.site == "hitmo" and "track__download-btn" in classes:
                    self.card["url"] = target if urlsplit(target).path.startswith("/get/music/") else ""
                elif self.site == "sefon" and urlsplit(target).path.endswith(".mp3") and "/prev/" not in target:
                    self.card["url"] = target
                if urlsplit(target).path.startswith(("/song/", "/mp3/")) or (self.site == "muzlap" and urlsplit(target).path.endswith(".html")):
                    self.card["landing"] = target
        if tag not in VOID_TAGS:
            self.stack.append((tag, classes))

    def handle_endtag(self, tag):
        index = next((i for i in range(len(self.stack) - 1, -1, -1) if self.stack[i][0] == tag), None)
        if index is None:
            return
        del self.stack[index:]
        if self.card and len(self.stack) <= self.depth:
            self.finish()

    def handle_data(self, text):
        if not self.card or not text.strip():
            return
        text = text.strip()
        self.card["text"].append(text)
        if self.site in ("sefon", "mp3pm"):
            fields = (("artist", "artist_name"), ("title", "song_name")) if self.site == "sefon" else (
                ("artist", "cplayer-data-sound-author"), ("title", "cplayer-data-sound-title"),
            )
            for field, cls in fields:
                if any(cls in classes for _, classes in self.stack[self.depth:]):
                    self.card[field].append(text)

    def finish(self):
        if self.card:
            data = self.card
            artist, title = " ".join(data["artist"]), " ".join(data["title"])
            duration = re.search(r"\b(\d{1,2}):(\d{2})\b", " ".join(data["text"]))
            sec = int(duration[1]) * 60 + int(duration[2]) if duration else 0
            if artist and title:
                self.results.append(sources.Candidate(
                    self.site, title, artist, data["url"], landing=data["landing"] or self.page, sec=sec,
                ))
            self.card = None

    def close(self):
        super().close()
        self.finish()


def parse_tracks(html, site, page):
    parser = TrackHTML(site, page)
    parser.feed(html)
    parser.close()
    return parser.results


def redact_proxy(value):
    proxy = os.environ.get("AUDIO_PROXY_URL", "").strip()
    if not proxy:
        return value
    parsed = urlsplit(proxy)
    secrets = {proxy, parsed.netloc, parsed.hostname, parsed.username, parsed.password,
               unquote(parsed.username or ""), unquote(parsed.password or "")}
    for secret in sorted(filter(None, secrets), key=len, reverse=True):
        value = value.replace(secret, "[redacted]")
    return value


def log_forbidden(response, url):
    """Record the site's explanation without cookies or authorization values."""
    parsed = urlsplit(url)
    headers = {
        name: "[redacted]" if re.search(r"cookie|authorization|token|secret|api[-_]key", name, re.I) else redact_proxy(value)
        for name, value in response.headers.items()
    }
    body = redact_proxy(response.text)
    print(json.dumps({
        "http_diagnostic": 403,
        "url": f"{parsed.scheme}://{parsed.hostname}{parsed.path}",
        "headers": headers,
        "body": body[:65536],
        "body_truncated": len(body) > 65536,
    }, ensure_ascii=False), file=sys.stderr, flush=True)


class CatalogClient:
    """Public requests with bounded retries, fixed origins, and HTTP error handling."""

    def __init__(self, http=requests):
        self.http = http
        proxy = os.environ.get("AUDIO_PROXY_URL", "").strip()
        self.proxies = None
        if proxy:
            try:
                parsed = urlsplit(proxy)
                valid = (parsed.scheme in ("http", "https") and parsed.hostname and parsed.port
                         and parsed.path in ("", "/") and not parsed.query and not parsed.fragment)
            except ValueError:
                valid = False
            if not valid:
                raise Refused("AUDIO_PROXY_URL must be an http:// or https:// proxy URL with a host and port")
            self.proxies = {"http": proxy, "https": proxy}

    def request(self, url, *, data=None):
        for attempt in range(3):
            try:
                options = {"headers": {"User-Agent": UA}, "timeout": (6, 15), "allow_redirects": False}
                response = self.get(url, **options) if data is None else self.post(url, data=data, **options)
                HTTP_LOG.append((urlsplit(url).hostname, response.status_code))
                if response.status_code == 403:
                    log_forbidden(response, url)
                response.raise_for_status()
                return response
            except requests.RequestException as exc:
                response = exc.response
                code = getattr(response, "status_code", 0)
                retry = code in (500, 502, 503, 504) or isinstance(exc, (requests.Timeout, requests.ConnectionError))
                if response is not None:
                    response.close()
                if not retry or attempt == 2 or (response is not None and response.headers.get("Retry-After")):
                    raise
                time.sleep(2 ** attempt)

    def search(self, site, query):
        base, path = SITES[site]
        if site in ("muztop", "spaces", "hitparad"):
            return self.public_search(site, query)
        if site == "mp3pm":
            # This is the public search form's own endpoint (SearchElementCtrl).
            # Its obsolete GET form returns the home page for every query.
            with self.request(base + "/public/api.search.php", data={"q": query}) as response:
                target = response.text.strip()
                if target.startswith('"'):
                    target = json.loads(target)
                if not isinstance(target, str) or not target or "<" in target:
                    raise Refused("MP3.pm search did not return a public result URL")
                url = urljoin(base, target)
        else:
            url = base + path + "?" + urlencode({"q": query})
        data = {"do": "search", "subaction": "search", "story": query} if site == "muzlap" else None
        if site == "muzlap":
            url = base + path
        for _ in range(6):
            parsed = urlsplit(url)
            origin_ok = (fetch_url.host_allowed(parsed.hostname, ("mp3.pm",)) if site == "mp3pm"
                         else parsed.netloc == urlsplit(base).netloc)
            if parsed.scheme != "https" or not origin_ok or parsed.username or parsed.password or parsed.port not in (None, 443):
                raise Refused("catalog search redirected outside its HTTPS origin")
            try:
                response = self.request(url, data=data)
            except requests.HTTPError as exc:
                # A missing result page is query-specific, not a dead catalog.
                if site in ("mp3pm", "muzlap") and getattr(exc.response, "status_code", None) == 404:
                    return []
                raise
            with response:
                if response.is_redirect:
                    url = urljoin(url, response.headers["Location"])
                    if response.status_code in (301, 302, 303):
                        data = None
                    continue
                return parse_tracks(response.text, site, url)
        raise Refused("too many catalog redirects")

    def public_search(self, site, query):
        base, path = SITES[site]

        def page(url, data=None, missing_ok=False):
            for _ in range(6):
                parsed = urlsplit(url)
                if (parsed.scheme != 'https' or parsed.netloc != urlsplit(base).netloc
                        or parsed.username or parsed.password):
                    raise Refused('public search redirected outside its HTTPS origin')
                try:
                    response = self.request(url, data=data)
                except requests.HTTPError as exc:
                    if missing_ok and getattr(exc.response, 'status_code', None) == 404:
                        return None
                    raise
                with response:
                    if response.is_redirect:
                        url = urljoin(url, response.headers['Location'])
                        if response.status_code in (301, 302, 303):
                            data = None
                        continue
                    html = response.text
                    if re.search(r'js_passed|/cdn-cgi/challenge-platform|cf-chl-|enable javascript and cookies', html, re.I):
                        print(json.dumps({'catalog_refused': site, 'detail': 'JavaScript/access challenge; not bypassed'}),
                              file=sys.stderr, flush=True)
                        raise Refused('public catalog requires a JavaScript/access challenge')
                    return read_public_html(html, site, url)
            raise Refused('too many public catalog redirects')

        home = page(base + path)
        if not home.forms:
            raise Refused('no public search form is available')
        form = home.forms[0]
        data = {**form['hidden'], form['query']: query}
        target = form['action']
        if form['method'] == 'get':
            target += ('&' if '?' in target else '?') + urlencode(data)
            data = None
        result = page(target, data, missing_ok=True)
        if result is None:
            return []
        if not result.tracks and not result.empty:
            raise Refused('public search returned no readable audio metadata')
        return result.tracks

    def get(self, url, **kwargs):
        """The direct downloader checks each redirect host before requesting it."""
        if self.proxies:
            kwargs["proxies"] = self.proxies
        return self.http.get(url, **kwargs)

    def post(self, url, **kwargs):
        if self.proxies:
            kwargs["proxies"] = self.proxies
        return self.http.post(url, **kwargs)


def searchers(client=None):
    client = client or CatalogClient()
    return {site: (lambda query, n, cfg, env, site=site: client.search(site, query)[:n]) for site in SITES}


def download_candidate(candidate, destination, cfg):
    """Download the site's advertised full file with a bounded redirect allowlist."""
    if candidate.source not in SITES:
        return download.download(candidate, destination, cfg, download_only=True)
    if not candidate.url:
        raise Refused("no public full-file URL, protected player URLs are excluded")
    config = {**cfg, "direct_urls": {**cfg.get("direct_urls", {}),
                                    "allowed_hosts": DOWNLOAD_HOSTS[candidate.source]}}
    name, _, _ = fetch_url.fetch_download_only(candidate.url, candidate.artist, candidate.title, destination, config,
                                              http=CatalogClient())
    return Path(destination) / name


def run(args, cfg=None, client=None):
    cfg = cfg or load_config()
    download_only = getattr(args, "download_only", False)
    if args.inspect:
        return [fetch_url.inspect_audio(args.inspect)]
    client = client or CatalogClient()
    entries = parse_queue(Path(args.queue).read_text(encoding="utf-8")) if args.queue else [
        {"artist": args.artist, "title": args.title},
    ]
    state = fetch_songs.load_memory(args.state)
    out, reports = Path(args.out), []
    saved = 0
    for entry in entries:
        if saved >= args.max:
            break
        artist, title = entry["artist"], entry["title"]
        key = fetch_songs.key(artist, title)
        report = {"artist": artist, "title": title, "sources": [], "downloaded": None,
                  "usage_rights": "not_evaluated", "technical": "not_checked"}
        previous = state["done"].get(key)
        if previous and (out / previous["file"]).is_file():
            path = out / previous["file"]
            digest = download.file_sha256(path)
            if f"sha256:{digest[:16]}" in previous["detail"]:
                report.update(result="already_saved", file=str(path))
                reports.append(report)
                continue
        for site in args.sites:
            try:
                candidates = client.search(site, f"{artist} {title}")
                matched = [candidate for candidate in candidates
                           if sources.matches(artist, title, candidate, collaborations=download_only)]
                report["sources"].append({"source": site, "candidates": len(candidates), "matched": len(matched)})
                if not args.download:
                    report["sources"][-1]["tracks"] = [candidate.dict() for candidate in matched]
                    continue
                for candidate in matched:
                    if not candidate.url:
                        report["sources"][-1]["detail"] = "no public full-file URL, protected player URLs are excluded"
                        continue
                    allowed_hosts = DOWNLOAD_HOSTS[site]
                    fetch_url._check_hop(candidate.url, allowed_hosts)
                    # Source redirects remain subject to the direct-URL host allowlist.
                    download_cfg = {**cfg, "direct_urls": {**cfg.get("direct_urls", {}), "allowed_hosts": allowed_hosts}}
                    if download_only:
                        name, digest, detail = fetch_url.fetch_download_only(
                            candidate.url, artist, title, out, download_cfg, http=client,
                            known_sha=fetch_songs.known_sha(state),
                        )
                    else:
                        name, digest, detail = fetch_url.fetch(candidate.url, artist, title, out, download_cfg,
                                                             license=args.license, rights=args.rights,
                                                             http=client,
                                                             known_sha=fetch_songs.known_sha(state))
                    state["done"][key] = {"status": "downloaded", "date": time.strftime("%Y-%m-%d", time.gmtime()),
                                          "song": f"{artist} - {title}", "file": name, "detail": detail}
                    state["skipped"].pop(key, None)
                    fetch_songs.save_memory(args.state, state)
                    report.update(downloaded=str(out / name), technical="verified",
                                  usage_rights="not_evaluated" if download_only else (
                                      "owner_declared" if args.rights == "owner" else "license_verified"))
                    saved += 1
                    break
            except (Refused, download.BadAudio, RuntimeError, requests.RequestException, OSError, ValueError) as exc:
                report["sources"].append({"source": site, "state": "refused" if isinstance(exc, Refused) else "unavailable",
                                           "detail": str(exc) if isinstance(exc, Refused) else safe_err(exc)})
            if report["downloaded"]:
                break
        reports.append(report)
    return reports


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artist")
    parser.add_argument("--title")
    parser.add_argument("--queue", help="existing artist | title queue")
    parser.add_argument("--inspect", help="technical validation of an existing local file")
    parser.add_argument("--sites", nargs="+", choices=SITES, default=list(SITES))
    parser.add_argument("--download", action="store_true", help="save a verified file when usage rights pass the existing policy")
    parser.add_argument("--download-only", action="store_true", help="save public audio after technical checks, without evaluating usage rights")
    parser.add_argument("--license", default="")
    parser.add_argument("--rights", choices=["", "owner"], default="")
    parser.add_argument("--out", default=str(ROOT / "accounts/main/audio"))
    parser.add_argument("--state", default=str(ROOT / "out/catalog-songs.md"))
    parser.add_argument("--max", type=int, default=3)
    args = parser.parse_args(argv)
    args.download = args.download or args.download_only
    if sum((bool(args.inspect), bool(args.queue), bool(args.artist or args.title))) != 1:
        parser.error("choose --inspect, --queue, or --artist with --title")
    if not (args.inspect or args.queue) and not (args.artist and args.title):
        parser.error("--artist and --title are required together")
    if args.max < 1:
        parser.error("--max must be positive")
    try:
        reports = run(args)
    except (Refused, download.BadAudio, OSError, ValueError) as exc:
        print(json.dumps({"technical": "failed", "detail": str(exc)}, ensure_ascii=False))
        return 1
    print(json.dumps(reports, ensure_ascii=False, indent=2))
    if args.download:
        return 0 if any(row.get("downloaded") or row.get("result") == "already_saved" for row in reports) else 1
    blocked = [row for row in reports if row.get("sources") and all(
        source.get("state") in ("refused", "unavailable") for source in row["sources"]
    )]
    return 1 if blocked and len(blocked) == len(reports) else 0


if __name__ == "__main__":
    raise SystemExit(main())
