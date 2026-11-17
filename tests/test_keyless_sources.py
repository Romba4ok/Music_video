"""Keyless search: ccMixter adapter, per-site isolation of failures, the HTTP log in the run report, no JAMENDO/SOUNDCLOUD keys needed."""
import json
from argparse import Namespace

import requests

from pipeline import common, fetch_songs as fs, sources

CFG = {"licenses_allowed": ["cc0", "pdm", "by"], "sources": {"order": ["openverse", "archive", "ccmixter", "jamendo", "soundcloud"]}}
CCM = [{"upload_name": "Таю", "user_name": "tasso", "user_real_name": "Tasso", "license_url": "https://creativecommons.org/licenses/by/4.0/",
        "file_page_url": "https://ccmixter.org/files/tasso/1",
        "files": [{"download_url": "https://ccmixter.org/content/t/a.zip", "file_format_info": {"default-ext": "zip"}},
                  {"download_url": "https://ccmixter.org/content/t/a.mp3", "file_format_info": {"default-ext": "mp3", "ps": "3:45"}}]},
       {"upload_name": "Таю NC", "user_name": "tasso", "license_url": "https://creativecommons.org/licenses/by-nc/4.0/",
        "files": [{"download_url": "https://ccmixter.org/content/t/b.mp3", "file_format_info": {"default-ext": "mp3", "ps": "3:00"}}]}]


def test_ccmixter_adapter_picks_the_mp3_reads_length_and_license_policy_drops_nc(monkeypatch):
    monkeypatch.setattr(sources, "get_json", lambda url, params=None, **k: CCM)
    got = sources._ccmixter("Tasso Таю", 5, CFG, {})
    assert [(c.url, c.sec) for c in got] == [("https://ccmixter.org/content/t/a.mp3", 225), ("https://ccmixter.org/content/t/b.mp3", 180)]
    ok, sts = sources.search("Tasso Таю", {**CFG, "sources": {"order": ["ccmixter"]}}, {}, searchers={"ccmixter": sources._ccmixter})
    assert [c.title for c in ok] == ["Таю"] and sts[0]["state"] == "ok"   # BY-NC is refused by the license filter


def test_one_dead_site_does_not_stop_the_others_and_no_keys_are_needed():
    def boom(q, n, cfg, env):
        raise requests.ConnectTimeout("archive down")
    s = {"openverse": lambda q, n, c, e: [], "archive": boom, "ccmixter": lambda q, n, c, e: [],
         "jamendo": sources._jamendo, "soundcloud": sources._soundcloud}
    cands, sts = sources.search("x y", CFG, {}, searchers=s)   # env without any key
    assert cands == [] and {x["source"]: x["state"] for x in sts} == {"openverse": "empty", "archive": "unavailable", "ccmixter": "empty",
                                                                      "jamendo": "needs_auth", "soundcloud": "needs_auth"}


class R:
    def __init__(self, code):
        self.status_code = code
        self.response = None

    def raise_for_status(self):
        if self.status_code >= 400:
            e = requests.HTTPError(str(self.status_code))
            e.response = self
            raise e

    def json(self):
        return {}


def test_http_log_records_hosts_statuses_and_errors_and_a_403_is_not_retried(monkeypatch):
    common.HTTP_LOG.clear()
    seq = iter([R(200)])
    monkeypatch.setattr(requests, "get", lambda *a, **k: next(seq))
    common.get_json("https://ccmixter.org/api/query")
    calls = []
    monkeypatch.setattr(requests, "get", lambda *a, **k: calls.append(1) or R(403))
    try:
        common.get_json("https://archive.org/advancedsearch.php")
    except requests.HTTPError:
        pass
    assert len(calls) == 1                                           # closed access is never retried or bypassed
    def timeout(*a, **k):
        raise requests.ConnectTimeout("t")
    monkeypatch.setattr(requests, "get", timeout)
    try:
        common.get_json("https://archive.org/x", retries=1)
    except requests.ConnectTimeout:
        pass
    assert common.http_summary() == {"ccmixter.org": {"requests": 1, "statuses": {"200": 1}},
                                     "archive.org": {"requests": 3, "statuses": {"403": 1, "ConnectTimeout": 2}}}


