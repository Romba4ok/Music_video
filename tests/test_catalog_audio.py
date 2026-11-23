import json
import base64
import threading
from argparse import Namespace
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest
import requests

from pipeline import catalog_audio, common, download, fetch_url


@pytest.fixture(autouse=True)
def no_audio_proxy(monkeypatch):
    monkeypatch.delenv("AUDIO_PROXY_URL", raising=False)


HITMO = """<ul><li data-musmeta='{"artist":"Xcho","title":"Ветер","url":"/get/cuts/preview.mp3"}'>
<a class="track__info-l" href="/song/123">Ветер</a><span>02:17</span>
<a class="track__download-btn" href="/get/music/original.mp3"></a></li>
<li data-musmeta='{"artist":"Xcho","title":"Ветер (Remix)"}'>
<a class="track__download-btn" href="/get/music/remix.mp3"></a></li></ul>"""

SEFON = """<div class="mp3" data-mp3_id="123"><span class="url_protected" data-url="#secret"></span>
<div class="artist_name"><a>Xcho</a> &amp; <a>DanRi</a></div>
<div class="song_name"><a href="/mp3/123-veter/">Ветер</a></div><span>02:17</span>
<div class="download"><a href="#protected">Скачать</a></div></div>"""

MP3PM = """<ul><li class="cplayer-sound-item" data-sound-url="https://cs1.mp3.pm/listen/1/clip.mp3"
data-download-url="https://cs1.mp3.pm/download/1/full.mp3">
<h4><i class="cplayer-data-sound-author">Xcho</i>
<a href="https://42-xcho.mp3.pm/song/1-veter/"><b class="cplayer-data-sound-title">Ветер</b></a></h4>
<em class="cplayer-data-sound-time">02:17</em></li></ul>"""


def test_mp3pm_reads_explicit_download_metadata_and_excludes_listen_only():
    track, = catalog_audio.parse_tracks(MP3PM, "mp3pm", "https://mp3.pm/")
    assert (track.artist, track.title, track.sec) == ("Xcho", "Ветер", 137)
    assert track.url == "https://cs1.mp3.pm/download/1/full.mp3"
    assert track.landing == "https://42-xcho.mp3.pm/song/1-veter/"
    listen_only = MP3PM.replace('data-download-url="https://cs1.mp3.pm/download/1/full.mp3"', '')
    assert catalog_audio.parse_tracks(listen_only, "mp3pm", "https://mp3.pm/")[0].url == ""


def test_mp3pm_search_follows_published_redirect_to_search_subdomain():
    calls = []

    class HTTP:
        def post(self, url, **kwargs):
            calls.append(url)
            assert kwargs['data'] == {'q': 'Xcho Ветер'}
            return Response(url, '"https://s-query.mp3.pm/"')

        def get(self, url, **kwargs):
            calls.append(url)
            return Response(url, MP3PM)

    tracks = catalog_audio.CatalogClient(HTTP()).search("mp3pm", "Xcho Ветер")
    assert len(tracks) == 1 and calls[0] == "https://mp3.pm/public/api.search.php"
    assert calls[1] == "https://s-query.mp3.pm/"


@pytest.mark.parametrize("target", ["https://mp3.pm.evil.test/", "https://evilmp3.pm/",
                                    "http://s-query.mp3.pm/", "https://user:pass@s-query.mp3.pm/",
                                    "https://s-query.mp3.pm:8443/"])
def test_mp3pm_search_refuses_redirect_outside_https_catalog(target):
    calls = []

    class HTTP:
        def post(self, url, **kwargs):
            calls.append(url)
            return Response(url, target)

    with pytest.raises(common.Refused):
        catalog_audio.CatalogClient(HTTP()).search("mp3pm", "Xcho Ветер")
    assert len(calls) == 1


MUZLAP = """<div class="short js-item" data-track="/uploads/music/full.mp3" data-title="Ветер" data-artist="Xcho">
<a href="/123-xcho-veter.html"><div class="short-title">Ветер</div></a><div class="short-time">2:17</div></div>"""


def test_muzlap_uses_published_form_and_track_attributes():
    calls = []

    class HTTP:
        def post(self, url, **kwargs):
            calls.append(url)
            assert kwargs['data'] == {'do': 'search', 'subaction': 'search', 'story': 'Xcho Ветер'}
            return Response(url, MUZLAP)

    track, = catalog_audio.CatalogClient(HTTP()).search('muzlap', 'Xcho Ветер')
    assert calls == ['https://muzlap.com/']
    assert (track.artist, track.title, track.sec) == ('Xcho', 'Ветер', 137)
    assert track.url == 'https://muzlap.com/uploads/music/full.mp3'
    assert track.landing == 'https://muzlap.com/123-xcho-veter.html'


