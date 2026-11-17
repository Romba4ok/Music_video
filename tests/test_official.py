"""Official-source stage: MusicBrainz recording -> release -> label -> track pages, license declared by the page, exact commercial links, robots.txt,
MusicBrainz rate limit / back-off / switch-off, one request per URL per run, per-song report."""
import json
from argparse import Namespace

import requests

from pipeline import fetch_songs as fs, official

CFG = {"licenses_allowed": ["cc0", "pdm", "by"], "sources": {"order": []}, "direct_urls": {"allowed_hosts": []}}
W = {"artist": "Tasso", "title": "Таю", "sec": 0}
CC = "https://creativecommons.org/licenses/by/4.0/"
NOSLEEP = lambda s: None


class Resp:
    def __init__(self, code=200, text="", ctype="text/html"):
        self.status_code, self.text, self.headers, self.encoding = code, text, {"Content-Type": ctype}, "utf-8"
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


class MB:
    """fake MusicBrainz: artist-level relations, optional recording (with release, label and relations)"""

    def __init__(self, artist_rels=(), recording=None, label_rels=(), artist=True):
        self.artist_rels, self.recording, self.label_rels, self.artist, self.calls = artist_rels, recording, label_rels, artist, []

    def __call__(self, url, params=None, headers=None, **k):
        path = url.split("/ws/2/")[1]
        self.calls.append(path)
        rel = lambda items: {"relations": [{"type": t, "url": {"resource": u}} for t, u in items]}
        if path == "recording/":
            return {"recordings": [{"id": "r1", "title": "Таю", "score": 100, "artist-credit": [{"name": "Tasso"}], "releases": [{"id": "rl1", "status": "Official"}]}] if self.recording else []}
        if path == "recording/r1":
            return rel(self.recording.get("rec", []))
        if path == "release/rl1":
            return {"title": "Альбом", "date": "2024", "label-info": [{"label": {"id": "l1", "name": "Label X"}}], **rel(self.recording.get("rel", []))}
        if path == "label/l1":
            return rel(self.label_rels)
        if path == "artist/":
            return {"artists": [{"id": "a1", "name": "Tasso", "score": 100}] if self.artist else []}
        if path == "artist/a1":
            return rel(self.artist_rels)
        raise AssertionError(path)


HOME = '<html><title>Tasso</title><a href="/music/tayu">Таю</a></html>'
SONG_OK = f'<html><title>Таю</title><a rel="license" href="{CC}">cc</a><a href="/files/tayu.mp3">download</a></html>'
SONG_NOLIC = '<html><title>Таю</title><a href="/files/tayu.mp3">download</a></html>'
FETCH_OK = lambda *a, **k: ("Tasso - Таю.mp3", "sha", "url ok")


def run(pages, mb, fetch=FETCH_OK, robots="User-agent: *\nAllow: /", ctx=None, w=W):
    http = Http(pages, robots)
    return official.try_song(w, CFG, "out", (), http=http, get_json=mb, fetch=fetch, sleep=NOSLEEP, ctx=ctx), http


def test_page_with_declared_cc_license_and_the_song_file_is_downloaded_from_that_host_only():
    got = {}
    fetch = lambda url, a, t, out, cfg, license="", known_sha=(), **k: got.update(url=url, lic=license, hosts=cfg["direct_urls"]["allowed_hosts"]) or ("Tasso - Таю.mp3", "s", "ok")
    res, _ = run({"https://t.example/": (200, HOME), "https://t.example/music/tayu": (200, SONG_OK)}, MB([("official homepage", "https://t.example/")]), fetch)
    assert res["file"] == "Tasso - Таю.mp3" and got == {"url": "https://t.example/files/tayu.mp3", "lic": CC, "hosts": ["t.example"]}


def test_label_site_of_the_exact_release_is_searched_and_its_track_page_gives_the_file():
    mb = MB(recording={"rec": [], "rel": []}, label_rels=[("official homepage", "https://label.example/")], artist=False)
    res, http = run({"https://label.example/": (200, '<a href="/t/tayu">Таю</a>'), "https://label.example/t/tayu": (200, SONG_OK)}, mb)
    assert res["file"] and "https://label.example/t/tayu" in http.calls and mb.calls[:3] == ["recording/", "recording/r1", "release/rl1"]


def test_track_level_free_download_page_from_the_release_is_checked_before_the_artist_homepage():
    mb = MB(recording={"rec": [("download for free", "https://free.example/tayu")], "rel": []}, artist_rels=[("official homepage", "https://t.example/")])
    res, http = run({"https://free.example/tayu": (200, SONG_OK), "https://t.example/": (200, HOME)}, mb)
    assert res["file"] and http.calls[1] == "https://free.example/tayu" or "https://free.example/tayu" in http.calls[:2]


