import pytest

from pipeline import render_widgets as rw
from pipeline import widget_kinds as wk


@pytest.mark.parametrize("kind", wk.NEW_KINDS)
def test_new_kind_renders(kind):
    h, js = wk.BUILD[kind]({}, 3, 10.0, 3.0, lambda f: round(10 + f * 3, 3))
    assert h.startswith("<") and js and not any("None" in x or "undefined" in x for x in js + [h])
    assert kind in rw.KINDS


def test_versus_and_auto_rules():
    h, js = rw._body("versus", {"art": "pulse", "art2": "coins", "label": "Любовь", "label2": "Бабки"}, 2, 5.0, 3.0, "x")
    assert "Бабки" in h and js
    assert rw._auto("Ты ему сперва дала, потом полюбила", "")["kind"] == "pulse"
    assert rw._auto("Ты ему сперва дала, потом полюбила", "pulse") == {}


def test_quote_row_cleans_vocalise_and_hides_doubtful_lines():
    from pipeline import render_widgets as rw
    assert rw._quote({"text": "У -у -у, кругу лягу У -у -у, три -один -два"}) == "кругу лягу три один два"
    assert rw._quote({"text": "Бензин был лепнет к моим рукам", "low_conf": [2]}) == ""  # whisper doubted a word: no quote
    assert len(rw._quote({"text": "Мы начинали с самого низа Запомни нас такими"})) <= 38


def test_drawn_card_shows_big_badge_and_chips_and_author_keeps_them():
    from pipeline import author, render_widgets as rw
    svg = '<rect width="800" height="420" fill="#eef"/><circle cx="400" cy="210" r="80" fill="#f49"/>'
    h, j = rw._body("draw", {"kind": "draw", "frames": [svg], "big": "03:32", "chips": ["никому не говорим", "пока не поздно"]}, 0, 0.0, 3.0, "t")
    assert 'class="dbig">03:32' in h and h.count("<span>") == 2 and any("#dc0" in x for x in j)
    w = author.sanitize_widgets([{"lines": [0], "kind": "draw", "frames": [svg], "chips": ["а", "б", "в", " "], "big": "×2"}], 1)
    assert w[0]["chips"] == ["а", "б"] and w[0]["big"] == "×2"
