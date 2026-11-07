"""Stability of the daily run: readable cards (contrast, painted text), HyperFrames check handling, audio validation,
low-confidence lyrics, one bad song never stops the batch."""
import json
import shutil
import subprocess

import pytest

from pipeline import analyze, batch, download, render, render_widgets as rw, script_gen
from pipeline.common import load_config

CFG = load_config()
HAVE_FFMPEG = bool(shutil.which("ffmpeg") and shutil.which("ffprobe"))
ffmpeg = pytest.mark.skipif(not HAVE_FFMPEG, reason="ffmpeg/ffprobe not installed")


# ---- readable cards
def test_unsung_word_grey_and_accents_pass_contrast():
    assert rw.contrast(rw.GREY, rw.CARD_BG) >= 3.0 and rw.contrast(rw.GREY, rw.WORST_BG) >= 3.0  # also under an orb / a fading card
    for col in ("#ff9a6b", "#ff7a3d", "#8a6bff", "#3b8bff", "#ff4f6d", "#4a6a9a", "#14956f", "#ffd400", "#ffffff", "#abc"):
        assert rw.contrast(rw.readable(col), rw.CARD_BG) >= 3.0 and rw.contrast(rw.readable(col), rw.WORST_BG) >= 3.0, col
    assert rw.readable("not-a-colour") == rw.INK and rw.readable("#14141f") == "#14141f"
    assert rw.readable("#3b6cff") != "#14141f"  # a colour that already reads is only darkened as far as needed, hue kept


def _page(palette, kinds=None):
    kinds = kinds or list(rw.KINDS)
    t, lines = 0.0, []
    for i, _ in enumerate(kinds):
        ws = [{"w": w, "s": t + j * .45, "e": t + j * .45 + .4, "p": .9} for j, w in enumerate("я иду домой по улицам".split())]
        lines.append({"start": ws[0]["s"], "end": ws[-1]["e"], "text": "я иду домой по улицам", "words": ws})
        t = ws[-1]["e"] + .4
    an = {"lines": lines, "fragment": {"first": 0, "last": len(lines) - 1, "start": 0, "end": lines[-1]["end"]}, "beats": [1, 2]}
    wds = [{"lines": [i], "kind": k, "art": "sunset"} for i, k in enumerate(kinds)]
    plan = script_gen.build_scenes(an, {"artist": "A", "title": "8800"}, CFG, intro=1.2, widgets=wds)
    return rw.build_html(plan, {"palette": palette, "song": {"artist": "A", "title": "8800"}, "hook": "ХУК", "metaphor": "love"}, CFG)


@pytest.mark.parametrize("palette", ["dusk", "cold", "warm", "contrast"])
def test_no_invisible_text_and_orbs_marked_as_overlays(palette):
    h = _page(palette)
    assert "color:transparent" not in h and "text-fill-color" not in h  # glyphs are always painted with an opaque colour
    assert "#b9b4cf" not in h  # the old 2:1 grey
    assert 'class="cr" style' not in h and 'class="cr" data-layout-allow-occlusion' in h  # orbs fly over text on purpose


def test_result_widget_text_is_solid_and_readable():
    h = _page("warm", ["search"])
    css = h[h.index(".rbig{"):].split("}")[0]
    assert "color:#" in css and "transparent" not in css
    col = css.split("color:")[1].split(";")[0]
    assert rw.contrast(col, rw.CARD_BG) >= 3.0


# ---- HyperFrames check: diagnostics are acted on, not hidden
def _fake_check(monkeypatch, data):
    monkeypatch.setattr(render, "_run", lambda cmd, stdout_only=False, **kw: (0, "progress...\n" + json.dumps(data)))


def test_check_blocks_contrast_and_unpainted_text_even_as_warnings(tmp_path, monkeypatch, capsys):
    data = {"ok": True, "contrast": {"findings": [{"code": "contrast_aa_failure", "severity": "warning", "selector": "#c0w1", "text": "дала",
                                                   "message": "Contrast is 1.99:1; WCAG AA requires 3:1.", "suggestedColor": "rgb(149,145,167)"}]},
            "layout": {"findings": [{"code": "text_not_painted", "severity": "error", "selector": "#rb2", "text": "0 результатов",
                                     "message": "Text paints with an effectively transparent fill.", "fixHint": "Set an opaque color."}]},
            "craft": {"findings": [{"code": "film_silent", "severity": "warning", "message": "no sound"}]}}
    _fake_check(monkeypatch, data)
    ok, errs = render.check(tmp_path)
    assert not ok and len(errs) == 2
    assert any("contrast_aa_failure" in e and "#c0w1" in e and "1.99" in e for e in errs)
    assert any("text_not_painted" in e and "#rb2" in e for e in errs)
    assert json.loads((tmp_path / "check.json").read_text(encoding="utf-8"))["ok"] is True  # full report kept for diagnosis
    assert "1 other warnings" in capsys.readouterr().out  # the remaining warning is counted, not hidden


