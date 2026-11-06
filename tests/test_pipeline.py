import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from pipeline import analyze, download, qa, script_gen, sources, tiktok_trends
from pipeline.common import NeedsAuth, Refused, license_key, license_ok, load_config

CFG = load_config()
ALLOWED = CFG["licenses_allowed"]


# ---- license policy
@pytest.mark.parametrize("s,key", [
    ("by", "by"), ("CC BY 4.0", "by"), ("https://creativecommons.org/licenses/by/4.0/", "by"),
    ("cc0", "cc0"), ("https://creativecommons.org/publicdomain/zero/1.0/", "cc0"), ("pdm", "pdm"),
    ("by-nc", "by-nc"), ("CC BY-NC-SA 4.0", "by-nc-sa"), ("by-sa", "by-sa"),
    ("Creative Commons Attribution license (reuse allowed)", "by"),
    ("Standard YouTube License", ""), ("", ""), (None, ""),
])
def test_license_key(s, key):
    assert license_key(s) == key


def test_license_policy_blocks_nc_nd_sa_unknown():
    for bad in ("by-nc", "by-nd", "by-sa", "Standard YouTube License", "", "all rights reserved"):
        assert not license_ok(bad, ALLOWED)
    for good in ("by", "cc0", "pdm"):
        assert license_ok(good, ALLOWED)


# ---- search fallback chain
def C(src, lic):
    return sources.Candidate(src, "t", "a", "https://x/y.mp3", lic)


def test_search_falls_back_and_reports_statuses():
    def boom(q, n, cfg, env): raise RuntimeError("secret?client_id=KEY")
    def auth(q, n, cfg, env): raise NeedsAuth("need key")
    def good(q, n, cfg, env): return [C("openverse", "by"), C("openverse", "by-nc"), C("openverse", "")]
    cfg = dict(CFG, sources=dict(CFG["sources"], order=["local", "jamendo", "openverse", "ghost"]))
    found, st = sources.search("x", cfg, {}, n=5, searchers={"local": boom, "jamendo": auth, "openverse": good})
    assert [c.license for c in found] == ["by"]  # NC and unknown filtered out
    states = {s["source"]: s["state"] for s in st}
    assert states == {"local": "unavailable", "jamendo": "needs_auth", "openverse": "ok", "ghost": "unavailable"}
    assert "KEY" not in json.dumps(st)  # no secrets/URLs leak into statuses


def test_jamendo_needs_key():
    with pytest.raises(NeedsAuth):
        sources._jamendo("q", 3, CFG, {})


# ---- download policy
class FakeResp:
    def __init__(self, data): self.data = data
    def __enter__(self): return self
    def __exit__(self, *a): pass
    def raise_for_status(self): pass
    def iter_content(self, n): yield self.data


class FakeHttp:
    def get(self, url, **kw): return FakeResp(b"ID3fake")


def test_download_refuses_disallowed_license_and_http(tmp_path):
    with pytest.raises(Refused):
        download.download(C("openverse", "by-nc"), tmp_path, CFG, FakeHttp())
    c = C("openverse", "by")
    c.url = "http://insecure/y.mp3"
    with pytest.raises(Refused):
        download.download(c, tmp_path, CFG, FakeHttp())


def test_download_ok_writes_sidecar_and_chain_skips_bad(tmp_path):
    p, st = download.download_first([C("openverse", "by-nc"), C("openverse", "by")], tmp_path, CFG, FakeHttp())
    assert p and p.read_bytes() == b"ID3fake"
    assert json.loads(Path(str(p) + ".license.json").read_text())["license"] == "by"
    assert [s["state"] for s in st] == ["refused", "ok"]


class FakeYDL:
    info = {}
    def __init__(self, opts): pass
    def __enter__(self): return self
    def __exit__(self, *a): pass
    def extract_info(self, url, download=False): return dict(self.info)
    def prepare_filename(self, info): return "x.webm"


def test_ytdlp_domain_and_license_gate(tmp_path):
    with pytest.raises(Refused, match="domain"):
        download.ytdlp_download("https://open.spotify.com/track/1", tmp_path, CFG, FakeYDL)
    FakeYDL.info = {"license": "Standard YouTube License", "title": "t"}
    with pytest.raises(Refused, match="license"):
        download.ytdlp_download("https://www.youtube.com/watch?v=1", tmp_path, CFG, FakeYDL)
    FakeYDL.info = {}
    with pytest.raises(Refused, match="license"):
        download.ytdlp_download("https://youtu.be/1", tmp_path, CFG, FakeYDL)


def test_local_video_extract_needs_rights_flag(tmp_path):
    with pytest.raises(Refused):
        download.extract_local_audio(tmp_path / "v.mp4", tmp_path)


# ---- tiktok trends
def test_trends_without_credentials_reports_needs_auth_then_local(tmp_path, monkeypatch):
    f = tmp_path / "t.json"
    f.write_text(json.dumps({"hashtags": ["#рэп"], "songs": ["a - b"]}), encoding="utf-8")
    cfg = dict(CFG, trends=dict(CFG["trends"], local_file=str(f)))
    monkeypatch.setattr(tiktok_trends, "ROOT", Path("/"))
    r = tiktok_trends.fetch_trends(cfg, env={})
    assert [(s["source"], s["state"]) for s in r["statuses"]] == [("research", "needs_auth"), ("local", "ok")]
    assert r["hashtags"] == ["#рэп"]


