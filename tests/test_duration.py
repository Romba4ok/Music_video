"""The video must always land in min_len..max_total (20-42 s): the fragment is never shorter than min_len, a short scenario is lengthened with REAL
audio around the lyrics (never stretched audio, never bare frames), and a scenario that still cannot fit is refused BEFORE the render.
Regression: Серёга — Чёрный Бумер rendered a 15.08 s video (12.58 s fragment + 2.5 s end card) and failed QA after a full render."""
import json

import pytest

from pipeline import analyze, build, qa, render, script_gen
from pipeline.common import load_config

CFG = load_config()
MAX_TOTAL = qa.max_total(CFG)
SONG = {"artist": "Серёга", "title": "Чёрный Бумер"}


def _line(t0, t1, text="строка"):
    n = max(2, int((t1 - t0) / 0.5))
    step = (t1 - t0) / n
    ws = [{"w": f"{text}{k}", "s": round(t0 + k * step, 3), "e": round(t0 + (k + 1) * step - 0.05, 3), "p": 0.9} for k in range(n)]
    return {"start": ws[0]["s"], "end": ws[-1]["e"], "text": " ".join(w["w"] for w in ws), "words": ws}


def _song(starts, dur=3.0):
    return [_line(t, t + dur, f"л{i}_") for i, t in enumerate(starts)]


def _frag(lines, a, b, **kw):
    return dict({"first": a, "last": b, "start": lines[a]["start"], "end": lines[b]["end"], "length": round(lines[b]["end"] - lines[a]["start"], 2),
                 "reason": "t", "pinned": False}, **kw)


def _analysis(lines, a, b, audio_dur=200.0):
    return {"lines": lines, "fragment": _frag(lines, a, b), "beats": [round(lines[a]["start"] + 0.5 * k, 3) for k in range(40)],
            "summary": {"audio_duration": audio_dur}}


# ---- analysis: the fragment is never shorter than min_len while the song has more lyrics
def test_a_short_fragment_grows_over_real_neighbour_lines_forward_first():
    lines = _song([10 + 4 * i for i in range(10)])  # ten 3 s lines, 1 s apart
    f = analyze.ensure_min_len(lines, _frag(lines, 3, 5), CFG)  # 11 s
    assert f["length"] >= CFG["min_len"] and f["first"] == 3 and f["last"] > 5 and not f.get("short") and "extended" in f["reason"]
    assert f["start"] == lines[3]["start"] and f["end"] == lines[f["last"]]["end"]  # real lines, exact times


def test_it_goes_backward_when_the_song_ends_and_says_when_a_pin_moved():
    lines = _song([10 + 4 * i for i in range(8)])
    f = analyze.ensure_min_len(lines, _frag(lines, 5, 7, pinned=True), CFG)  # the pinned start is line 5, the song ends at line 7
    assert f["length"] >= CFG["min_len"] and f["first"] < 5 and f["last"] == 7 and f["pinned"] is False and "pinned start moved" in f["reason"]
    kept = analyze.ensure_min_len(lines, _frag(lines, 2, 3, pinned=True), CFG)  # room ahead: the pin stays
    assert kept["first"] == 2 and kept["pinned"] is True and kept["length"] >= CFG["min_len"]


def test_a_song_with_too_little_lyrics_is_marked_short_not_stretched():
    lines = _song([10, 14, 18])  # 11 s of lyrics in total
    f = analyze.ensure_min_len(lines, _frag(lines, 0, 2), CFG)
    assert f["short"] is True and f["length"] < CFG["min_len"] and (f["first"], f["last"]) == (0, 2) and "no more lyrics" in f["reason"]


def test_a_long_enough_fragment_is_untouched():
    lines = _song([10 + 4 * i for i in range(10)])
    frag = _frag(lines, 1, 6)
    assert analyze.ensure_min_len(lines, frag, CFG) is frag


def test_a_window_shrunk_by_the_second_recognition_pass_is_grown_again():
    lines = _song([10 + 4 * i for i in range(10)])
    shrunk = dict(_frag(lines, 3, 5), pinned=False)  # the big model merged the edge lines: 11 s left
    assert analyze.ensure_min_len(lines, shrunk, CFG)["length"] >= CFG["min_len"]