def test_check_passes_when_only_ordinary_warnings(tmp_path, monkeypatch):
    _fake_check(monkeypatch, {"ok": True, "lint": {"findings": [{"code": "overlapping_gsap_tweens", "severity": "warning", "message": "x"}]}})
    assert render.check(tmp_path) == (True, [])


def test_check_unreadable_output_fails(tmp_path, monkeypatch):
    monkeypatch.setattr(render, "_run", lambda cmd, stdout_only=False, **kw: (1, "npm ERR!"))
    ok, errs = render.check(tmp_path)
    assert not ok and "unreadable" in errs[0]


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


def test_new_pictures_are_available_to_claude_and_the_fallback():
    assert len(rw.ART_KEYS) >= 15 and all(a in rw.ART_KEYS for a in NEW_ARTS)
    for a in NEW_ARTS:
        assert f'id="' in rw._art(a, 3) and rw._art_anim(a, 3, 1.0, 2.0)  # drawn and animated
    from pipeline import author
    ws = author.sanitize_widgets([{"lines": [0], "kind": "scene", "art": "flame"}, {"lines": [1], "kind": "scene", "art": "nonsense"}], 2)
    assert ws[0]["art"] == "flame" and "art" not in ws[1]


def test_pick_never_repeats_a_picture_inside_one_video():
    texts = ["а дальше тишина", "и снова та же ночь", "он молча ушёл", "ночь и тишина", "снова ночь", "ночь", "ночь опять", "ночью", "ночь без сна"]
    used = []
    for i, t in enumerate(texts):
        used.append(rw.ARTS[rw._pick(t, i, used, seed=5)][0])
    assert len(set(used)) == len(used)  # even when every line says "ночь" (moon)
    assert rw.ARTS[rw._pick("звонит телефон", 0)][0] == "phone"  # meaning still comes first
    assert rw._pick("звонит телефон", 0, ["phone"]) != rw._pick("звонит телефон", 0)  # ...unless that picture was already shown


def test_auto_kind_rotates_and_is_capped():
    line = "они смотрят, а я один, и кто мне скажет почему"  # matches camera, dots, search
    kinds = {rw._auto(line, "", {}, seed)["kind"] for seed in range(6)}
    assert len(kinds) >= 2  # different songs/lines do not all get the same widget
    assert rw._auto(line, "camera", {"dots": 2, "search": 2}) == {}  # previous kind and kinds used twice are skipped
    assert rw._auto("смерть рядом, любовь", "", {}, 3)["kind"] == "alert"  # danger keeps priority


def test_builds_differ_between_songs_for_the_same_lines():
    lines = [{"start": i * 3.0, "end": i * 3.0 + 2.5, "text": "ну вот и всё теперь тихо",
              "words": [{"w": w, "s": i * 3.0 + j * .4, "e": i * 3.0 + j * .4 + .35, "p": .9} for j, w in enumerate("ну вот и всё теперь тихо".split())]} for i in range(8)]
    an = {"lines": lines, "fragment": {"first": 0, "last": 7, "start": 0, "end": 24}, "beats": []}
    seen = []
    for t in ("Один", "Другой", "Третий"):
        plan = script_gen.build_scenes(an, {"artist": "A", "title": t}, CFG, intro=1.2)
        h = rw.build_html(plan, {"palette": "cold", "song": {"artist": "A", "title": t}, "hook": "X", "metaphor": "love"}, CFG)
        seen.append(tuple(a for a in rw.ART_KEYS if f'class="sc"' in h and h.count(a) and a in ("lock", "bird", "wave", "flame", "phone", "window") and f'id="{ {"lock": "lk", "bird": "bd", "wave": "wv", "flame": "fl", "phone": "pw", "window": "wl"}[a] }' in h))
    assert len(set(seen)) > 1


def test_author_prompt_asks_for_other_kinds_than_the_rest_of_the_day():
    from pipeline import author
    lines = [{"start": 0, "end": 3, "text": "строка", "words": []}]
    p = author.build_prompt({"artist": "A", "title": "T", "avoid_kinds": ["pair", "pulse"]}, lines, CFG)
    assert "pair, pulse" in p and "{{AVOID}}" not in p and "flame" in p
    assert "{{AVOID}}" not in author.build_prompt({"artist": "A", "title": "T"}, lines, CFG)


def test_batch_tells_the_author_what_earlier_videos_used(tmp_path):
    aud = _batch_env(tmp_path, ["One", "Two"])
    frag = {"first": 0, "last": 0, "start": 0, "end": 40, "length": 40, "reason": "x", "low_ratio": 0.0}
    built, seen = [], []
    stages, _ = _stages(aud, lambda a, p, c: {"fragment": frag, "lines": [], "beats": [], "summary": {}}, built)

    def author(entry, analysis, spec, cfg):
        seen.append(list(entry["avoid_kinds"]))
        return analysis, dict(spec, widgets=[{"lines": [0], "kind": "pair"}, {"lines": [1], "kind": "ring"}]), "claude: 2 cards"

    stages["author"] = author
    batch.run_batch("tiktok", 2, "2026-11-06", CFG, root=tmp_path, stages=stages)
    assert seen == [[], ["pair", "ring"]]


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