def test_commercial_release_is_saved_as_its_exact_link_and_nothing_is_downloaded():
    mb = MB(recording={"rec": [("purchase for download", "https://store.example/tayu")], "rel": [("streaming music", "https://music.example/album/1")]}, artist=False)
    res, http = run({}, mb, fetch=lambda *a, **k: 1 / 0)
    assert res["file"] is None and [u for u, n in res["links"]] == ["https://store.example/tayu", "https://music.example/album/1"]
    assert all(n.startswith("коммерческий релиз") for u, n in res["links"]) and "лейбл: Label X" in res["reason"] and not http.calls


def test_release_without_any_shop_link_is_saved_as_its_musicbrainz_page():
    res, _ = run({}, MB(recording={"rec": [], "rel": []}, artist=False))
    assert res["links"][0][0] == "https://musicbrainz.org/release/rl1" and "Label X" in res["links"][0][1]


def test_file_without_a_declared_license_is_not_downloaded_only_its_link_is_kept():
    res, _ = run({"https://t.example/": (200, HOME), "https://t.example/music/tayu": (200, SONG_NOLIC)}, MB([("official homepage", "https://t.example/")]), fetch=lambda *a, **k: 1 / 0)
    assert res["file"] is None and "не объявляет разрешённую лицензию" in res["links"][0][1]


def test_track_page_without_a_file_is_saved_as_a_link():
    res, _ = run({"https://t.example/": (200, HOME), "https://t.example/music/tayu": (200, "<html><title>Таю</title>listen</html>")}, MB([("official homepage", "https://t.example/")]))
    assert res["file"] is None and res["links"][0][0] == "https://t.example/music/tayu"


def test_robots_txt_closed_page_is_not_fetched_and_streaming_hosts_are_link_only():
    mb = MB([("official homepage", "https://t.example/"), ("bandcamp", "https://tasso.bandcamp.com/")])
    res, http = run({"https://t.example/": (200, HOME)}, mb, robots="User-agent: *\nDisallow: /")
    assert "https://t.example/" not in http.calls and not any("bandcamp" in c for c in http.calls)
    assert res["links"][0][0] == "https://tasso.bandcamp.com/" and "robots" in res["reason"]


def test_unknown_song_and_artist_give_a_reason_and_a_dead_musicbrainz_is_marked_unavailable():
    assert "ни записи, ни артиста" in run({}, MB(artist=False))[0]["reason"]
    def boom(*a, **k):
        raise ConnectionError()
    r = official.try_song(W, CFG, "out", get_json=boom, sleep=NOSLEEP)["reason"]
    assert "musicbrainz:unavailable" in r   # the memory re-checks such a song on the next run, not in 14 days


class Err(requests.HTTPError):
    def __init__(self, code, retry_after=None):
        super().__init__(str(code))
        self.response = Resp(code)
        if retry_after is not None:
            self.response.headers["Retry-After"] = str(retry_after)


def clock_sleep():
    waits, now = [], [0.0]
    def sleep(s):
        waits.append(round(s, 2))
        now[0] += s
    return waits, (lambda: now[0]), sleep


def test_user_agent_comes_from_musicbrainz_contact_and_is_never_invented():
    assert official.Ctx(env={"MUSICBRAINZ_CONTACT": "https://example.org/vybex"}).ua == {"User-Agent": "VYBEX/1.0 (https://example.org/vybex)"}
    assert official.Ctx(env={}).ua == {"User-Agent": "VYBEX/1.0"} and official.Ctx(env={"MUSICBRAINZ_CONTACT": "  "}).contact == ""
    seen = {}
    ctx = official.Ctx(env={"MUSICBRAINZ_CONTACT": "mail@example.org"})
    ctx.mb("artist/", {"q": 1}, lambda url, params=None, headers=None, **k: seen.update(h=headers, r=k.get("retries")) or {"ok": 1}, NOSLEEP)
    assert seen == {"h": {"User-Agent": "VYBEX/1.0 (mail@example.org)"}, "r": 0}   # one User-Agent for every MusicBrainz call, no hidden instant retries


def test_requests_are_spaced_by_at_least_the_gap_with_a_margin():
    waits, clock, sleep = clock_sleep()
    ctx = official.Ctx(clock=clock, env={})
    for q in range(3):
        ctx.mb("artist/", {"q": q}, lambda *a, **k: {"ok": 1}, sleep)
    assert waits[0] == 0 and waits[1:] == [1.5, 1.5]   # more than the 1 request/second MusicBrainz allows


def test_503_without_retry_after_backs_off_3_6_12_and_the_spacing_grows_then_shrinks_again():
    waits, clock, sleep = clock_sleep()
    ctx = official.Ctx(clock=clock, env={})
    seq = iter([503, 503, 200])
    def gj(*a, **k):
        c = next(seq)
        if c == 503:
            raise Err(503)
        return {"ok": 1}
    assert ctx.mb("artist/", {"q": 1}, gj, sleep) == {"ok": 1}
    assert waits[0] == 0 and 5.2 <= waits[1] <= 5.3 and 9.3 <= waits[2] <= 9.5   # 2.25 + 3, then 3.4 + 6 (the spacing is widened after every 503)
    assert 1.5 <= ctx.gap < 3.4   # and it shrinks again after the success


