"""The scenario -> Remotion props step (pipeline/widgets_plan.py): kinds, defaults, notifications, drawn pictures, theme flags.
The pictures themselves live in remotion/src/widgets and are checked by rendering frames (docs/remotion.md)."""
import json

import pytest

from pipeline import author, script_gen, widget_kinds as wk, widgets_plan as wp
from pipeline.common import load_config

CFG = load_config()
GOOD = '<rect width="800" height="420" fill="#eef"/><circle cx="400" cy="210" r="80" fill="#f49"/>'
SPEC = {"palette": "cold", "song": {"artist": "A", "title": "T"}, "hook": "хук?", "metaphor": "love"}


def _plan(kinds, text="я иду домой по улицам"):
    t, lines = 0.0, []
    for _ in kinds:
        ws = [{"w": w, "s": t + j * .45, "e": t + j * .45 + .4, "p": .9} for j, w in enumerate(text.split())]
        lines.append({"start": ws[0]["s"], "end": ws[-1]["e"], "text": text, "words": ws})
        t = ws[-1]["e"] + .4
    an = {"lines": lines, "fragment": {"first": 0, "last": len(lines) - 1, "start": 0, "end": lines[-1]["end"]}, "beats": []}
    wds = [dict(k, lines=[i]) if isinstance(k, dict) else {"lines": [i], "kind": k, "art": "sunset"} for i, k in enumerate(kinds)]
    return script_gen.build_scenes(an, {"artist": "A", "title": "T"}, CFG, widgets=wds)


@pytest.mark.parametrize("kind", wp.KINDS)
def test_every_kind_resolves_to_json_props(kind):
    w = {"kind": kind, "art": "sunset", "svg": GOOD} if kind == "draw" else {"kind": kind, "art": "sunset"}
    props = wp.resolve(_plan([w]), SPEC, CFG)
    json.dumps(props, ensure_ascii=False)
    card = props["scenes"][0]
    assert card["kind"] == kind and card["app"] and card["icon"] and props["scenes"][-1]["role"] == "outro"


def test_props_shape_and_hook_and_credit():
    props = wp.resolve(_plan(["scene", "pair"]), SPEC, CFG)
    assert (props["width"], props["height"], props["fps"]) == (CFG["width"], CFG["height"], CFG["fps"])
    assert props["hook"] == "ХУК?" and props["credit"].startswith("автор: ") and props["nCards"] == 2
    assert props["ostart"] == props["scenes"][-1]["start"] < props["duration"]
    assert [s["i"] for s in props["scenes"]] == [0, 1, 2]


def test_long_hook_is_cut_and_theme_flags():
    spec = dict(SPEC, hook="очень длинный вопрос который не влезет в строку хука никак")
    assert len(wp.resolve(_plan(["scene"]), spec, CFG)["hook"]) <= 36
    light, dark = wp.resolve(_plan(["scene"]), SPEC, CFG), wp.resolve(_plan(["scene"]), dict(SPEC, theme="dark"), CFG)
    assert not light["dark"] and dark["dark"] and dark["pal"]["b"] == list(wp.DARK_BG) and dark["pal"]["alt"] == list(wp.PAL["cold"][:3])
    assert wp.resolve(_plan(["scene"]), SPEC, dict(CFG, alternate_theme=True))["alternate"] is True
    assert wp.resolve(_plan(["scene"]), SPEC, dict(CFG, alternate_theme=False))["alternate"] is False


def test_contrast_helpers():
    assert wp.readable("not-a-colour") == wp.INK and wp.readable("#14141f") == "#14141f"
    assert wp.contrast(wp.readable("#ff9a6b"), wp.WORST_BG) >= 3.0 and wp.readable("#3b6cff") != "#14141f"


def test_cards_hold_through_vocal_gaps_but_not_past_the_end():
    props = wp.resolve(_plan(["scene", "scene"]), SPEC, CFG)
    a, b, outro = props["scenes"]
    assert a["end"] >= b["start"] - 1e-6 or a["end"] <= b["start"]
    assert all(s["end"] <= props["duration"] + 1e-6 for s in props["scenes"])


def test_default_apps_notifications_and_banners():
    p = wp.resolve(_plan(["thermo", "alert", "scene", {"kind": "target", "notify": False}]), SPEC, CFG)
    assert p["scenes"][0]["notify"]["app"] == wk.DEFAULT_NOTIFY["thermo"]["app"] and p["scenes"][3]["notify"] is None
    assert p["scenes"][2]["notify"] and p["scenes"][2]["notify"]["glyph"] in ("bubble", "heart", "pin", "lines", "bell")
    assert p["scenes"][0]["app"] == wk.DEFAULT_APP["thermo"][0] and p["scenes"][0]["icon"] == wk.DEFAULT_APP["thermo"][1]


def test_scene_without_art_gets_one_and_never_repeats_inside_a_video():
    p = wp.resolve(_plan([{"kind": "scene"}] * 6), SPEC, CFG)
    arts = [s["w"]["art"] for s in p["scenes"] if s["role"] == "lyric"]
    assert all(a in wp.ART_KEYS for a in arts) and len(set(arts)) == len(arts)
    assert wp.ARTS[wp._pick("звонит телефон", 0)][0] == "phone"  # meaning first
    assert wp._pick("звонит телефон", 0, ["phone"]) != wp._pick("звонит телефон", 0)  # ...unless already shown


