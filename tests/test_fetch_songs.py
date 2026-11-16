import json
from argparse import Namespace

from pipeline import fetch_songs, sources
from pipeline.sources import Candidate

CC = "https://creativecommons.org/licenses/by/4.0/"


def cand(title="Таю", artist="Tasso", lic=CC, sec=200, source="openverse"):
    return Candidate(source, title, artist, "https://x/a.mp3", lic, lic, "https://x/page", sec=sec)


def test_matches_accepts_exact_and_rejects_other_recordings():
    ok = lambda c, sec=0: sources.matches("Tasso", "Таю", c, sec)
    assert ok(cand())
    assert not ok(cand(title="Таю (Remix)"))            # remix is another recording
    assert not ok(cand(title="Таю - cover"))
    assert not ok(cand(title="Другая песня"))            # wrong title
    assert not ok(cand(artist="Someone Else"))           # wrong artist
    assert not ok(cand(sec=30), sec=200)                 # a 30 s preview of a 200 s song
    assert ok(cand(sec=190), sec=200)


def test_archive_searcher_filters_license_before_file_request(monkeypatch):
    calls = []

    def fake(url, params=None, **kw):
        calls.append(url)
        if "advancedsearch" in url:
            return {"response": {"docs": [{"identifier": "good", "title": "T", "creator": ["A"], "licenseurl": CC},
                                          {"identifier": "nc", "title": "T", "licenseurl": "https://creativecommons.org/licenses/by-nc/4.0/"}]}}
        return {"files": [{"name": "t one.mp3", "source": "original", "title": "T", "length": "201.5"}, {"name": "t.jpg", "source": "original"}]}

    monkeypatch.setattr(sources, "get_json", fake)
    out = sources._archive("q", 5, {"licenses_allowed": ["cc0", "pdm", "by"]}, {})
    assert [c.url for c in out] == ["https://archive.org/download/good/t%20one.mp3"] and out[0].sec == 201.5
    assert not any("/nc" in u for u in calls)           # the by-nc item cost no file request


def test_soundcloud_needs_key_and_keeps_only_downloadable(monkeypatch):
    import pytest
    from pipeline.common import NeedsAuth
    with pytest.raises(NeedsAuth):
        sources._soundcloud("q", 3, {}, {})
    monkeypatch.setattr(sources, "get_json", lambda *a, **k: [
        {"title": "A", "user": {"username": "u"}, "downloadable": True, "download_url": "https://api.soundcloud.com/d", "license": "cc-by", "duration": 180000},
        {"title": "B", "user": {"username": "u"}, "downloadable": False, "license": "cc-by"}])
    out = sources._soundcloud("q", 3, {}, {"SOUNDCLOUD_CLIENT_ID": "k"})
    assert len(out) == 1 and out[0].sec == 180 and sources.license_ok(out[0].license, ["by"])


def mkfile(tmp_path):
    f = tmp_path / "raw.mp3"
    f.write_bytes(b"x")
    return f


def test_fetch_one_downloads_checks_and_names_file(tmp_path):
    cfg = {"licenses_allowed": ["cc0", "pdm", "by"], "sources": {"order": ["local", "openverse"]}}
    seen = {}

    def check(p, **kw):
        seen.update(kw)
        return p, []

    name, why = fetch_songs.fetch_one({"artist": "Tasso", "title": "Таю", "sec": 0}, cfg, tmp_path / "o",
                                      searchers={"openverse": lambda q, n, c, e: [cand(), cand(title="Таю remix")]},
                                      dl=lambda c, d, cfg: mkfile(tmp_path), check=check)
    assert name == "Tasso - Таю.mp3" and (tmp_path / "o" / name).exists()
    side = json.loads((tmp_path / "o" / (name + ".license.json")).read_text(encoding="utf-8"))
    assert "Tasso" in side["attribution"] and seen["min_sec"] == 90  # full track, not a preview


