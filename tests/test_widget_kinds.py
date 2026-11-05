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
