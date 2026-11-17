"""A skipped song must not be blocked forever: it is searched again when the sources / permissions / algorithm change, when a source did not answer,
with --force-retry, or after 14 days. The memory keeps one row per song (history counter), and the run report says what really happened."""
import json
import time
from argparse import Namespace

from pipeline import fetch_songs as fs

TODAY = time.strftime("%Y-%m-%d", time.gmtime())
CFG = {"licenses_allowed": ["cc0", "pdm", "by"], "sources": {"order": ["openverse", "jamendo"]}}
QUEUE = "Tasso | Таю | | |\nXcho | Ветер | | |\n"


def args(tmp_path, **kw):
    q = tmp_path / "queue.md"
    q.write_text(QUEUE, encoding="utf-8")
    base = dict(out=str(tmp_path / "out"), have_file=None, state=str(tmp_path / "m.md"), queue=str(q), max=5, tries=40, record_used=None, prune=None,
                discover=False, previews=False, check_list=None, force_retry=False)
    return Namespace(**{**base, **kw})


class Spy:
    """openverse finds nothing; jamendo answers per `jamendo`: needs_auth | unavailable"""

    def __init__(self, jamendo="needs_auth"):
        self.calls, self.jamendo = [], jamendo

    def openverse(self, q, n, cfg, env):
        self.calls.append(q)
        return []

    def jam(self, q, n, cfg, env):
        if self.jamendo == "needs_auth":
            raise fs.sources.NeedsAuth("no key")
        raise ConnectionError("down")

    @property
    def searchers(self):
        return {"openverse": self.openverse, "jamendo": self.jam}


def go(a, spy, cfg=CFG, capsys=None):
    fs.run(a, cfg, spy.searchers, lambda c: [], sleep=lambda s: None)
    return json.loads(capsys.readouterr().out.strip().splitlines()[-1])


def test_signature_changes_with_sources_hosts_credentials_and_algorithm(monkeypatch):
    base = fs.search_signature(CFG, {})
    assert base == fs.search_signature(CFG, {})
    assert base != fs.search_signature({**CFG, "sources": {"order": ["openverse", "jamendo", "archive"]}}, {})
    assert base != fs.search_signature({**CFG, "licenses_allowed": ["cc0", "pdm", "by", "by-sa"]}, {})
    assert base != fs.search_signature({**CFG, "direct_urls": {"allowed_hosts": ["example.org"]}}, {})
    assert base != fs.search_signature(CFG, {"JAMENDO_CLIENT_ID": "k"})   # a new key = a source that could not be searched before
    monkeypatch.setattr(fs, "ALGO_VERSION", "other")
    assert base != fs.search_signature(CFG, {})


def test_same_signature_inside_the_window_is_not_searched_again(tmp_path, capsys):
    spy = Spy()
    r1 = go(args(tmp_path), spy, capsys=capsys)
    assert r1["checked"] == 2 and r1["downloaded"] == [] and r1["blocked_recent"] == 0
    r2 = go(args(tmp_path), spy, capsys=capsys)
    assert r2["checked"] == 0 and r2["blocked_recent"] == 2 and len(spy.calls) == 2   # nothing new could be found


def test_changed_sources_recheck_at_once_and_keep_one_row_per_song_with_history(tmp_path, capsys):
    spy = Spy()
    go(args(tmp_path), spy, capsys=capsys)
    cfg2 = {**CFG, "sources": {"order": ["openverse", "jamendo", "archive"]}}   # the list of sources changed
    spy.searchers_extra = None
    r = go(args(tmp_path), Spy(), cfg2, capsys)
    assert r["checked"] == 2 and r["rechecked_skipped"] == 2
    mem = fs.load_memory(tmp_path / "m.md")
    assert len(mem["skipped"]) == 2                                   # same two rows, no duplicates
    sig, n, first, why = fs.read_tag(next(iter(mem["skipped"].values()))["detail"])
    assert n == 2 and first == TODAY and sig == fs.search_signature(cfg2) and "no licensed match" in why


def test_a_source_that_did_not_answer_is_not_a_real_no(tmp_path, capsys):
    spy = Spy(jamendo="unavailable")
    go(args(tmp_path), spy, capsys=capsys)
    r = go(args(tmp_path), spy, capsys=capsys)
    assert r["checked"] == 2 and r["blocked_recent"] == 0              # searched again on the very next run, not in 14 days


def test_force_retry_checks_every_skipped_song_and_an_untagged_old_row_is_checked_once(tmp_path, capsys):
    spy = Spy()
    go(args(tmp_path), spy, capsys=capsys)
    r = go(args(tmp_path, force_retry=True), spy, capsys=capsys)
    assert r["checked"] == 2 and r["force_retry"] is True
    st = fs.load_memory(tmp_path / "m.md")
    for row in st["skipped"].values():
        row["detail"] = fs.read_tag(row["detail"])[3]                 # an old row from before the signature existed
    fs.save_memory(tmp_path / "m.md", st)
    assert go(args(tmp_path), spy, capsys=capsys)["checked"] == 2
    assert go(args(tmp_path), spy, capsys=capsys)["checked"] == 0      # and now it carries a signature again


def test_after_the_window_a_song_is_searched_again(tmp_path, capsys):
    spy = Spy()
    go(args(tmp_path), spy, capsys=capsys)
    st = fs.load_memory(tmp_path / "m.md")
    for row in st["skipped"].values():
        row["date"] = "2026-01-01"
    fs.save_memory(tmp_path / "m.md", st)
    assert go(args(tmp_path), spy, capsys=capsys)["checked"] == 2


def test_report_counts_and_reasons(tmp_path, capsys):
    r = go(args(tmp_path, max=1, tries=1), Spy(), capsys=capsys)
    assert r["candidates"] == 2 and r["eligible"] == 2 and r["checked"] == 1 and r["left_unchecked"] == 1 and r["downloaded"] == []
    assert r["skip_reasons"] == {"no licensed match": 1}
    assert r["source_states"]["openverse:empty"] == 1 and r["source_states"]["jamendo:needs_auth"] == 1   # why nothing was found is visible
    assert r["signature"] == fs.search_signature(CFG)


def test_a_found_song_moves_from_skipped_to_done_without_a_duplicate_row(tmp_path, capsys, monkeypatch):
    spy = Spy()
    go(args(tmp_path), spy, capsys=capsys)
    monkeypatch.setattr(fs, "fetch_one", lambda w, cfg, out, **kwargs: ("Tasso - Таю.mp3", "openverse: found") if w["title"] == "Таю" else (None, "no licensed match"))
    r = go(args(tmp_path, force_retry=True), spy, capsys=capsys)
    mem = fs.load_memory(tmp_path / "m.md")
    assert r["downloaded"] == ["Tasso - Таю.mp3"] and len(mem["done"]) == 1 and len(mem["skipped"]) == 1
