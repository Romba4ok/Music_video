import json
from argparse import Namespace
from pathlib import Path

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


def test_explicit_search_uses_public_html_without_crawler_gate():
    calls = []

    class HTTP:
        def get(self, url, **kwargs):
            calls.append(url)
            return Response(url, HITMO)

    tracks = catalog_audio.CatalogClient(HTTP()).search("hitmo", "Xcho Ветер")
    assert len(tracks) == 2
    assert len(calls) == 1 and "/search?q=" in calls[0]


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


def test_403_logs_response_body_and_headers_without_cookie_or_url_secrets(capsys):
    class HTTP:
        def get(self, url, **kwargs):
            return Response(url, "<h1>Access denied for your country</h1>", code=403, headers={
                "Server": "nginx", "Content-Type": "text/html", "X-Request-ID": "request-123",
                "Set-Cookie": "session=private", "Authorization": "Bearer private", "X-Api-Key": "private",
            })

    with pytest.raises(requests.HTTPError):
        catalog_audio.CatalogClient(HTTP()).request("https://sefon.pro/search/?q=song&token=private")
    logged = json.loads(capsys.readouterr().err)
    assert logged["http_diagnostic"] == 403
    assert logged["body"] == "<h1>Access denied for your country</h1>"
    assert logged["headers"]["Server"] == "nginx" and logged["headers"]["X-Request-ID"] == "request-123"
    assert logged["headers"]["Set-Cookie"] == logged["headers"]["Authorization"] == "[redacted]"
    assert logged["headers"]["X-Api-Key"] == "[redacted]"
    assert logged["url"] == "https://sefon.pro/search/" and logged["body_truncated"] is False


def test_403_diagnostic_marks_body_limit(capsys):
    catalog_audio.log_forbidden(Response("https://sefon.pro/", "x" * 70000, code=403), "https://sefon.pro/")
    logged = json.loads(capsys.readouterr().err)
    assert len(logged["body"]) == 65536 and logged["body_truncated"] is True


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


def test_403_download_is_rejected_without_retry_or_credentials(monkeypatch):
    calls = []

    class HTTP:
        def get(self, url, **kwargs):
            calls.append((url, kwargs))
            return Response(url, code=403)

    client = catalog_audio.CatalogClient(HTTP())
    with pytest.raises(common.Refused, match="HTTP 403"):
        fetch_url._open("https://ru.hitmoz.org/get/music/a.mp3",
                        {**fetch_url.DEFAULTS, "allowed_hosts": ["ru.hitmoz.org"]}, client)
    assert len(calls) == 1
    assert "Authorization" not in calls[0][1].get("headers", {})
