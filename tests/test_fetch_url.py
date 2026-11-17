"""Direct-URL download against a real local HTTP server (127.0.0.1 is the only allowed host in the test config)."""
import json
import subprocess
import threading
import time
from argparse import Namespace
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from pipeline import fetch_songs, fetch_url
from pipeline.common import Refused

CFG = {"licenses_allowed": ["cc0", "pdm", "by"], "sources": {"order": []},
       "direct_urls": {"allowed_hosts": ["127.0.0.1"], "min_sec": 3, "max_sec": 600, "max_mb": 5, "timeout": 2, "max_redirects": 3, "retries": 1}}
OWNER = {"VYBEX_OWNER_DECLARES_RIGHTS": "1"}
TYPES = {"mp3": "audio/mpeg", "wav": "audio/wav", "flac": "audio/flac", "m4a": "audio/mp4"}
CODEC = {"mp3": ["-c:a", "libmp3lame"], "wav": ["-c:a", "pcm_s16le"], "flac": ["-c:a", "flac"], "m4a": ["-c:a", "aac"]}


def make_audio(path, kind, dur=6):
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", f"sine=frequency=440:duration={dur}", *CODEC[kind], str(path)], check=True)
    return path.read_bytes()


@pytest.fixture()
def server(tmp_path):
    files = {f"/song.{k}": (make_audio(tmp_path / f"s.{k}", k), TYPES[k]) for k in TYPES}
    files["/fake.mp3"] = (b"<html>not audio at all</html>" * 50, "audio/mpeg")  # HTML renamed to .mp3
    files["/page"] = (b"<html></html>", "text/html")
    files["/big.mp3"] = (b"x" * (6 * 1024 * 1024), "audio/mpeg")

    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def redirect(self, to):
            self.send_response(302)
            self.send_header("Location", to)
            self.end_headers()

        def do_GET(self):
            if self.path == "/redir":
                self.redirect("/song.mp3")
            elif self.path == "/out":  # redirect to a host that is not on the list
                self.redirect("http://localhost:1/x.mp3")
            elif self.path == "/loop":
                self.redirect("/loop")
            elif self.path == "/slow":
                time.sleep(4)
            elif self.path == "/private":
                self.send_response(403)
                self.end_headers()
            elif self.path in files:
                body, ctype = files[self.path]
                self.send_response(200)
                self.send_header("Content-Type", ctype)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            else:
                self.send_response(404)
                self.end_headers()

    srv = HTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_port}"
    srv.shutdown()


def get(server, path, tmp_path, **kw):
    kw.setdefault("license", "by")
    return fetch_url.fetch(server + path, "Артист", "Песня", tmp_path / "out", CFG, env=OWNER, **kw)


@pytest.mark.parametrize("kind", ["mp3", "wav", "flac", "m4a"])
def test_all_four_formats_end_up_as_a_checked_mp3_with_license_sidecar(server, tmp_path, kind):
    name, sha, detail = get(server, f"/song.{kind}", tmp_path)
    assert name == "Артист - Песня.mp3" and (tmp_path / "out" / name).stat().st_size > 1000
    side = json.loads((tmp_path / "out" / (name + ".license.json")).read_text(encoding="utf-8"))
    assert side["license"] == "by" and side["sha256"] == sha and side["source"].endswith(f"/song.{kind}") and "Артист" in side["attribution"]


def test_redirect_inside_the_allowlist_is_followed_and_outside_is_refused(server, tmp_path):
    assert get(server, "/redir", tmp_path)[0] == "Артист - Песня.mp3"
    with pytest.raises(Refused, match="не в списке"):
        get(server, "/out", tmp_path)
    with pytest.raises(Refused, match="перенаправлений"):
        get(server, "/loop", tmp_path)


def test_host_not_on_the_list_and_bad_scheme_are_refused_before_any_request(tmp_path):
    for url, why in (("https://other.example/a.mp3", "не в списке"), ("ftp://127.0.0.1/a.mp3", "схема")):
        with pytest.raises(Refused, match=why):
            fetch_url.fetch(url, "A", "T", tmp_path, CFG, license="by")