@pytest.mark.parametrize("missing", ["form", "results"])
def test_missing_mp3pm_result_does_not_disable_later_queries(missing):
    calls = []

    class HTTP:
        def post(self, url, **kwargs):
            calls.append("form")
            code = 404 if missing == "form" and len(calls) == 1 else 200
            return Response(url, 'https://s-query.mp3.pm/', code=code)

        def get(self, url, **kwargs):
            calls.append("results")
            code = 404 if missing == "results" and calls.count("results") == 1 else 200
            return Response(url, MP3PM, code=code)

    client = catalog_audio.CatalogClient(HTTP())
    assert client.search('mp3pm', 'not in catalog') == []
    assert client.search('mp3pm', 'Xcho Ветер')[0].artist == 'Xcho'
    assert calls.count("form") == 2


def test_proxy_applies_to_public_post_search(monkeypatch):
    monkeypatch.setenv('AUDIO_PROXY_URL', 'https://user:pass@proxy.example:443')

    class HTTP:
        def post(self, url, **kwargs):
            assert kwargs['proxies'] == {scheme: 'https://user:pass@proxy.example:443' for scheme in ('http', 'https')}
            return Response(url, MUZLAP)

    assert catalog_audio.CatalogClient(HTTP()).search('muzlap', 'Xcho Ветер')


@pytest.mark.parametrize('site', ['muztop', 'spaces', 'hitparad'])
def test_extra_catalogs_follow_only_the_published_public_search_form(site):
    base, path = catalog_audio.SITES[site]
    calls = []
    form = '<form action="/find" method="get"><input name="q" type="search"><input type="hidden" name="kind" value="audio"></form>'
    result = '<script type="application/ld+json">' + json.dumps({
        '@type': 'MusicRecording', 'name': 'Ветер', 'byArtist': {'name': 'Xcho'},
        'duration': 'PT2M17S', 'audio': {'@type': 'AudioObject', 'contentUrl': base + '/file.mp3'},
    }) + '</script>'

    class HTTP:
        def get(self, url, **kwargs):
            calls.append(url)
            return Response(url, form if len(calls) == 1 else result)

    track, = catalog_audio.CatalogClient(HTTP()).search(site, 'Xcho Ветер')
    assert calls[0] == base + path and calls[1].startswith(base + '/find?')
    assert 'kind=audio' in calls[1] and 'q=Xcho' in calls[1]
    assert (track.artist, track.title, track.sec, track.url) == ('Xcho', 'Ветер', 137, base + '/file.mp3')


def test_extra_catalog_does_not_execute_access_challenge_or_send_login():
    calls = []

    class HTTP:
        def get(self, url, **kwargs):
            calls.append(url)
            return Response(url, '<script>document.cookie="js_passed=2"</script>')

    with pytest.raises(common.Refused, match='challenge'):
        catalog_audio.CatalogClient(HTTP()).search('spaces', 'Xcho Ветер')
    assert len(calls) == 1


def test_extra_catalog_refuses_search_form_on_an_unrelated_host():
    calls = []

    class HTTP:
        def get(self, url, **kwargs):
            calls.append(url)
            return Response(url, '<form action="https://other.example/find"><input name="q"></form>')

    with pytest.raises(common.Refused, match='origin'):
        catalog_audio.CatalogClient(HTTP()).search('muztop', 'Xcho Ветер')
    assert len(calls) == 1


def test_login_form_is_not_used_as_public_search():
    class HTTP:
        def get(self, url, **kwargs):
            return Response(url, '<form><input name="q"><input name="password" type="password"></form>')

    with pytest.raises(common.Refused, match='no public search'):
        catalog_audio.CatalogClient(HTTP()).search('hitparad', 'Xcho Ветер')


def test_all_seven_requested_catalogs_are_registered():
    assert set(catalog_audio.SITES) == {'hitmo', 'sefon', 'mp3pm', 'muzlap', 'muztop', 'spaces', 'hitparad'}


def test_extra_catalog_result_404_is_an_empty_query_not_a_dead_source():
    calls = []

    class HTTP:
        def get(self, url, **kwargs):
            calls.append(url)
            if '/find?' in url:
                return Response(url, code=404)
            return Response(url, '<form action="/find"><input name="q"></form>')

    client = catalog_audio.CatalogClient(HTTP())
    assert client.search('hitparad', 'First missing song') == []
    assert client.search('hitparad', 'Next song') == []
    assert len(calls) == 4


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


