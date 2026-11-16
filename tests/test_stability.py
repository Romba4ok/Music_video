"""Stability of the daily run: audio validation,
low-confidence lyrics, one bad song never stops the batch."""
import json
import shutil
import subprocess

import pytest

from pipeline import analyze, batch, download, render, script_gen
from pipeline.common import load_config

CFG = load_config()
HAVE_FFMPEG = bool(shutil.which("ffmpeg") and shutil.which("ffprobe"))
ffmpeg = pytest.mark.skipif(not HAVE_FFMPEG, reason="ffmpeg/ffprobe not installed")


# ---- low-confidence lyrics: move to a reliable window, never invent words
def _lines(low):
    texts = ["walking home tonight", "streetlights fade away", "nobody calls my name", "hook line alpha", "hook line beta", "money cannot buy time",
             "silence in the room", "hook line alpha", "hook line beta", "morning comes again", "hook line alpha", "hook line beta", "final words here",
             "one more verse", "second to last", "very end"]
    out, t = [], 0.0
    for i, x in enumerate(texts):
        p = .2 if i in low else .9
        out.append({"start": t, "end": t + 4.0, "text": x, "words": [{"w": w, "s": t, "e": t + 1, "p": p} for w in x.split()]})
        t += 5.0
    return out


CFG20 = dict(CFG, min_len=20, max_len=40)


def test_reliable_window_replaces_one_with_too_many_unsure_words():
    lines = _lines(low={3, 4, 5, 6, 7, 8})
    f = analyze.pick_reliable(lines, "", CFG20)
    assert f["low_ratio"] <= .15 and f["length"] >= 20 and "moved to line" in f["reason"]
    assert analyze.low_ratio(lines, f, .5) <= .15  # a longer window that finishes the thought may touch one unsure line, as long as the share stays under the limit
    assert all(lines[i]["words"][0]["p"] == .2 for i in (3, 4))  # the words themselves are untouched


def test_reliable_window_keeps_first_choice_when_it_is_fine():
    lines = _lines(low=set())
    f = analyze.pick_reliable(lines, "", CFG20)
    assert f["low_ratio"] == 0 and "moved" not in f["reason"]
    assert f["first"] == analyze.pick_fragment(lines, "", 20, 40)["first"]


def test_no_reliable_window_is_reported_not_hidden():
    lines = _lines(low=set(range(16)))
    f = analyze.pick_reliable(lines, "", CFG20)
    assert f["low_ratio"] == 1.0 and "no window within limits" in f["reason"]


def test_pinned_start_is_the_owners_choice_even_if_unsure():
    lines = _lines(low={9, 10, 11, 12})
    f = analyze.pick_reliable(lines, "=morning comes", CFG20)
    assert f["first"] == 9 and f["pinned"] and f["low_ratio"] > .15


# ---- audio validation (real ffmpeg)
def _tone(path, sec, codec):
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", f"sine=f=440:d={sec}", "-c:a", codec, str(path)], check=True)


@ffmpeg
def test_good_audio_passes(tmp_path):
    _tone(tmp_path / "ok.wav", 25, "pcm_s16le")
    p, notes = download.check_audio(tmp_path / "ok.wav", 20, fixdir=tmp_path / "fix")
    assert p == tmp_path / "ok.wav" and notes == []


@ffmpeg
def test_garbage_file_named_mp3_is_rejected(tmp_path):
    (tmp_path / "x.mp3").write_bytes(b"this is not audio at all" * 100)
    with pytest.raises(download.BadAudio):
        download.check_audio(tmp_path / "x.mp3", 20, fixdir=tmp_path / "fix")


@ffmpeg
def test_too_short_and_video_without_audio_are_rejected(tmp_path):
    _tone(tmp_path / "short.wav", 5, "pcm_s16le")
    with pytest.raises(download.BadAudio, match="shorter"):
        download.check_audio(tmp_path / "short.wav", 20, fixdir=tmp_path / "fix")
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "color=c=black:s=64x64:d=30", "-an", str(tmp_path / "v.mp4")], check=True)
    with pytest.raises(download.BadAudio, match="no audio"):
        download.check_audio(tmp_path / "v.mp4", 20, fixdir=tmp_path / "fix")