def test_pick_reliable_returns_a_fragment_that_meets_min_len():
    lines = _song([10 + 4 * i for i in range(10)])
    f = analyze.pick_reliable(lines, "", CFG)
    assert CFG["min_len"] <= f["length"] <= CFG["max_len"] + CFG["close_overrun"]


# ---- scenario: lengthen with real audio before and after the lyrics
def test_the_15_08_second_scenario_is_lengthened_to_min_len_with_real_audio():
    lines = [_line(30.0, 42.58, "бумер")]  # 12.58 s of lyrics + 2.5 s end card = 15.08 s: the failing case
    plan = script_gen.build_scenes(_analysis(lines, 0, 0), SONG, CFG)
    assert CFG["min_len"] + script_gen.MIN_MARGIN - 0.02 <= plan["duration"] <= MAX_TOTAL and not plan["short"]
    assert qa.plan_duration_errors(plan, CFG) == []
    pre, hold = plan["extended"]["preroll"], plan["extended"]["hold"]
    base = round(lines[0]["end"] - lines[0]["start"] + CFG["tail_sec"], 2)  # about 15.03 s before the fix
    assert pre > 0 and hold > 0 and abs(pre + hold - (plan["duration"] - base)) < 0.03  # exactly what was missing, no more
    assert plan["duration"] - (CFG["min_len"] + script_gen.MIN_MARGIN) < 0.03  # and not a second more than needed
    assert plan["audio_start"] == round(30.0 - pre, 3) and plan["audio_len"] == plan["duration"]  # a real slice of the song, not stretched
    assert plan["audio_start"] + plan["audio_len"] <= 200.0
    cards = [s for s in plan["scenes"] if s["role"] == "lyric"]
    outro = plan["scenes"][-1]
    assert cards[0]["start"] == 0.0  # the first card is on screen from the first frame: no bare stage during the lead-in
    assert all(a["end"] <= b["start"] + 1e-6 for a, b in zip(plan["scenes"], plan["scenes"][1:]))
    assert outro["end"] == plan["duration"] and outro["start"] >= cards[-1]["end"]


def test_words_and_beats_keep_their_place_against_the_music():
    lines = [_line(30.0, 42.58, "бумер")]
    an = _analysis(lines, 0, 0)
    plan = script_gen.build_scenes(an, SONG, CFG)
    w = plan["scenes"][0]["words"][0]
    assert plan["audio_start"] + w["s"] == pytest.approx(lines[0]["words"][0]["s"], abs=0.01)  # word time in the video + audio start = its time in the song
    song_beats = an["beats"]
    assert plan["beats"] and all(any(abs(plan["audio_start"] + b - sb) < 0.01 for sb in song_beats) for b in plan["beats"])


def test_extension_is_limited_by_the_audio_the_song_really_has():
    lines = [_line(1.0, 13.58, "бумер")]  # the song starts at 1 s and ends right after: almost no audio to add
    plan = script_gen.build_scenes(_analysis(lines, 0, 0, audio_dur=16.0), SONG, CFG)
    assert plan["short"] is True and plan["audio_start"] >= 0
    errs = qa.plan_duration_errors(plan, CFG)
    assert errs and "shorter than min_len" in errs[0]


def test_a_scenario_that_already_fits_is_unchanged():
    lines = _song([10 + 4 * i for i in range(8)])
    plan = script_gen.build_scenes(_analysis(lines, 0, 5), SONG, CFG)
    assert plan["extended"] == {"preroll": 0.0, "hold": 0.0} and plan["intro"] == 0 and not plan["short"]
    assert plan["duration"] == round(lines[5]["end"] - lines[0]["start"] + CFG["tail_sec"], 2)


def test_every_length_from_a_few_seconds_to_the_limit_ends_inside_the_range_or_is_flagged():
    for length in (5.0, 8.0, 12.58, 15.0, 17.5, 19.9, 20.0, 25.0, 38.0):
        plan = script_gen.build_scenes(_analysis([_line(40.0, 40.0 + length, "x")], 0, 0), SONG, CFG)
        d = plan["duration"]
        assert plan["short"] == (d < CFG["min_len"]), (length, d)  # never silently short: either it fits or it is flagged
        assert d <= MAX_TOTAL + 1e-6, (length, d)
        assert (not plan["short"]) == (qa.plan_duration_errors(plan, CFG) == [])