def test_fetch_one_skips_when_nothing_matches_and_marks_dead_source(tmp_path):
    cfg = {"licenses_allowed": ["by"], "sources": {"order": ["openverse", "archive"]}}

    def boom(q, n, c, e):
        raise ConnectionError("down")

    dead = set()
    name, why = fetch_songs.fetch_one({"artist": "Tasso", "title": "Таю", "sec": 0}, cfg, tmp_path,
                                      searchers={"openverse": lambda q, n, c, e: [cand(lic="all-rights-reserved")], "archive": boom}, dead=dead)
    assert name is None and "no licensed match" in why and dead == {"archive"}


def run_args(tmp_path, queue="", **kw):
    q = tmp_path / "queue.md"
    q.write_text(queue, encoding="utf-8")
    return Namespace(out=str(tmp_path / "out"), have_file=None, state=str(tmp_path / "memory.md"), queue=str(q), max=5, tries=40, record_used=None, prune=None, discover=False, previews=False, **kw)


def test_run_journal_dedup_and_retry_window(tmp_path, monkeypatch):
    cfg = {"licenses_allowed": ["by"], "sources": {"order": ["openverse"]}}
    searchers = {"openverse": lambda q, n, c, e: [cand()] if "Таю" in q else []}
    monkeypatch.setattr(sources, "SEARCHERS", searchers)
    monkeypatch.setattr(fetch_songs.download, "download", lambda c, d, cfg=None, http=None: mkfile(tmp_path))
    monkeypatch.setattr(fetch_songs.download, "check_audio", lambda p, **kw: (p, []))
    chart = lambda cfg: [{"title": "Tasso - Таю", "sec": 0}, {"title": "Nobody - Нету", "sec": 0}]
    a = run_args(tmp_path, "Tasso | Таю | | |\n")
    got = fetch_songs.run(a, cfg, searchers, chart, sleep=lambda s: None)
    assert got == ["Tasso - Таю.mp3"]                    # queue and chart both list it: downloaded once
    st = fetch_songs.load_memory(tmp_path / "memory.md")
    assert len(st["done"]) == 1 and len(st["skipped"]) == 1
    assert fetch_songs.run(a, cfg, searchers, chart, sleep=lambda s: None) == []   # done is not repeated, skipped waits RETRY_DAYS


def test_run_skips_songs_already_in_drive(tmp_path):
    have = tmp_path / "have.txt"
    have.write_text("Tasso - Таю.mp3\n", encoding="utf-8")
    a = run_args(tmp_path, "Tasso | Таю | | |\n")
    a.have_file = str(have)
    cfg = {"licenses_allowed": ["by"], "sources": {"order": ["openverse"]}}
    assert fetch_songs.run(a, cfg, {"openverse": lambda *x: 1 / 0}, lambda c: [], sleep=lambda s: None) == []  # a search would have crashed the searcher


def test_memory_md_roundtrip_and_feat_is_same_song(tmp_path):
    st = {"done": {}, "skipped": {}}
    fetch_songs.record_used(st, ["Guf - Kalpak (Feat. Mark).mp3", "Баста - Моя игра.mp3"], "2026-11-16")
    f = tmp_path / "m.md"
    fetch_songs.save_memory(f, st)
    text = f.read_text(encoding="utf-8")
    assert text.startswith("# Память песен") and "| used | 2026-11-16 | Guf - Kalpak (Feat. Mark) |" in text
    back = fetch_songs.load_memory(f)
    assert fetch_songs.key("Guf", "Kalpak") in back["done"] and len(back["done"]) == 2   # 'Kalpak' = 'Kalpak (Feat. Mark)'


def test_record_used_only_mode_searches_nothing(tmp_path):
    names = tmp_path / "done.txt"
    names.write_text("Tasso - Таю.mp3\n\n", encoding="utf-8")
    a = run_args(tmp_path, "Tasso | Таю | | |\n")
    a.record_used = str(names)
    assert fetch_songs.run(a, {"licenses_allowed": ["by"], "sources": {"order": ["openverse"]}}, {"openverse": lambda *x: 1 / 0}, lambda c: 1 / 0) == []
    assert len(fetch_songs.load_memory(tmp_path / "memory.md")["done"]) == 1