@ffmpeg
def test_mp3_with_a_few_bad_frames_is_accepted_with_a_note(tmp_path):
    _tone(tmp_path / "s.mp3", 30, "libmp3lame")
    b = bytearray((tmp_path / "s.mp3").read_bytes())
    for i in range(len(b) // 3, len(b) // 3 + 6000):  # ~0.7 s of the 30 s lost
        b[i] = (i * 37) % 256
    (tmp_path / "s.mp3").write_bytes(bytes(b))
    p, notes = download.check_audio(tmp_path / "s.mp3", 20, fixdir=tmp_path / "fix")
    assert p == tmp_path / "s.mp3" and notes and "warning" in notes[0]


@ffmpeg
def test_badly_damaged_mp3_is_repaired_or_rejected_never_passed_on(tmp_path):
    _tone(tmp_path / "d.mp3", 30, "libmp3lame")
    b = bytearray((tmp_path / "d.mp3").read_bytes())
    for i in range(len(b) // 5, len(b)):  # 80% destroyed
        b[i] = (i * 37) % 256
    (tmp_path / "d.mp3").write_bytes(bytes(b))
    try:
        p, notes = download.check_audio(tmp_path / "d.mp3", 20, fixdir=tmp_path / "fix")
    except download.BadAudio:
        return
    assert p != tmp_path / "d.mp3" and any("re-encoded" in n for n in notes)  # only a clean copy may continue


# ---- batch: a bad song never stops the others
def _batch_env(tmp_path, titles):
    acc = tmp_path / "accounts" / "main"
    acc.mkdir(parents=True)
    (acc / "queue.md").write_text("".join(f"A | {t} | | |\n" for t in titles), encoding="utf-8")
    aud = tmp_path / "a.mp3"
    aud.write_bytes(b"x")
    return aud


def _stages(aud, analyze_fn, built):
    def build_stub(out, n, cfg):
        built.append(n)
        (out / f"work-{n}").mkdir(exist_ok=True)
        (out / f"work-{n}" / "final.mp4").write_bytes(b"v")
        return "id", [("PASS", "x", "")], out / "v.mp4"

    def check(a, min_len):
        if getattr(check, "bad", None) == check.calls:
            check.calls += 1
            raise download.BadAudio("ffmpeg cannot decode the file: Invalid data")
        check.calls += 1
        return a, ["1 decoder warning(s): Illegal Audio-MPEG-Header"]

    check.calls = 0
    return {"fetch": lambda e, c, m: (aud, []), "check_audio": check, "analyze": analyze_fn, "build": build_stub}, check


def test_corrupt_audio_is_reported_and_the_rest_continue(tmp_path):
    aud = _batch_env(tmp_path, ["One", "Two", "Three"])
    frag = {"first": 0, "last": 0, "start": 0, "end": 40, "length": 40, "reason": "x", "low_ratio": 0.0}
    built = []
    stages, check = _stages(aud, lambda a, p, c: {"fragment": frag, "lines": [], "beats": [], "summary": {}}, built)
    check.bad = 0  # the first song is damaged
    rep = batch.run_batch("tiktok", 2, "2026-11-06", CFG, root=tmp_path, stages=stages)
    songs = {r["song"]: r for r in rep["songs"]}
    assert rep["succeeded"] == 2 and built == [1, 2]
    assert songs["A — One"]["stages"]["fetch"] == "bad_audio" and "rejected" in songs["A — One"]["note"] and "render" not in songs["A — One"]["stages"]
    assert songs["A — Two"]["audio_notes"] and "Illegal Audio-MPEG-Header" in songs["A — Two"]["audio_notes"][0]  # warnings are kept in the report
    assert songs["A — Two"]["stages"]["render"] == "ok" and songs["A — Three"]["stages"]["render"] == "ok"


def test_unreliable_lyrics_are_not_rendered_and_the_rest_continue(tmp_path):
    aud = _batch_env(tmp_path, ["Bad", "Good"])
    built = []

    def an(a, p, c):
        low = 0.2 if not built and not hasattr(an, "seen") else 0.05
        an.seen = True
        return {"fragment": {"first": 0, "last": 0, "start": 0, "end": 40, "length": 40, "reason": "x", "low_ratio": low}, "lines": [], "beats": [], "summary": {}}

    stages, _ = _stages(aud, an, built)
    rep = batch.run_batch("tiktok", 1, "2026-11-06", CFG, root=tmp_path, stages=stages)
    songs = {r["song"]: r for r in rep["songs"]}
    assert rep["succeeded"] == 1 and built == [1]
    assert songs["A — Bad"]["stages"]["analyze"] == "low_confidence" and "not rendered" in songs["A — Bad"]["note"]
    assert songs["A — Good"]["stages"]["render"] == "ok"
    assert (tmp_path / "out" / "2026-11-06" / "analysis-1.json").exists()  # evidence kept for the owner


# ---- variety of card pictures
NEW_ARTS = ("phone", "window", "flame", "lock", "bird", "wave")


# ---- Claude-drawn pictures (kind "draw")
from pipeline import author, svg_safe  # noqa: E402

GOOD = ('<rect width="800" height="420" fill="#1b1f5c"/><defs><linearGradient id="lg"><stop offset="0" stop-color="#fff"/><stop offset="1" stop-color="#f0a"/></linearGradient></defs>'
        '<g transform="translate(400 210) rotate(10)"><circle r="80" fill="url(#lg)"/><path d="M-60 80L0 -90L60 80Z" fill="#ffd66b" stroke="#fff" stroke-width="6"/></g>')


def test_svg_clean_keeps_shapes_and_gradients():
    out = svg_safe.clean(GOOD)
    assert out and out.count("<circle") == 1 and 'id="lg"' in out and "url(#lg)" in out and "rotate(10)" in out
    assert svg_safe.clean(f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 800 420">{GOOD}</svg>')  # a full <svg> wrapper is unwrapped
    assert svg_safe.clean(out) == out  # idempotent: the renderer re-cleans what the author already cleaned


@pytest.mark.parametrize("bad", [
    "", "   ", "<rect", "<script>alert(1)</script>", '<rect width="5" height="5" onclick="x()"/><script/>', '<image href="http://evil/x.png"/>',
    '<use href="#a"/>', '<foreignObject><div/></foreignObject>', '<style>*{}</style><rect width="1" height="1"/>', "<!DOCTYPE x><rect/>",
    '<!ENTITY a "b">', '<rect width="1" height="1" fill="&lol;"/>', "<a href='x'><rect width='1' height='1'/></a>",
    "<rect width='1' height='1'/>" * 200, "<text>только текст</text>"])
def test_svg_clean_rejects_dangerous_or_unusable(bad):
    assert svg_safe.clean(bad) is None


def test_svg_clean_strips_dangerous_attributes_but_keeps_the_shape():
    out = svg_safe.clean('<rect width="10" height="10" onclick="x()" style="x:y" class="a" fill="url(http://evil)" id="r" transform="evil(1)" stroke="red"/>')
    assert out == '<rect width="10" height="10" stroke="red"></rect>'  # onclick/style/class/id(on a rect)/bad transform dropped; bad url() dropped
    t = svg_safe.clean('<g><title>x</title><text x="1">надпись</text><rect width="9" height="9"/></g>')
    assert t == '<g><rect width="9" height="9"></rect></g>'  # text in a picture is dropped


def test_scope_prefixes_gradient_ids_per_card():
    m = svg_safe.scope(svg_safe.clean(GOOD), 7)
    assert 'id="dr7_lg"' in m and "url(#dr7_lg)" in m and 'id="lg"' not in m


def test_author_drops_a_bad_drawing_and_keeps_good_ones():
    ws = author.sanitize_widgets([
        {"lines": [0], "kind": "draw", "svg": GOOD, "motion": "sway", "app": "Заметки"},
        {"lines": [1], "kind": "draw", "svg": "<script>1</script>"},
        {"lines": [2], "kind": "draw"},
        {"lines": [3], "kind": "draw", "svg": GOOD, "motion": "explode"}], 4)
    assert ws[0]["kind"] == "draw" and ws[0]["motion"] == "sway" and "<circle" in ws[0]["svg"]
    assert [w["lines"] for w in ws] == [[0], [3]]  # nothing unsafe survives; lines 1 and 2 get a scene picked by meaning (widgets_plan)
    assert ws[1]["kind"] == "draw" and "motion" not in ws[1]  # unknown motion ignored (renderer defaults to float)


def test_prompt_explains_drawing_and_wants_no_text_in_pictures():
    p = author.build_prompt({"artist": "A", "title": "T"}, [{"start": 0, "end": 3, "text": "строка", "words": []}], CFG)
    assert "draw: svg" in p and "tw (" in p and "text/tspan" in p and "0 0 800 420" in p
    assert "больше не используй" in p  # the slideshow of frames is retired: objects move by tweens


def test_window_with_a_long_instrumental_pause_is_avoided():
    lines = _lines(low=set())
    for k in range(6, 16):  # a 12 s break after line 5: lines 6.. start later
        lines[k]["start"] += 12
        lines[k]["end"] += 12
        for w in lines[k]["words"]:
            w["s"] += 12
            w["e"] += 12
    base = analyze.pick_fragment(lines, "", 20, 40)  # the plain logic grows the chorus window across the break
    assert analyze.max_gap(lines, base) > 5
    f = analyze.pick_reliable(lines, "", CFG20)
    assert f["max_gap"] <= 5 and f["low_ratio"] <= .15


# ---- recognition: second pass with a bigger model, hallucination filter
def _L(texts, start=0.0, p=.9):
    out, t = [], start
    for x in texts:
        out.append({"start": t, "end": t + 2.5, "text": x, "words": [{"w": w, "s": t + j * .4, "e": t + j * .4 + .35, "p": p} for j, w in enumerate(x.split())]})
        t += 3.0
    return out


RCFG = dict(CFG, whisper=dict(CFG["whisper"], refine_model="large-v3", refine_margin=2.0))


def test_whisper_credits_hallucination_is_dropped():
    lines = _L(["живая строка песни", "Редактор субтитров А.Семкин", "ещё строка", "Продолжение следует..."])
    kept = [l["text"] for l in analyze.clean_lines(lines, "ru")]
    assert kept == ["живая строка песни", "ещё строка"]


def test_refine_replaces_only_the_window_and_keeps_everything_else(monkeypatch):
    lines = _L(["a1 a2 a3", "b1 b2 b3", "c1 c2 c3", "d1 d2 d3", "e1 e2 e3"])
    frag = {"first": 1, "last": 3, "start": lines[1]["start"], "end": lines[3]["end"], "length": 8.5, "reason": "x", "low_ratio": .3}
    calls = []

    def fake(path, cfg, model=None, window=None):
        calls.append((model, window))
        return _L(["B1 B2 B3", "C1 C2 C3", "D1 D2 D3"], start=3.0, p=.95)

    monkeypatch.setattr(analyze, "transcribe", fake)
    out, f, note = analyze.refine_fragment("x.mp3", lines, frag, RCFG)
    assert calls == [("large-v3", (1.0, 13.5))]  # the window plus a 2 s margin, nothing else
    assert [l["text"] for l in out] == ["a1 a2 a3", "B1 B2 B3", "C1 C2 C3", "D1 D2 D3", "e1 e2 e3"]
    assert (f["first"], f["last"]) == (1, 3) and f["low_ratio"] == 0 and "large-v3" in note and "30%" in note


def test_refine_failure_or_empty_answer_keeps_the_first_pass(monkeypatch):
    lines = _L(["a1 a2 a3", "b1 b2 b3", "c1 c2 c3"])
    frag = {"first": 0, "last": 2, "start": 0.0, "end": 8.5, "length": 8.5, "reason": "x", "low_ratio": .1}

    def boom(*a, **k):
        raise MemoryError("no memory for the model")

    monkeypatch.setattr(analyze, "transcribe", boom)
    out, f, note = analyze.refine_fragment("x.mp3", lines, frag, RCFG)
    assert out is lines and f is frag and "failed" in note and "MemoryError" in note
    monkeypatch.setattr(analyze, "transcribe", lambda *a, **k: _L(["z"], start=1.0))  # one word instead of nine: not trusted
    out, f, note = analyze.refine_fragment("x.mp3", lines, frag, RCFG)
    assert out is lines and "kept the first pass" in note


def test_refine_is_off_without_a_different_model():
    lines = _L(["a1 a2"])
    frag = {"first": 0, "last": 0, "start": 0.0, "end": 2.5, "length": 2.5, "reason": "x", "low_ratio": 0}
    for cfg in (CFG, dict(CFG, whisper=dict(CFG["whisper"], refine_model=""))):
        cfg = dict(cfg, whisper=dict(cfg["whisper"], **({"refine_model": cfg["whisper"]["model"]} if cfg is CFG else {})))
        assert analyze.refine_fragment("x.mp3", lines, frag, cfg) == (lines, frag, "")


def test_a_long_line_can_be_two_cards_and_empty_lines_join_a_neighbour():
    from pipeline import author, script_gen
    words = lambda t0, n: [{"w": f"w{k}", "s": t0 + k * .5, "e": t0 + k * .5 + .4, "p": .9} for k in range(n)]
    lines = [{"start": 0, "end": 4, "text": "a", "words": words(0, 8)}, {"start": 4.5, "end": 5.5, "text": "у-у", "words": words(4.5, 2)},
             {"start": 6, "end": 8, "text": "b", "words": words(6, 4)}]
    an = {"lines": lines, "fragment": {"first": 0, "last": 2, "start": 0.0, "end": 8.0}, "beats": []}
    ws = author.sanitize_widgets([{"lines": [0], "kind": "draw", "svg": GOOD, "half": 0}, {"lines": [0], "kind": "draw", "svg": GOOD, "half": 1},
                                  {"lines": [1, 2], "kind": "draw", "svg": GOOD}, {"lines": [0], "kind": "draw", "svg": GOOD}], 3)
    assert [(w["lines"], w.get("half")) for w in ws] == [([0], 0), ([0], 1), ([1, 2], None)]  # the 4th overlaps line 0: dropped
    sc = script_gen.build_scenes(an, {"artist": "A", "title": "T"}, {"tail_sec": 2.5, "whisper": {"min_confidence": .5}}, widgets=ws)["scenes"]
    assert [len(s["words"]) for s in sc if s["role"] == "lyric"] == [4, 4, 6]  # 8 words split 4+4; the vocalise joins the last card


def test_cards_are_remembered_between_runs_and_joined_with_views(tmp_path):
    from pipeline import batch, insights
    acc = tmp_path / "acc"
    for i, th in enumerate(("light", "dark", "dark")):
        batch.remember_cards(acc, f"2026-11-0{i + 1}", f"A — S{i}", {"hook": "h", "theme": th, "widgets": [{"kind": "draw", "big": "x"}, {"kind": "pair"}]})
    past = batch.recall_cards(acc, 2)
    assert [r["song"] for r in past] == ["A — S1", "A — S2"] and past[0]["draw_share"] == .5 and past[0]["details"] == 1
    (acc / "views.csv").write_text("song,views\na — s0,100\nA — S1,300\n", encoding="utf-8")
    rows, out = insights.table(batch.recall_cards(acc, 10), insights.load_views(acc / "views.csv"))
    assert sorted(r["views"] for r in rows) == [100, 300] and ("theme", "dark", 1, 300) in out