def test_audio_proxy_is_used_for_search_and_each_download_redirect(monkeypatch):
    proxy = "http://proxy-user:proxy-password@proxy.example:8080"
    monkeypatch.setenv("AUDIO_PROXY_URL", proxy)
    monkeypatch.setenv("HTTPS_PROXY", "http://other-proxy.example:8080")
    calls = []

    class HTTP:
        def get(self, url, **kwargs):
            calls.append((url, kwargs))
            if "/search?" in url:
                return Response(url, HITMO)
            if "ru.hitmoz.org" in url:
                return Response(url, code=302, headers={"Location": "https://cdn12.deliciousoranges.com/song.mp3"})
            return Response(url)

    transport = HTTP()
    client = catalog_audio.CatalogClient(transport)
    assert client.search("hitmo", "Xcho Ветер")
    response = fetch_url._open("https://ru.hitmoz.org/get/music/song.mp3",
                              {**fetch_url.DEFAULTS, "allowed_hosts": catalog_audio.DOWNLOAD_HOSTS["hitmo"]}, client)
    assert response.status_code == 200 and len(calls) == 3
    for _, kwargs in calls:
        assert kwargs["proxies"] == {"http": proxy, "https": proxy}
        assert "verify" not in kwargs
    transport.get("https://www.googleapis.com/drive/v3/files")
    assert "proxies" not in calls[-1][1]


def test_download_candidate_passes_proxy_client_to_the_actual_transfer(tmp_path, monkeypatch):
    monkeypatch.setenv("AUDIO_PROXY_URL", "http://proxy.example:8080")
    candidate = catalog_audio.parse_tracks(HITMO, "hitmo", "https://ru.hitmoz.org/search?q=Xcho")[0]
    clients = []

    def fetch(url, artist, title, destination, cfg, **kwargs):
        clients.append(kwargs["http"])
        return "Xcho - Ветер.mp3", "digest", "detail"

    monkeypatch.setattr(fetch_url, "fetch_download_only", fetch)
    result = catalog_audio.download_candidate(candidate, tmp_path, common.load_config())
    assert result.name == "Xcho - Ветер.mp3"
    assert clients[0].proxies["https"] == "http://proxy.example:8080"


@pytest.mark.parametrize("value", [
    "proxy.example:8080", "socks5://proxy.example:1080", "http://user:secret@proxy.example",
    "http://user:secret@proxy.example:bad", "http://proxy.example:8080/?secret=private",
])
def test_invalid_proxy_fails_without_disclosing_its_value(value, monkeypatch):
    monkeypatch.setenv("AUDIO_PROXY_URL", value)
    with pytest.raises(common.Refused) as exc:
        catalog_audio.CatalogClient()
    assert value not in str(exc.value) and "secret" not in str(exc.value)


def test_proxy_credentials_are_removed_from_403_diagnostics(monkeypatch, capsys):
    proxy = "https://proxy-user:p%40ssword@proxy.example:8443"
    monkeypatch.setenv("AUDIO_PROXY_URL", proxy)
    response = Response("https://sefon.pro/", f"Rejected {proxy} p@ssword proxy-user", code=403,
                        headers={"Via": "proxy.example", "Proxy-Authorization": "Basic private"})
    catalog_audio.log_forbidden(response, response.url)
    output = capsys.readouterr().err
    assert all(secret not in output for secret in (proxy, "p%40ssword", "p@ssword", "proxy-user", "proxy.example", "private"))
    assert json.loads(output)["headers"]["Proxy-Authorization"] == "[redacted]"


def test_requests_really_connects_to_authenticated_proxy_without_direct_fallback(monkeypatch):
    connections = []

    class Proxy(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_CONNECT(self):
            connections.append((self.path, self.headers.get("Proxy-Authorization")))
            self.send_response(407)
            self.send_header("Content-Length", "0")
            self.end_headers()

    server = HTTPServer(("127.0.0.1", 0), Proxy)
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    try:
        monkeypatch.setenv("AUDIO_PROXY_URL", f"http://proxy-user:proxy-password@127.0.0.1:{server.server_port}")
        monkeypatch.setenv("HTTPS_PROXY", "http://unreachable.invalid:1")
        with pytest.raises(requests.exceptions.ProxyError):
            catalog_audio.CatalogClient().get("https://sefon.pro/search/?q=test", timeout=2)
        authorization = "Basic " + base64.b64encode(b"proxy-user:proxy-password").decode()
        assert connections == [("sefon.pro:443", authorization)]
    finally:
        server.shutdown()
        server.server_close()
        worker.join(timeout=2)