def test_chart_keeps_only_russian_or_owners_artists_owners_first():
    taste = {"guf", "jahkhalib"}
    chart = lambda cfg: [{"title": "Taylor Swift - The Fate of Ophelia"}, {"title": "Djo - End of Beginning"}, {"title": "Tasso - Таю"},
                         {"title": "Jah Khalib - Na Parallel`nykh Putjakh"}, {"title": "Guf - Kalpak (Feat. Mark)"}]
    got = fetch_songs.wanted({}, "", chart, taste)
    assert [(w["artist"], w["title"]) for w in got] == [("Jah Khalib", "Na Parallel`nykh Putjakh"), ("Guf", "Kalpak (Feat. Mark)"), ("Tasso", "Таю")]


def test_queue_is_not_filtered_and_taste_comes_from_used_rows():
    st = {"done": {}, "skipped": {}}
    fetch_songs.record_used(st, ["Guf - Дно.mp3", "Oxxxymiron - Тысячелетний герой.mp3"], "2026-11-16")
    assert fetch_songs.taste_artists(st) == {"guf", "oxxxymiron"}
    assert [w["artist"] for w in fetch_songs.wanted({}, "Some Latin | Song | | |\n", lambda c: [], set())] == ["Some Latin"]


def test_prune_lists_misfit_downloads_and_forgets_them(tmp_path):
    f = tmp_path / "m.md"
    st = {"done": {}, "skipped": {}}
    for song, file in [("Taylor Swift - The Fate of Ophelia", "Taylor Swift - The Fate of Ophelia.mp3"), ("Tasso - Таю", "Tasso - Таю.mp3")]:
        a, t = fetch_songs.parse_name(song)
        st["done"][fetch_songs.key(a, t)] = {"status": "downloaded", "date": "2026-11-16", "song": song, "file": file, "detail": ""}
    fetch_songs.save_memory(f, st)
    a = run_args(tmp_path)
    a.state, a.prune = str(f), str(tmp_path / "prune.txt")
    fetch_songs.run(a, {}, {}, lambda c: 1 / 0)
    assert (tmp_path / "prune.txt").read_text(encoding="utf-8").splitlines() == ["Taylor Swift - The Fate of Ophelia.mp3", "Taylor Swift - The Fate of Ophelia.mp3.license.json"]
    back = fetch_songs.load_memory(f)
    assert len(back["done"]) == 1 and len(back["skipped"]) == 1   # Таю stays, Swift is remembered as skipped (never fetched again)


def test_discover_takes_russian_titled_allowed_license_tracks_only(tmp_path, monkeypatch):
    cfg = {"licenses_allowed": ["cc0", "pdm", "by"], "sources": {"order": ["local", "openverse"]}}
    monkeypatch.setattr(fetch_songs.download, "download", lambda c, d, cfg=None, http=None: mkfile(tmp_path))
    monkeypatch.setattr(fetch_songs.download, "check_audio", lambda p, **kw: (p, []))
    pool = [cand(title="Лесная песня", artist="aniarky", sec=281), cand(title="Forest song", artist="aniarky"),      # not Russian
            cand(title="Песня про ТВ", artist="Vint", lic="https://creativecommons.org/licenses/by-sa/4.0/"),         # SA refused
            cand(title="Короткая", artist="Кто-то", sec=40), cand(title="Известная", artist="Y", sec=200)]            # too short / one-letter artist ok
    got = fetch_songs.discover(cfg, tmp_path / "o", set(), 5, find=lambda q: pool, sleep=lambda s: None, day=0)
    assert [w["title"] for w, _, _ in got] == ["Лесная песня", "Известная"]
    assert fetch_songs.discover(cfg, tmp_path / "o2", {fetch_songs.key("aniarky", "Лесная песня")}, 1, find=lambda q: pool[:1], sleep=lambda s: None) == []   # already known


def test_fits_rejects_instrumental_remix_and_cover_even_for_owners_artist():
    assert not fetch_songs.fits("ВОЛАНД", "ПЕСНЯ БЕЗ СЛОВ", set())
    assert not fetch_songs.fits("Guf", "Дно (Remix)", {"guf"})
    assert not fetch_songs.fits("Кто-то", "Таю (кавер)", set())
    assert fetch_songs.fits("Кто-то", "Песня", set())