def test_retry_after_from_the_server_is_obeyed():
    waits, clock, sleep = clock_sleep()
    ctx = official.Ctx(clock=clock, env={})
    seq = iter([Err(503, retry_after=17), None])
    def gj(*a, **k):
        e = next(seq)
        if e:
            raise e
        return {"ok": 1}
    ctx.mb("artist/", {"q": 1}, gj, sleep)
    assert waits[1] >= 17 and waits[1] < 20
    assert official._retry_after(Err(503, retry_after=9999).response) == 120      # capped
    assert official._retry_after(Err(503).response) == 0


def test_a_failed_request_never_switches_musicbrainz_off_the_next_one_is_tried_after_a_longer_pause():
    waits, clock, sleep = clock_sleep()
    ctx = official.Ctx(clock=clock, env={})
    def dead(*a, **k):
        raise Err(503)
    for q in (1, 2):
        try:
            ctx.mb("artist/", {"q": q}, dead, sleep)
        except requests.HTTPError:
            pass
    n = len(waits)
    assert ctx.mb("artist/", {"q": 3}, lambda *a, **k: {"ok": 1}, sleep) == {"ok": 1}   # the server recovered: answered, not "off for the rest of the run"
    assert waits[n] >= 60 and ctx.fails == 0                                          # after two failures the pause before the next request was 60 s


def test_waiting_budget_is_bounded_and_the_song_is_marked_unavailable_for_the_next_run():
    ctx = official.Ctx(env={}, budget=5)
    def dead(*a, **k):
        raise Err(503)
    r = official.try_song(W, CFG, "out", get_json=dead, sleep=NOSLEEP, ctx=ctx)
    assert "musicbrainz:unavailable" in r["reason"] and ctx.budget < 5


def test_answers_are_cached_on_disk_so_the_next_run_asks_nothing_for_known_releases(tmp_path):
    f = tmp_path / "musicbrainz-cache.json"
    mb1 = MB([("official homepage", "https://t.example/")])
    official.try_song(W, CFG, "out", http=Http({"https://t.example/": (200, HOME)}), get_json=mb1, fetch=FETCH_OK, sleep=NOSLEEP, ctx=(c1 := official.Ctx(env={}, cache_file=f)))
    c1.save()
    assert mb1.calls and f.exists()
    mb2 = MB([("official homepage", "https://t.example/")])
    official.try_song(W, CFG, "out", http=Http({"https://t.example/": (200, HOME)}), get_json=mb2, fetch=FETCH_OK, sleep=NOSLEEP, ctx=official.Ctx(env={}, cache_file=f))
    assert mb2.calls == []                                            # same recording / artist: no request at all
    old = json.loads(f.read_text(encoding="utf-8"))
    for v in old.values():
        v["t"] = 1.0                                                  # older than the 30-day TTL
    f.write_text(json.dumps(old), encoding="utf-8")
    mb3 = MB([("official homepage", "https://t.example/")])
    official.try_song(W, CFG, "out", http=Http({"https://t.example/": (200, HOME)}), get_json=mb3, fetch=FETCH_OK, sleep=NOSLEEP, ctx=official.Ctx(env={}, cache_file=f))
    assert mb3.calls


def test_two_songs_of_one_artist_cost_one_musicbrainz_artist_lookup_and_one_page_fetch():
    mb, ctx = MB([("official homepage", "https://t.example/")]), official.Ctx(env={})
    pages = {"https://t.example/": (200, HOME)}
    http = Http(pages)
    for title in ("Таю", "Другая"):
        official.try_song({"artist": "Tasso", "title": title, "sec": 0}, CFG, "out", (), http=http, get_json=mb, fetch=FETCH_OK, sleep=NOSLEEP, ctx=ctx)
    assert mb.calls.count("artist/") == 1 and mb.calls.count("artist/a1") == 1 and http.calls.count("https://t.example/") == 1


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
    off = lambda w, cfg, out, known=(), ctx=None: ({"file": None, "detail": "", "links": [("https://t.example/p", "страница")], "reason": ""} if w["artist"] == "Tasso"
                                                   else {"file": None, "detail": "", "links": [], "reason": "musicbrainz:unavailable (HTTPError HTTP 503)"})
    fs.run(a, {**CFG, "sources": {"order": []}}, {}, lambda c: [], sleep=lambda s: None, official_try=off)
    rep = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    r = {s["song"]: s for s in rep["songs"]}
    assert r["Tasso - Таю"]["result"] == "link_saved" and r["Xcho - Ветер"]["result"] == "skipped" and "musicbrainz:unavailable" in r["Xcho - Ветер"]["reason"]
    assert "https://t.example/p" in (tmp_path / "song-links.md").read_text(encoding="utf-8")
    assert rep["source_states"]["musicbrainz:unavailable"] == 1
    fs.run(a, {**CFG, "sources": {"order": []}}, {}, lambda c: [], sleep=lambda s: None, official_try=off)   # the failed song is re-checked at once, the known one is not
    assert json.loads(capsys.readouterr().out.strip().splitlines()[-1])["checked"] == 1
