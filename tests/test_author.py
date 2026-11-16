import json

from pipeline import author

CFG = {"min_len": 10, "max_len": 40, "author": {"enabled": True}}
LINES = [{"text": f"строка {i}", "start": i * 4.0, "end": i * 4.0 + 3.5, "words": []} for i in range(8)]
AN = {"lines": LINES, "fragment": {"first": 0, "last": 7, "start": 0.0, "end": 31.5, "length": 31.5, "reason": "t"}}
SPEC = {"id": "x", "caption": "c", "hashtags": ["#a", "#b", "#c"]}
ENTRY = {"artist": "A", "title": "T"}
DRAW = '<rect width="800" height="420" fill="#eef"/><circle cx="400" cy="210" r="80" fill="#f49"/>'
SC = {"about": "про дружбу и путь с нуля", "arc": ["вместе начали", "поссорились", "снова рядом"], "trim": {"from": 1, "to": 5}, "hook": "кто виноват?",
      "caption": "Про любовь. Сделано с ИИ", "mood": "dark",
      "cards": [{"lines": [0, 1], "kind": "draw", "idea": "два зонта под солнцем и дождём", "cap": "Ты"},
                {"lines": [2], "kind": "draw", "idea": "чат, где никто не отвечает"},
                {"lines": [3], "kind": "draw", "idea": "пустой стул у стола"},
                {"lines": [4], "kind": "draw", "idea": "ключ в двери"}]}
GOOD = {"widgets": [{"lines": [0, 1], "kind": "draw", "svg": DRAW, "notify": {"app": "Сообщения", "text": "Новое", "icon": "#34c759"}},
                    {"lines": [2], "kind": "draw", "svg": DRAW},
                    {"lines": [3], "kind": "draw", "svg": "<script/>"},  # an unsafe drawing: dropped, the line gets a plain panel
                    {"lines": [4], "kind": "draw", "svg": DRAW, "icon": "javascript:1"}]}  # bad icon dropped


def run(build, cfg=CFG, scenario=SC):
    """A runner that answers stage 1 (the prompt starts with ЭТАП 1) with the scenario and stage 2 with `build`."""
    dump = lambda x: x if isinstance(x, str) else json.dumps(x)
    return author.author(ENTRY, AN, SPEC, cfg, runner=lambda p, c: dump(scenario if p.startswith("ЭТАП 1") else build))


def test_the_prompt_carries_the_whole_song_for_the_theme():
    lines = [{"start": 0, "end": 3, "text": "куплет про море", "words": []}] * 2
    whole = [{"text": "куплет про море"}, {"text": "куплет про море"}, {"text": "припев про дом"}]
    p = author.build_prompt(ENTRY, lines[:1], CFG, whole)
    assert "припев про дом" in p and p.count("куплет про море") == 2 and "{{SONG}}" not in p  # once in the fragment list, once in the song (repeat dropped)
    assert "{{SONG}}" not in author.build_prompt(ENTRY, lines[:1], CFG)


def test_off_by_env_and_by_config():
    assert run(GOOD)[2] == "off"  # conftest sets VYBEX_NO_AUTHOR


def test_good_answer_trims_and_sanitizes(monkeypatch):
    monkeypatch.delenv("VYBEX_NO_AUTHOR")
    an, sp, st = run("```json\n" + json.dumps(GOOD) + "\n```")
    assert st.startswith("claude") and "trim 1..5" in st and "scenario 4 cards -> 3 built" in st
    assert (an["fragment"]["first"], an["fragment"]["last"]) == (1, 5) and an["fragment"]["length"] == 19.5
    assert [w["kind"] for w in sp["widgets"]] == ["draw", "draw", "draw"] and "icon" not in sp["widgets"][2]  # the unsafe drawing was dropped
    assert sp["hook"] == "КТО ВИНОВАТ?" and sp["caption"].endswith("ИИ") and sp["theme"] == "dark" and sp["about"].startswith("про дружбу")
    assert sp["scenario"]["arc"][0] == "вместе начали" and len(sp["scenario"]["cards"]) == 4  # the script stays with the spec