class FakeResp:
    content = b"x" * 100

    def raise_for_status(self):
        pass


class FakeHttp:
    def get(self, url, timeout=0):
        return FakeResp()


def prev(title="Таю", artist="TASSO", url="https://cdn.example/p.mp3"):
    return Candidate("apple-preview", title, artist, url, "official-preview", "", "https://music.example/t", sec=30)


def test_preview_is_saved_with_analysis_only_sidecar(tmp_path, monkeypatch):
    monkeypatch.setattr(fetch_songs.download, "check_audio", lambda p, **kw: (p, []))
    name, why = fetch_songs.fetch_preview({"artist": "Tasso", "title": "Таю", "sec": 0}, tmp_path / "o", [prev()], FakeHttp())
    assert name == "Tasso - Таю.mp3" and (tmp_path / "o" / name).exists()
    side = json.loads((tmp_path / "o" / (name + ".license.json")).read_text(encoding="utf-8"))
    assert side["analysis_only"] is True and side["license"] == "official-preview"
    assert fetch_songs.fetch_preview({"artist": "Tasso", "title": "Таю", "sec": 0}, tmp_path / "o", [prev(url="http://insecure/p.mp3")], FakeHttp())[0] is None  # https only


def test_preview_candidates_drop_live_versions_and_other_songs():
    def get(url, params=None):
        if "itunes" in url:
            return {"results": [{"trackName": "Таю", "artistName": "TASSO", "previewUrl": "https://a/1.m4a"},
                                {"trackName": "Таю (Live Session)", "artistName": "TASSO", "previewUrl": "https://a/2.m4a"},
                                {"trackName": "Тихо", "artistName": "TASSO", "previewUrl": "https://a/3.m4a"}]}
        return {"data": [{"title": "Таю", "artist": {"name": "Tasso"}, "preview": "https://d/1.mp3", "link": "l"}]}
    got = fetch_songs.preview_candidates({"artist": "Tasso", "title": "Таю"}, get)
    assert [c.url for c in got] == ["https://a/1.m4a", "https://d/1.mp3"]


def test_run_with_previews_takes_list_songs_even_if_skipped_before_and_ignores_chart_songs(tmp_path, monkeypatch):
    monkeypatch.setattr(fetch_songs.download, "check_audio", lambda p, **kw: (p, []))
    cfg = {"licenses_allowed": ["by"], "sources": {"order": ["openverse"]}}
    a = run_args(tmp_path, "Tasso | Таю | | |\n")
    a.previews = True
    st = {"done": {}, "skipped": {fetch_songs.key("Tasso", "Таю"): {"status": "skipped", "date": fetch_songs.time.strftime("%Y-%m-%d", fetch_songs.time.gmtime()),
                                                                     "song": "Tasso - Таю", "file": "", "detail": "no licensed match"}}}
    fetch_songs.save_memory(tmp_path / "memory.md", st)
    seen = []
    monkeypatch.setattr(fetch_songs, "fetch_preview", lambda w, out, cands=None, http=None: (seen.append(w["title"]) or ("Tasso - Таю.mp3", "превью")))
    chart = lambda c: [{"title": "Nobody - Нету"}]
    got = fetch_songs.run(a, cfg, {"openverse": lambda *x: []}, chart, sleep=lambda s: None, preview_find=lambda w: [prev()])
    assert got == ["Tasso - Таю.mp3"] and seen == ["Таю"]   # the chart song got no preview, the list song did despite the 14-day window


def test_off_list_finds_audio_that_is_not_in_queue(tmp_path):
    (tmp_path / "Tasso - Таю.mp3").write_bytes(b"x")
    (tmp_path / "Tasso - Таю.mp3.license.json").write_text("{}")
    (tmp_path / "Random - Чужая.mp3").write_bytes(b"x")
    assert fetch_songs.off_list(tmp_path, "Tasso | Таю | | |\n") == ["Random - Чужая.mp3"]
    assert fetch_songs.off_list(tmp_path / "none", "Tasso | Таю | | |\n") == []