def test_trends_nothing_available():
    cfg = dict(CFG, trends=dict(CFG["trends"], local_file="data/definitely_missing.json"))
    r = tiktok_trends.fetch_trends(cfg, env={})
    assert [s["state"] for s in r["statuses"]] == ["needs_auth", "empty"] and r["hashtags"] == []


def test_summarize_videos_weights_by_views():
    v = [{"hashtag_names": ["Rap", "kz"], "view_count": 100, "music_id": 1, "video_duration": 30},
         {"hashtag_names": ["rap"], "view_count": 50, "music_id": 1, "video_duration": 40}]
    s = tiktok_trends.summarize_videos(v)
    assert s["hashtags"][0] == {"tag": "rap", "videos": 2, "views": 150}
    assert s["music_ids"][0] == {"music_id": "1", "videos": 2} and s["duration_sec"]["median"] == 40


def test_own_stats_needs_token():
    assert tiktok_trends.own_stats(env={})["status"]["state"] == "needs_auth"


# ---- chorus + fragment
def mk_lines():
    texts = ["walking home tonight", "streetlights fade away", "nobody calls my name", "hook line alpha", "hook line beta",
             "money cannot buy time", "silence in the room", "hook line alpha", "hook line beta", "morning comes again",
             "hook line alpha", "hook line beta", "final words here"]
    t, lines = 0.0, []
    for x in texts:
        lines.append({"start": t, "end": t + 4.0, "text": x, "words": [{"w": w, "s": t, "e": t + 1, "p": .9} for w in x.split()]})
        t += 5.0
    return lines


def test_find_chorus_picks_repeated_block():
    ch = analyze.find_chorus(mk_lines())
    assert ch[0]["text"] == "hook line alpha" and ch[0]["repeats"] == 3 and ch[0]["last"] - ch[0]["first"] == 1


def test_pick_fragment_uses_popular_line_and_length():
    lines = mk_lines()
    f = analyze.pick_fragment(lines, "hook line beta", 30, 60)
    assert "popular_line matched" in f["reason"]
    assert 30 <= f["length"] <= 60
    assert lines[f["first"]]["start"] <= lines[4]["start"] <= lines[f["last"]]["end"]


def test_pick_fragment_falls_back_to_chorus_when_line_not_found():
    f = analyze.pick_fragment(mk_lines(), "zzzz qqqq nothing", 30, 60)
    assert "not found" in f["reason"] and "chorus" in f["reason"]


def test_pick_fragment_never_exceeds_max():
    f = analyze.pick_fragment(mk_lines(), "hook line alpha", 30, 40)
    assert f["length"] <= 40


def test_pinned_start_begins_exactly_at_that_line():
    lines = mk_lines()
    f = analyze.pick_fragment(lines, "=morning comes", 20, 60)  # the chorus snap would start earlier
    assert f["pinned"] and f["first"] == 9 and "pinned" in f["reason"]
    f = analyze.pick_fragment(lines, "=hook line beta", 20, 60)
    assert f["first"] == 4  # not snapped back to the chorus start (line 3)


def test_pinned_start_not_found_falls_back_to_auto():
    f = analyze.pick_fragment(mk_lines(), "=zzzz qqqq nothing", 30, 60)
    assert not f["pinned"] and "chorus" in f["reason"]


# ---- scenario generation
def test_build_scenes_no_overlap_and_relative_times():
    lines = mk_lines()
    frag = analyze.pick_fragment(lines, "hook line alpha", 30, 60)
    plan = script_gen.build_scenes({"lines": lines, "fragment": frag, "beats": [frag["start"] + 1, 9999]},
                                   {"artist": "A", "title": "T"}, CFG)
    sc = plan["scenes"]
    assert sc[0]["start"] >= 0 and sc[-1]["role"] == "outro" and sc[-1]["end"] == plan["duration"]
    assert all(x["end"] <= y["start"] + 1e-6 for x, y in zip(sc, sc[1:]))
    assert plan["beats"] == [1.0] and plan["audio_start"] == frag["start"]


def test_split_words_limits_to_8():
    parts = script_gen.split_words(list(range(17)))
    assert all(len(p) <= 8 for p in parts) and sum(map(len, parts)) == 17


# ---- spec validation
def good_spec():
    return {"id": "x", "mode": "with_audio", "song": {"artist": "a", "title": "t"}, "metaphor": "love", "palette": "cold",
            "caption": "hi", "hashtags": ["#a", "#b", "#c"], "ai_label": True}


def test_validate_spec():
    assert qa.validate_spec(good_spec(), CFG) == []
    s = good_spec(); s["ai_label"] = False; s["palette"] = "neon"; s["hashtags"] = ["a"]
    assert len(qa.validate_spec(s, CFG)) == 3
    c = good_spec(); c["mode"] = "commentary"; c["scenes"] = [{"role": "hook", "text": "t", "start": 0, "dur": 20},
                                                           {"role": "outro", "text": "t", "start": 21, "dur": 15}]
    assert "scenes not contiguous" in qa.validate_spec(c, CFG)