def test_the_build_prompt_is_made_from_the_scenario():
    sub = [{"start": 0, "end": 3, "text": "строка", "words": []}]
    p1 = author.build_scenario_prompt(ENTRY, sub, CFG, [{"text": "весь текст песни"}])
    assert p1.startswith("ЭТАП 1") and "весь текст песни" in p1 and "{{" not in p1
    p2 = author.build_prompt(ENTRY, sub, CFG, [{"text": "весь текст песни"}], SC)
    assert p2.startswith("ЭТАП 2") and "пустой стул у стола" in p2 and "вместе начали → поссорились → снова рядом" in p2 and "{{" not in p2


def test_a_build_that_ignores_the_scenario_is_redone_without_a_new_scenario(monkeypatch):
    monkeypatch.delenv("VYBEX_NO_AUTHOR")
    off = {"widgets": GOOD["widgets"][:3]}  # one card short
    calls = []
    def runner(p, c):
        calls.append(p[:7])
        return json.dumps(SC if p.startswith("ЭТАП 1") else (off if calls.count("ЭТАП 2 ") < 2 else GOOD))
    st = author.author(ENTRY, AN, SPEC, CFG, runner=runner)[2]
    assert st.startswith("claude") and "attempt 2" in st and calls == ["ЭТАП 1 ", "ЭТАП 2 ", "ЭТАП 2 "]


def test_an_unusable_scenario_falls_back(monkeypatch):
    monkeypatch.delenv("VYBEX_NO_AUTHOR")
    for bad in (dict(SC, cards=SC["cards"][:2]),                       # too few cards
                dict(SC, cards=SC["cards"][:2] + [dict(SC["cards"][0], kind="weather", lines=[3]), dict(SC["cards"][0], kind="night", lines=[4])]),  # ready-made scenes are not cards
                {k: v for k, v in SC.items() if k != "about"}):       # no theme of the whole song
        assert run(GOOD, scenario=bad)[2].startswith("fallback")


def test_retired_template_kinds_never_survive():
    old = ("pair", "pulse", "route", "venn", "ring", "thermo", "alert", "target", "polaroid", "versus", "counter", "search", "chat", "dots", "camera", "scene",
           "weather", "typing", "bloom", "duo", "breath", "deep", "unlock", "night")  # + the eight animated scenes (2026-11-16)
    w = [{"lines": [i], "kind": k, "from": 1, "to": 2, "art": "moon"} for i, k in enumerate(old)]
    assert author.sanitize_widgets(w, len(old)) == []  # the owner removed them: they must not appear (2026-11-09, scenes 2026-11-16)


def test_bad_trim_is_ignored_and_failures_fall_back(monkeypatch):
    monkeypatch.delenv("VYBEX_NO_AUTHOR")
    an, sp, st = run(GOOD, scenario=dict(SC, trim={"from": 0, "to": 0}))  # 3.5 s < min_len: whole fragment kept
    assert "no trim" in st and an is AN
    for bad in ("not json", {"widgets": [{"lines": [99], "kind": "pair"}]}):
        an, sp, st = run(bad)
        assert st.startswith("fallback") and sp is SPEC and an is AN
    def boom(p, c):
        raise RuntimeError("no token")
    assert author.author(ENTRY, AN, SPEC, CFG, runner=boom)[2].startswith("fallback")


def test_a_bad_first_answer_is_retried(monkeypatch):
    monkeypatch.delenv("VYBEX_NO_AUTHOR")
    answers, prompts = ["not json", json.dumps(SC), json.dumps(GOOD)], []
    def flaky(p, c):
        prompts.append(p)
        return answers.pop(0)
    st = author.author(ENTRY, AN, SPEC, CFG, runner=flaky)[2]
    assert st.startswith("claude") and "attempt 2" in st and len(prompts) == 3
    n = [0]
    def always_bad(p, c):
        n[0] += 1
        return "not json"
    assert author.author(ENTRY, AN, SPEC, CFG, runner=always_bad)[2].startswith("fallback") and n[0] == 3


def test_every_brief_is_different_and_names_no_ready_made_kinds():
    briefs = {author.variety() for _ in range(40)}
    assert len(briefs) > 6 and all("Стиль всех рисунков" in b and "НЕ используй виды" not in b for b in briefs)
