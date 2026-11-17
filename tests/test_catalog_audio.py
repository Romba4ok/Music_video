from argparse import Namespace
from pathlib import Path
from urllib.robotparser import RobotFileParser

import pytest
import requests

from pipeline import catalog_audio, common, download, fetch_url


HITMO = """<ul><li data-musmeta='{"artist":"Xcho","title":"Ветер","url":"/get/cuts/preview.mp3"}'>
<a class="track__info-l" href="/song/123">Ветер</a><span>02:17</span>
<a class="track__download-btn" href="/get/music/original.mp3"></a></li>
<li data-musmeta='{"artist":"Xcho","title":"Ветер (Remix)"}'>
<a class="track__download-btn" href="/get/music/remix.mp3"></a></li></ul>"""

SEFON = """<div class="mp3" data-mp3_id="123"><span class="url_protected" data-url="#secret"></span>
<div class="artist_name"><a>Xcho</a> &amp; <a>DanRi</a></div>
<div class="song_name"><a href="/mp3/123-veter/">Ветер</a></div><span>02:17</span>
<div class="download"><a href="#protected">Скачать</a></div></div>"""


class Response:
    def __init__(self, url, text="", code=200, headers=None):
        self.url, self.text, self.status_code = url, text, code
        self.headers = headers or {}
        self.is_redirect = 300 <= code < 400
        self.closed = False

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(response=self)

    def close(self):
        self.closed = True

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


def test_html_metadata_uses_download_anchor_instead_of_player_clip():
    tracks = catalog_audio.parse_tracks(HITMO, "hitmo", "https://ru.hitmoz.org/search?q=Xcho")
    assert tracks[0].url == "https://ru.hitmoz.org/get/music/original.mp3"
    assert (tracks[0].artist, tracks[0].title, tracks[0].sec) == ("Xcho", "Ветер", 137)
    assert tracks[0].license == "" and tracks[0].landing == "https://ru.hitmoz.org/song/123"
    assert not catalog_audio.sources.matches("Xcho", "Ветер", tracks[1])


def test_sefon_metadata_preserves_protected_download_as_unavailable():
    tracks = catalog_audio.parse_tracks(SEFON, "sefon", "https://sefon.pro/search/?q=Xcho")
    assert len(tracks) == 1
    assert (tracks[0].artist, tracks[0].title, tracks[0].sec) == ("Xcho & DanRi", "Ветер", 137)
    assert tracks[0].url == "" and tracks[0].landing.endswith("/mp3/123-veter/")


@pytest.mark.parametrize("rule,url,expected", [
    ("Disallow: *q=*", "https://ru.hitmoz.org/search?q=Xcho", False),
    ("Disallow: /get/", "https://ru.hitmoz.org/get/music/song.mp3", False),
    ("Disallow: /search", "https://sefon.pro/search/?q=Xcho", False),
    ("Disallow: /get/\nAllow: /get/public/", "https://example.org/get/public/song.mp3", True),
    ("Disallow: /*.mp3$", "https://example.org/song.mp3", False),
    ("Disallow: /*.mp3$", "https://example.org/song.mp3/info", True),
    ("Allow: /", "https://example.org/search?q=Xcho", True),
])
def test_robot_wildcards_queries_and_allow_precedence(rule, url, expected):
    parser = RobotFileParser()
    parser.parse(("User-agent: *\n" + rule).splitlines())
    assert catalog_audio.robots_allows(parser, url) == expected


def test_restricted_search_is_stopped_before_requesting_results():
    calls = []

    class HTTP:
        def get(self, url, **kwargs):
            calls.append(url)
            return Response(url, "User-agent: *\nDisallow: *q=*\nDisallow: /get/")

    with pytest.raises(common.Refused, match="robots.txt"):
        catalog_audio.CatalogClient(HTTP()).search("hitmo", "Xcho Ветер")
    assert calls == ["https://ru.hitmoz.org/robots.txt"]


