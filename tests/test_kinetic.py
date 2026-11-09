from pipeline import render_widgets as rw


def _sc(words, low=(), role="lyric", start=3.0, end=6.0):
    return {"role": role, "text": " ".join(words), "start": start, "end": end, "low_conf": list(low),
            "words": [{"w": w, "s": start + i * .4, "e": start + i * .4 + .3} for i, w in enumerate(words)]}


def test_kinetic_words_in_order_and_skips_doubtful():
    html_, js = rw._kinetic([_sc(["ночь", "уже", "не", "выследит"]), _sc(["сомнительно"], low=[0], start=7, end=9), _sc([], role="outro", start=10, end=12)], 1.9, 12)
    assert html_.count('class="kw"') == 4 and "сомнительно" not in html_  # a doubted line shows nothing
    assert js[0].startswith('tl.fromTo("#kw0_0"') and "#kw1" not in "".join(js)


def test_kinetic_waits_for_hook_and_cuts_long_line():
    long = ["словооооооо"] * 20
    html_, js = rw._kinetic([_sc(long, start=0.5, end=8)], 1.9, 12)
    assert 'data-start="1.9"' in html_ and html_.count('class="kw"') < 20
