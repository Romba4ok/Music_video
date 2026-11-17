"""Official-source stage: artist pages from MusicBrainz, license declared by the page, links saved when no allowed file, robots.txt, per-song report."""
import json
from argparse import Namespace

from pipeline import fetch_songs as fs, official

CFG = {"licenses_allowed": ["cc0", "pdm", "by"], "sources": {"order": []}, "direct_urls": {"allowed_hosts": []}}
W = {"artist": "Tasso", "title": "Таю", "sec": 0}
CC = "https://creativecommons.org/licenses/by/4.0/"


class Resp:
    def __init__(self, code=200, text="", ctype="text/html"):
        self.status_code, self.text, self.headers, self.encoding = code, text, {"Content-Type": ctype}, "utf-8"
        import io
        self.raw = type("R", (), {"read": lambda s, n, decode_content=True: text.encode()})()

    def close(self):
        pass


class Http:
    def __init__(self, pages, robots="User-agent: *\nAllow: /"):
        self.pages, self.robots, self.calls = pages, robots, []

    def get(self, url, **kw):
        self.calls.append(url)
        if url.endswith("/robots.txt"):
            return Resp(200, self.robots, "text/plain")
        return Resp(*self.pages[url]) if url in self.pages else Resp(404)


def mb(pages, ids=True):
    def gj(url, params=None, headers=None, **k):
        if url.endswith("artist/"):
            return {"artists": [{"id": "x", "name": "Tasso", "score": 100}] if ids else []}
        return {"relations": [{"type": t, "url": {"resource": u}} for t, u in pages]}
    return gj


HOME = '<html><title>Tasso</title><a href="/music/tayu">Таю</a></html>'
SONG_OK = f'<html><title>Таю</title><a rel="license" href="{CC}">cc</a><a href="/files/tayu.mp3">download</a></html>'
SONG_NOLIC = '<html><title>Таю</title><a href="/files/tayu.mp3">download</a></html>'


def run(pages, mbpages, fetch=None, robots="User-agent: *\nAllow: /", ids=True):
    http = Http(pages, robots)
    res = official.try_song(W, CFG, "out", (), http=http, get_json=mb(mbpages, ids), fetch=fetch or (lambda *a, **k: ("Tasso - Таю.mp3", "sha", "url ok")), sleep=lambda s: None)
    return res, http


def test_page_with_declared_cc_license_and_the_song_file_is_downloaded_from_that_host_only():
    got = {}
    res, _ = run({"https://t.example/": (200, HOME), "https://t.example/music/tayu": (200, SONG_OK)}, [("official homepage", "https://t.example/")],
                 fetch=lambda url, a, t, out, cfg, license="", known_sha=(), **k: got.update(url=url, lic=license, hosts=cfg["direct_urls"]["allowed_hosts"]) or ("Tasso - Таю.mp3", "s", "ok"))
    assert res["file"] == "Tasso - Таю.mp3" and got == {"url": "https://t.example/files/tayu.mp3", "lic": CC, "hosts": ["t.example"]}


def test_file_without_a_declared_license_is_not_downloaded_only_its_link_is_kept():
    res, _ = run({"https://t.example/": (200, HOME), "https://t.example/music/tayu": (200, SONG_NOLIC)}, [("official homepage", "https://t.example/")],
                 fetch=lambda *a, **k: 1 / 0)
    assert res["file"] is None and res["links"] and "не объявляет разрешённую лицензию" in res["links"][0][1]


def test_song_page_without_a_file_is_saved_as_a_link():
    res, _ = run({"https://t.example/": (200, HOME), "https://t.example/music/tayu": (200, "<html><title>Таю</title>listen</html>")}, [("official homepage", "https://t.example/")])
    assert res["file"] is None and res["links"][0][0] == "https://t.example/music/tayu"


def test_robots_txt_closed_page_is_not_fetched_and_streaming_hosts_are_link_only():
    res, http = run({"https://t.example/": (200, HOME)}, [("official homepage", "https://t.example/"), ("bandcamp", "https://tasso.bandcamp.com/")], robots="User-agent: *\nDisallow: /")
    assert "https://t.example/" not in http.calls and not any("bandcamp" in c for c in http.calls)
    assert res["links"][0][0] == "https://tasso.bandcamp.com/" and "robots" in res["reason"]


def test_unknown_artist_and_dead_musicbrainz_give_a_reason_not_an_exception():
    assert "артист не найден" in run({}, [], ids=False)[0]["reason"]
    def boom(*a, **k):
        raise ConnectionError()
    assert "MusicBrainz не ответил" in official.try_song(W, CFG, "out", get_json=boom, sleep=lambda s: None)["reason"]


def test_links_file_keeps_one_row_per_song_page_and_the_first_date(tmp_path):
    p = tmp_path / "song-links.md"
    official.save_links(p, [("A - B", "https://x/1", "n1")], "2026-01-01")
    official.save_links(p, [("A - B", "https://x/1", "n2"), ("A - B", "https://x/2", "n3")], "2026-02-02")
    rows = [l for l in p.read_text(encoding="utf-8").splitlines() if l.startswith("| 2026")]
    assert len(rows) == 2 and rows[0].startswith("| 2026-01-01 |") and "n1" in rows[0]


def test_run_report_lists_every_song_with_result_and_reason_and_writes_the_links_file(tmp_path, capsys):
    q = tmp_path / "queue.md"
    q.write_text("Tasso | Таю | | |\nXcho | Ветер | | |\n", encoding="utf-8")
    a = Namespace(out=str(tmp_path / "out"), have_file=None, state=str(tmp_path / "m.md"), queue=str(q), max=5, tries=40, record_used=None, prune=None,
                  discover=False, previews=False, check_list=None, force_retry=False)
    off = lambda w, cfg, out, known=(): ({"file": None, "detail": "", "links": [("https://t.example/p", "страница")], "reason": ""} if w["artist"] == "Tasso"
                                         else {"file": None, "detail": "", "links": [], "reason": "MusicBrainz: артист не найден"})
    fs.run(a, {**CFG, "sources": {"order": []}}, {}, lambda c: [], sleep=lambda s: None, official_try=off)
    rep = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    r = {s["song"]: s for s in rep["songs"]}
    assert r["Tasso - Таю"]["result"] == "link_saved" and r["Xcho - Ветер"]["result"] == "skipped" and "артист не найден" in r["Xcho - Ветер"]["reason"]
    assert "https://t.example/p" in (tmp_path / "song-links.md").read_text(encoding="utf-8")
