import json

from pipeline import author

CFG = {"min_len": 10, "max_len": 40, "author": {"enabled": True}}
LINES = [{"text": f"строка {i}", "start": i * 4.0, "end": i * 4.0 + 3.5, "words": []} for i in range(8)]
AN = {"lines": LINES, "fragment": {"first": 0, "last": 7, "start": 0.0, "end": 31.5, "length": 31.5, "reason": "t"}}
SPEC = {"id": "x", "caption": "c", "hashtags": ["#a", "#b", "#c"]}
ENTRY = {"artist": "A", "title": "T"}
GOOD = {"trim": {"from": 1, "to": 5}, "hook": "кто виноват?", "caption": "Про любовь. Сделано с ИИ",
        "widgets": [{"lines": [0, 1], "kind": "pair", "a": "Я", "b": "Ты", "notify": {"app": "Сообщения", "text": "Новое", "icon": "#34c759"}},
                    {"lines": [2], "kind": "thermo", "from": 36.6, "to": 38.9},
                    {"lines": [3], "kind": "hack", "label": "x"},       # unknown kind: dropped
                    {"lines": [3, 4], "kind": "ring", "from": 0, "to": 100, "icon": "javascript:1"},  # no number in the lines: dropped
                    {"lines": [4], "kind": "draw", "svg": '<rect width="800" height="420" fill="#eef"/><circle cx="400" cy="210" r="80" fill="#f49"/>', "icon": "javascript:1"}]}  # bad icon dropped


def run(res, cfg=CFG):
    return author.author(ENTRY, AN, SPEC, cfg, runner=lambda p, c: res if isinstance(res, str) else json.dumps(res))


def test_off_by_env_and_by_config():
    assert run(GOOD)[2] == "off"  # conftest sets VYBEX_NO_AUTHOR


def test_good_answer_trims_and_sanitizes(monkeypatch):
    monkeypatch.delenv("VYBEX_NO_AUTHOR")
    an, sp, st = run("```json\n" + json.dumps(GOOD) + "\n```")
    assert st.startswith("claude") and "trim 1..5" in st
    assert (an["fragment"]["first"], an["fragment"]["last"]) == (1, 5) and an["fragment"]["length"] == 19.5
    kinds = [w["kind"] for w in sp["widgets"]]
    assert kinds == ["pair", "thermo", "draw"] and "icon" not in sp["widgets"][2] and sp["hook"] == "КТО ВИНОВАТ?" and sp["caption"].endswith("ИИ")  # the ring quotes 100 %, the lines do not: dropped
    assert sp["widgets"][1]["from"] == 36.6


def test_a_template_as_the_last_card_is_rejected_and_retried(monkeypatch):
    monkeypatch.delenv("VYBEX_NO_AUTHOR")
    bad = dict(GOOD, widgets=GOOD["widgets"][:2])  # ends with thermo
    answers, prompts = [json.dumps(bad), json.dumps(GOOD)], []
    def runner(p, c):
        prompts.append(p)
        return answers.pop(0)
    st = author.author(ENTRY, AN, SPEC, CFG, runner=runner)[2]
    assert st.startswith("claude") and "attempt 2" in st and len(prompts) == 2


def test_number_cards_need_the_number_in_the_line():
    w = [{"lines": [0], "kind": "ring", "from": 0, "to": 92}, {"lines": [1], "kind": "dots", "from": 8000, "to": 1},
         {"lines": [2], "kind": "counter", "from": 5000, "to": 0}]
    assert [x["kind"] for x in author.sanitize_widgets(w, 3, ["Хранилище почти полно", "один из миллиардов", "осталось 0 монет"])] == ["counter"]
    assert [x["kind"] for x in author.sanitize_widgets(w, 3, ["заряд 92%", "всего 1 человек", "ноль"])] == ["ring", "dots"]
    assert len(author.sanitize_widgets(w, 3)) == 3  # no texts given: no check (hand-written specs)


def test_bad_trim_is_ignored_and_failures_fall_back(monkeypatch):
    monkeypatch.delenv("VYBEX_NO_AUTHOR")
    an, sp, st = run(dict(GOOD, trim={"from": 0, "to": 0}))  # 3.5 s < min_len
    assert "no trim" in st and an is AN
    for bad in ("not json", {"widgets": [{"lines": [99], "kind": "pair"}]}):
        an, sp, st = run(bad)
        assert st.startswith("fallback") and sp is SPEC and an is AN
    def boom(p, c):
        raise RuntimeError("no token")
    assert author.author(ENTRY, AN, SPEC, CFG, runner=boom)[2].startswith("fallback")


def test_a_bad_first_answer_is_retried(monkeypatch):
    monkeypatch.delenv("VYBEX_NO_AUTHOR")
    answers, prompts = ["not json", json.dumps(GOOD)], []
    def flaky(p, c):
        prompts.append(p)
        return answers.pop(0)
    st = author.author(ENTRY, AN, SPEC, CFG, runner=flaky)[2]
    assert st.startswith("claude") and "attempt 2" in st and len(prompts) == 2
    n = [0]
    def always_bad(p, c):
        n[0] += 1
        return "not json"
    assert author.author(ENTRY, AN, SPEC, CFG, runner=always_bad)[2].startswith("fallback") and n[0] == 3


def test_every_brief_is_different_and_bans_real_kinds():
    briefs = {author.variety() for _ in range(12)}
    assert all(len(b.split("виды:")[1].split(".")[0].split(",")) == 6 for b in briefs)
    assert len(briefs) > 6 and all("НЕ используй виды:" in b and "draw" not in b.split("виды:")[1].split(".")[0] for b in briefs)