def test_run_report_has_the_http_summary(tmp_path, capsys):
    common.HTTP_LOG.clear()
    q = tmp_path / "queue.md"
    q.write_text("Tasso | Таю | | |\n", encoding="utf-8")
    a = Namespace(out=str(tmp_path / "out"), have_file=None, state=str(tmp_path / "m.md"), queue=str(q), max=5, tries=40, record_used=None, prune=None,
                  discover=False, previews=False, check_list=None, force_retry=False)

    def ccm(q, n, cfg, env):
        common.HTTP_LOG.append(("ccmixter.org", 200))
        return []
    fs.run(a, {**CFG, "sources": {"order": ["ccmixter"]}}, {"ccmixter": ccm}, lambda c: [], sleep=lambda s: None)
    rep = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert rep["http"] == {"ccmixter.org": {"requests": 1, "statuses": {"200": 1}}} and rep["checked"] == 1


def test_probe_asks_every_source_without_early_stop_and_stats_count_per_source():
    ok = lambda q, n, c, e: [sources.Candidate("x", "T", "A", "https://x/a.mp3", "https://creativecommons.org/licenses/by/4.0/", sec=120)] * 5
    nc = lambda q, n, c, e: [sources.Candidate("y", "T", "A", "https://y/a.mp3", "https://creativecommons.org/licenses/by-nc/4.0/", sec=90)]
    def key(q, n, c, e):
        raise sources.NeedsAuth("no key")
    cfg = {**CFG, "sources": {"order": ["local", "openverse", "jamendo", "soundcloud"]}}
    got = sources.probe("piano", cfg, {}, {"openverse": ok, "jamendo": nc, "soundcloud": key})
    assert [(r["source"], r["state"], r["candidates"], r["allowed"]) for r in got] == [("openverse", "ok", 5, 5), ("jamendo", "ok", 1, 0), ("soundcloud", "needs_auth", 0, 0)]
    assert "120 s" in got[0]["example"]
    sources.STATS.clear()
    sources.search("piano", {**cfg, "sources": {"order": ["jamendo"]}}, {}, searchers={"jamendo": nc})
    assert sources.STATS["jamendo"] == {"queries": 1, "candidates": 1, "allowed": 0, "matched": 0, "downloaded": 0}


def test_jamendo_api_failure_is_unavailable_not_an_empty_answer_and_the_key_stays_out_of_the_message(monkeypatch):
    monkeypatch.setattr(sources, "get_json", lambda url, params=None, **k: {"headers": {"status": "failed", "code": 5, "error_message": "invalid client_id k123"}, "results": []})
    cands, sts = sources.search("x", {**CFG, "sources": {"order": ["jamendo"]}}, {"JAMENDO_CLIENT_ID": "k123"}, searchers={"jamendo": sources._jamendo})
    assert cands == [] and sts[0]["state"] == "unavailable"
    monkeypatch.setattr(sources, "get_json", lambda url, params=None, **k: {"headers": {"status": "success"}, "results": [
        {"name": "T", "artist_name": "A", "audiodownload": "https://x/a.mp3", "audiodownload_allowed": True, "license_ccurl": "https://creativecommons.org/licenses/by/3.0/", "duration": 200},
        {"name": "N", "artist_name": "A", "audiodownload": "", "audiodownload_allowed": False}]})
    cands, sts = sources.search("x", {**CFG, "sources": {"order": ["jamendo"]}}, {"JAMENDO_CLIENT_ID": "k123"}, searchers={"jamendo": sources._jamendo})
    assert [(c.title, c.sec) for c in cands] == [("T", 200)] and sts[0]["state"] == "ok"