def test_author_turns_a_bad_drawing_into_a_template_picture_and_keeps_good_ones():
    ws = author.sanitize_widgets([
        {"lines": [0], "kind": "draw", "svg": GOOD, "motion": "sway", "art": "moon", "app": "Заметки"},
        {"lines": [1], "kind": "draw", "svg": "<script>1</script>", "art": "lock"},
        {"lines": [2], "kind": "draw"},
        {"lines": [3], "kind": "draw", "svg": GOOD, "motion": "explode"}], 4)
    assert ws[0]["kind"] == "draw" and ws[0]["motion"] == "sway" and "<circle" in ws[0]["svg"]
    assert ws[1] == {"lines": [1], "kind": "scene", "art": "lock"}  # nothing unsafe survives; the line still gets a picture
    assert ws[2]["kind"] == "scene"
    assert ws[3]["kind"] == "draw" and "motion" not in ws[3]  # unknown motion ignored (renderer defaults to float)


def test_draw_card_renders_scoped_svg_and_a_loop_and_falls_back():
    h, j = rw._body("draw", {"svg": GOOD, "motion": "pulse"}, 4, 3.0, 2.5, "x")
    assert 'id="dr4"' in h and "dr4_lg" in h and "<script" not in h and j and "scale" in j[0]
    h2, j2 = rw._body("draw", {"svg": "<script/>", "art": "flame"}, 5, 3.0, 2.5, "x")  # hand-edited spec: bad drawing never reaches the page
    assert "<script" not in h2 and 'id="fl5"' in h2
    assert all(rw._draw_anim(m, 1, 0, 2)[0].startswith('tl.fromTo("#dr1"') for m in (*svg_safe.MOTIONS, None))


def test_prompt_explains_drawing_and_wants_no_text_in_pictures():
    p = author.build_prompt({"artist": "A", "title": "T"}, [{"start": 0, "end": 3, "text": "строка", "words": []}], CFG)
    assert "draw: frames" in p and "text/tspan" in p and "0 0 800 420" in p


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


def test_muted_text_greys_read_on_pastel_backgrounds_too():
    import pathlib
    src = "".join(pathlib.Path(f).read_text(encoding="utf-8") for f in ("pipeline/render_widgets.py", "pipeline/widget_kinds.py"))
    for old in ("#7a7592", "#7a7a92", "#6b6585"):  # these measured 2.8-2.97:1 on the pastel background (a real HyperFrames failure)
        assert old not in src
    assert rw.contrast("#5f5a7c", "#f1c7e2") >= 4 and rw.contrast("#5f5a7c", rw.CARD_BG) >= 6


def test_text_on_the_dark_island_banner_stays_light():
    css = rw.build_html.__code__  # noqa: F841 - the CSS lives inside build_html's template; check the rendered page instead
    h = _page("dusk", ["pair"])
    now = h[h.index(".now{"):].split("}")[0]
    col = now.split("color:")[1].split(";")[0]
    assert rw.contrast(col, "#14141f") >= 4.5  # "сейчас" sits on the dark banner: darkening every grey made it unreadable


def test_a_drawn_card_can_be_several_frames_and_only_safe_ones_survive():
    ws = author.sanitize_widgets([
        {"lines": [0], "kind": "draw", "frames": [GOOD, "<script>1</script>", GOOD, GOOD, GOOD, GOOD, GOOD]},  # bad frame dropped, max 5 kept
        {"lines": [1], "kind": "draw", "frames": ["<script>1</script>"], "art": "moon"},                         # nothing usable -> template picture
        {"lines": [2], "kind": "pair", "frames": [GOOD]}], 3)                                                   # frames only belong to draw
    assert ws[0]["kind"] == "draw" and len(ws[0]["frames"]) == 5 and all("<circle" in f for f in ws[0]["frames"])
    assert ws[1]["kind"] == "scene" and "frames" not in ws[1] and "frames" not in ws[2]


def test_frames_follow_each_other_about_once_a_second():
    from pipeline import render_widgets as rw
    html_, js = rw._body("draw", {"frames": [GOOD, GOOD, GOOD], "svg": "<script>1</script>"}, 4, 10.0, 3.0, "x")
    assert html_.count('id="df4_') == 3 and 'id="dr4f1_lg"' in html_ and 'id="dr4f2_lg"' in html_ and "<script" not in html_
    assert any('"#df4_1"' in l and "opacity:1" in l and "10.9" not in l and ",11.0)" in l.replace(" ", "") or ",11)" in l for l in js)  # frame 2 comes in at +1 s
    assert any('"#df4_0"' in l and "opacity:0" in l for l in js)  # and the previous one leaves
    h1, j1 = rw._body("draw", {"svg": GOOD}, 5, 0.0, 3.0, "x")  # a single drawing still works as before
    assert h1.count('id="df5_') == 1 and not any("opacity:1,duration:.3" in l for l in j1)