# ---- the check before the render, and the MP4 tolerance
def test_plan_duration_errors_flags_too_long_and_too_short():
    assert qa.plan_duration_errors({"duration": 25.0, "short": False}, CFG) == []
    assert "longer than" in qa.plan_duration_errors({"duration": MAX_TOTAL + 1, "short": False}, CFG)[0]
    assert "shorter than" in qa.plan_duration_errors({"duration": 15.08, "short": True, "extended": {"preroll": 0.5, "hold": 1.0}}, CFG)[0]


def test_build_refuses_a_too_short_scenario_before_rendering(tmp_path, monkeypatch):
    an = _analysis([_line(1.0, 13.58, "бумер")], 0, 0, audio_dur=16.0)
    (tmp_path / "analysis-1.json").write_text(json.dumps(an, ensure_ascii=False), encoding="utf-8")
    spec = {"id": "x", "mode": "with_audio", "song": SONG, "metaphor": "love", "palette": "dusk", "caption": "c", "hashtags": ["#a", "#b", "#c"],
            "ai_label": True, "audio": "audio/none.mp3"}
    (tmp_path / "spec-1.json").write_text(json.dumps(spec, ensure_ascii=False), encoding="utf-8")

    def no_render(*a, **k):
        raise AssertionError("render must not start")

    monkeypatch.setattr(render, "render", no_render)
    sid, out, video = build.build_one(tmp_path, 1, CFG)
    assert video is None and out[0][:2] == ("FAIL", "scenario_duration") and "min_len" in out[0][2]


def test_the_mp4_check_forgives_a_frame_of_rounding_but_not_a_real_shortfall(monkeypatch):
    def run(dur, exp):
        info = {"streams": [{"codec_type": "video", "width": 1080, "height": 1920, "r_frame_rate": "30/1", "codec_name": "h264"}], "format": {"duration": str(dur)}}
        monkeypatch.setattr(qa, "probe", lambda v: info)
        monkeypatch.setattr(qa, "black_frames", lambda v: [])
        monkeypatch.setattr(qa, "validate_spec", lambda s, c: [])
        plan = {"duration": exp, "scenes": []}
        return next(x for x in qa.run_checks({"mode": "commentary"}, "v.mp4", plan, CFG) if x[1] == "duration")[0]

    assert run(19.97, 20.0) == "PASS"  # one frame under 20 s: rounding
    assert run(19.9, 19.9) == "FAIL"  # a real shortfall stays a failure
    assert run(15.07, 15.08) == "FAIL"  # the original case is still refused


def test_other_modes_and_the_sync_hint_follow_the_lengthened_plan():
    lines = _song([10 + 4 * i for i in range(8)])
    plan = script_gen.build_scenes(_analysis(lines, 0, 5), SONG, CFG)
    assert plan["scenes"][-1]["role"] == "outro" and plan["audio_start"] == lines[0]["start"]
    short = script_gen.build_scenes(_analysis([_line(30.0, 42.58)], 0, 0), SONG, CFG)
    sync = build.sync_info({"song": SONG}, short)  # tiktok mode: the official sound is cut in earlier by exactly the added lead-in
    assert sync["sound_start_sec"] == short["audio_start"] < 30.0


def test_cards_that_start_together_stay_readable_and_never_overlap():
    """Regression (Guf - Uragan, QA: no_card_overlap [0] + cards_readable too short [0]): card 1 started 0.1 s after card 0, the old overlap fix cut
    card 0 to 0.2 s past its own start, longer than the gap, so it overlapped card 1 and was too short to read."""
    first = _line(30.0, 33.0, "а")
    second = _line(30.1, 33.0, "б")  # an overlapping voice: starts almost together with the first line
    third = _line(34.0, 37.0, "в")
    lines = [first, second, third]
    plan = script_gen.build_scenes(_analysis(lines, 0, 2), SONG, CFG)
    cards = [s for s in plan["scenes"] if s["role"] == "lyric"]
    assert all(c["end"] - c["start"] >= 0.5 - 1e-6 for c in cards)
    assert all(x["end"] <= y["start"] + 1e-6 for x, y in zip(plan["scenes"], plan["scenes"][1:]))