def test_rights_gate_needs_an_allowed_license_or_the_owner_declaration(server, tmp_path):
    with pytest.raises(Refused, match="подтверждения прав"):
        fetch_url.fetch(server + "/song.mp3", "A", "T", tmp_path, CFG, license="by-nc", env=OWNER)  # NC is not allowed
    with pytest.raises(Refused, match="подтверждения прав"):
        fetch_url.fetch(server + "/song.mp3", "A", "T", tmp_path, CFG, rights="owner", env={})  # the owner declaration is missing
    assert fetch_url.fetch(server + "/song.mp3", "A", "T", tmp_path, CFG, rights="owner", env=OWNER)[0] == "A - T.mp3"


def test_http_errors_timeouts_html_disguised_as_mp3_and_size_cap(server, tmp_path):
    with pytest.raises(Exception, match="404"):
        get(server, "/missing.mp3", tmp_path)
    with pytest.raises(Refused, match="HTTP 403"):
        get(server, "/private", tmp_path)
    with pytest.raises(RuntimeError, match="Timeout"):
        get(server, "/slow", tmp_path)
    with pytest.raises(Refused, match="не аудио"):
        get(server, "/page", tmp_path)
    with pytest.raises(Refused, match="ffprobe"):
        get(server, "/fake.mp3", tmp_path)
    with pytest.raises(Refused, match="МБ"):
        get(server, "/big.mp3", tmp_path)
    assert not list((tmp_path / "out").glob("*.mp3"))  # nothing half-saved


def test_too_short_audio_is_refused(server, tmp_path):
    cfg = {**CFG, "direct_urls": {**CFG["direct_urls"], "min_sec": 30}}
    with pytest.raises(Exception, match="shorter"):
        fetch_url.fetch(server + "/song.mp3", "A", "T", tmp_path, cfg, license="by")


def test_the_same_file_is_not_saved_twice(server, tmp_path):
    _, sha, _ = get(server, "/song.mp3", tmp_path)
    with pytest.raises(fetch_url.Duplicate):
        get(server, "/song.mp3", tmp_path, known_sha={sha[:16]})


def test_cli_writes_the_memory_and_skips_a_known_song(server, tmp_path, monkeypatch):
    monkeypatch.setattr(fetch_url, "load_config", lambda: CFG)
    monkeypatch.setenv("VYBEX_OWNER_DECLARES_RIGHTS", "1")
    mem, out = tmp_path / "songs.md", tmp_path / "out"
    args = [server + "/song.mp3", "--artist", "Артист", "--title", "Песня", "--license", "by", "--out", str(out), "--state", str(mem)]
    assert fetch_url.main(args) == 0
    text = mem.read_text(encoding="utf-8")
    assert "downloaded" in text and "sha256:" in text
    assert fetch_url.main(args) == 0  # a known song: duplicate, exit 0, nothing new
    bad = [server + "/missing.mp3", "--artist", "X", "--title", "Y", "--license", "by", "--out", str(out), "--state", str(mem)]
    assert fetch_url.main(bad) == 1


def test_queue_md_link_is_fetched_by_the_songs_job_and_recorded(server, tmp_path, monkeypatch):
    monkeypatch.setenv("VYBEX_OWNER_DECLARES_RIGHTS", "1")
    q = tmp_path / "queue.md"
    q.write_text(f"Артист | Песня | | {server}/song.mp3\nДругой | Ссылка | | {server}/missing.mp3\n", encoding="utf-8")
    a = Namespace(out=str(tmp_path / "out"), have_file=None, state=str(tmp_path / "m.md"), queue=str(q), max=5, tries=40,
                  record_used=None, prune=None, discover=False, previews=False, check_list=None, force_retry=False)
    got = fetch_songs.run(a, CFG, {}, lambda c: [], sleep=lambda s: None)
    assert got == ["Артист - Песня.mp3"]
    mem = fetch_songs.load_memory(tmp_path / "m.md")
    assert len(mem["done"]) == 1 and len(mem["skipped"]) == 1
    assert "ссылка" in list(mem["skipped"].values())[0]["detail"]