def test_auto_kind_rotates_and_is_capped():
    line = "ты любишь меня, мы вместе, почему?"
    assert len({wp._auto(line, "", {}, seed)["kind"] for seed in range(6)}) >= 2
    assert wp._auto(line, "camera", {"dots": 2, "search": 2}) == {} or wp._auto(line, "pulse", {}, 0)["kind"] != "pulse"
    assert wp._auto("смерть рядом, любовь", "", {}, 3)["kind"] == "alert"  # danger keeps priority
    assert wp._auto("Ты ему сперва дала, потом полюбила", "pulse") == {}


def test_drawn_card_is_cleaned_scoped_and_falls_back():
    good = wp.resolve(_plan([{"kind": "draw", "svg": GOOD, "big": "03:32", "chips": ["а", "б"]}]), SPEC, CFG)["scenes"][0]
    assert good["kind"] == "draw" and 'id="' not in good["w"]["frames"][0] and good["w"]["big"] == "03:32" and good["w"]["anim"] is False
    anim = wp.resolve(_plan([{"kind": "draw", "svg": '<g id="a"><circle cx="9" cy="9" r="9"/></g><rect id="b" x="1" y="1" width="9" height="9"/>',
                              "tw": [{"id": "a", "to": {"x": 5}}, {"id": "b", "to": {"y": 5}, "loop": True}, {"id": "nope", "to": {"x": 1}}]}]), SPEC, CFG)["scenes"][0]
    assert anim["w"]["anim"] and 'id="dr0_a"' in anim["w"]["frames"][0] and len(anim["w"]["tw"]) == 2
    bad = wp.resolve(_plan([{"kind": "draw", "svg": "<script/>", "art": "flame"}]), SPEC, CFG)["scenes"][0]
    assert bad["kind"] == "scene" and bad["w"]["art"] == "flame"  # a hand-edited bad drawing never reaches the renderer


def test_several_frames_keep_only_safe_ones():
    sc = wp.resolve(_plan([{"kind": "draw", "frames": [GOOD, GOOD, "<script>1</script>"]}]), SPEC, CFG)["scenes"][0]
    assert len(sc["w"]["frames"]) == 2


def test_different_songs_pick_different_pictures_for_the_same_lines():
    seen = set()
    for t in ("A", "BB", "CCC", "DDDD", "EEEEE", "F"):
        p = wp.resolve(_plan([{"kind": "scene"}] * 2, "ничего особенного тут"), dict(SPEC, song={"artist": "X", "title": t}), CFG)
        seen.add(tuple(s["w"]["art"] for s in p["scenes"] if s["role"] == "lyric"))
    assert len(seen) >= 2


def test_caption_row_only_when_a_card_has_cap():
    assert wp.resolve(_plan(["scene"]), SPEC, CFG)["hasCap"] is False
    assert wp.resolve(_plan([{"kind": "scene", "cap": "подпись"}]), SPEC, CFG)["hasCap"] is True


def test_render_rejects_props_without_cards():
    from pipeline import render
    assert render.check_props({"scenes": [], "duration": 5, "ostart": 3})
    assert not render.check_props(wp.resolve(_plan(["scene"]), SPEC, CFG))


def test_author_keeps_chips_and_big_for_drawings():
    w = author.sanitize_widgets([{"lines": [0], "kind": "draw", "frames": [GOOD], "chips": ["а", "б", "в", " "], "big": "×2"}], 1)
    assert w[0]["chips"] == ["а", "б"] and w[0]["big"] == "×2"


def test_cards_snap_to_a_near_beat_and_keep_order():
    plan = _plan(["scene", "scene", "scene"])
    starts = [s["start"] for s in plan["scenes"]]
    plan["beats"] = [round(starts[1] + 0.1, 3), round(starts[2] + 0.6, 3)]  # one beat close to card 2, one too far from card 3
    props = wp.resolve(plan, SPEC, CFG)
    got = [s["start"] for s in props["scenes"]]
    assert got[1] == plan["beats"][0] and got[2] == starts[2]  # snapped / left alone
    assert all(a["end"] <= b["start"] + 1e-6 or a["role"] == "outro" for a, b in zip(props["scenes"], props["scenes"][1:])), "no overlap after snapping"
    assert wp.resolve(plan, SPEC, dict(CFG, beat_snap_sec=0))["scenes"][1]["start"] == starts[1]  # switched off


@pytest.mark.skipif(not __import__("shutil").which("ffmpeg"), reason="ffmpeg not installed")
def test_motion_check_tells_a_still_picture_from_a_moving_one(tmp_path):
    import subprocess
    from pipeline import qa
    still, moving = tmp_path / "still.mp4", tmp_path / "moving.mp4"
    for out, src in ((still, "color=c=gray:s=1080x1920:d=3:r=30"), (moving, "color=c=gray:s=1080x1920:d=3:r=30,noise=alls=60:allf=t")):
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", src, "-pix_fmt", "yuv420p", str(out)], check=True)
    cards = [{"start": 0.0, "end": 3.0}]
    assert qa.motion_levels(still, cards)[0] < qa.STILL_DIFF < qa.motion_levels(moving, cards)[0]
    assert qa.motion_levels(still, [{"start": 0.0, "end": 0.8}]) == [None]  # too short to tell