def test_temporary_search_error_is_retried_and_403_is_final(monkeypatch):
    monkeypatch.setattr(catalog_audio.time, "sleep", lambda seconds: None)
    responses = iter([Response("url", code=503), Response("url", code=200)])
    calls = []

    class HTTP:
        def get(self, url, **kwargs):
            calls.append(url)
            return next(responses)

    client = catalog_audio.CatalogClient(HTTP())
    assert client.request("https://ru.hitmoz.org/").status_code == 200
    assert len(calls) == 2
    responses = iter([Response("url", code=403)])
    with pytest.raises(requests.HTTPError):
        client.request("https://ru.hitmoz.org/")
    assert len(calls) == 3


def test_rights_and_technical_validation_are_independent(tmp_path, monkeypatch):
    raw = tmp_path / "unknown-rights.mp3"
    raw.write_bytes(b"audio")
    monkeypatch.setattr(fetch_url, "_format_name", lambda path: "mp3")
    monkeypatch.setattr(download, "check_audio", lambda path, **kwargs: (path, []))
    report = fetch_url.inspect_audio(raw)
    assert report["technical"] == "verified" and report["usage_rights"] == "not_evaluated"
    assert report["sha256"] == download.file_sha256(raw)
    with pytest.raises(common.Refused, match="подтверждения прав"):
        fetch_url.fetch("https://ru.hitmoz.org/get/music/a.mp3", "A", "T", tmp_path, env={})


def test_queue_download_fallback_and_second_run_without_requests(tmp_path, monkeypatch):
    queue = tmp_path / "queue.md"
    queue.write_text("Xcho | Ветер | | |\n", encoding="utf-8")
    args = Namespace(inspect=None, queue=queue, artist=None, title=None, out=tmp_path / "audio",
                     state=tmp_path / "state.md", sites=["sefon", "hitmo"], download=True, max=1, license="by", rights="")
    searches = []

    class Client:
        def search(self, site, query):
            searches.append(site)
            if site == "sefon":
                raise requests.ConnectTimeout()
            return catalog_audio.parse_tracks(HITMO, site, "https://ru.hitmoz.org/search?q=Xcho")

        def allowed(self, url):
            pass

    def fetch(url, artist, title, out, cfg, **kwargs):
        assert kwargs["license"] == "by" and cfg["direct_urls"]["allowed_hosts"][0] == "ru.hitmoz.org"
        out.mkdir(parents=True)
        path = out / "Xcho - Ветер.mp3"
        path.write_bytes(b"verified audio")
        digest = download.file_sha256(path)
        return path.name, digest, f"hitmo sha256:{digest[:16]}"

    monkeypatch.setattr(fetch_url, "fetch", fetch)
    report = catalog_audio.run(args, client=Client())[0]
    assert searches == ["sefon", "hitmo"] and report["technical"] == "verified"
    assert Path(report["downloaded"]).is_file()
    assert catalog_audio.run(args, client=Client())[0]["result"] == "already_saved"
    assert searches == ["sefon", "hitmo"]


def test_search_without_download_does_not_treat_unknown_license_as_rejection(tmp_path):
    args = Namespace(inspect=None, queue=None, artist="Xcho", title="Ветер", out=tmp_path,
                     state=tmp_path / "state.md", sites=["hitmo"], download=False, max=1)

    class Client:
        def search(self, *args):
            return catalog_audio.parse_tracks(HITMO, "hitmo", "https://ru.hitmoz.org/search?q=Xcho")

    report = catalog_audio.run(args, client=Client())[0]
    assert report["sources"][0]["matched"] == 1
    assert report["usage_rights"] == "not_evaluated" and report["downloaded"] is None


def test_download_hop_is_checked_against_robots_before_network():
    calls = []

    class HTTP:
        def get(self, url, **kwargs):
            calls.append(url)
            return Response(url, "User-agent: *\nDisallow: /get/")

    with pytest.raises(common.Refused, match="robots.txt"):
        catalog_audio.CatalogClient(HTTP()).get("https://ru.hitmoz.org/get/music/a.mp3")
    assert calls == ["https://ru.hitmoz.org/robots.txt"]
