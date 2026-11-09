from pipeline import svg_safe


def test_anim_svg_keeps_ids_only_when_asked_and_scopes_them():
    m = '<g id="a"><circle id="b" cx="1" cy="1" r="1"/></g>'
    assert 'id="a"' not in svg_safe.clean(m)
    assert 'id="dr3_b"' in svg_safe.scope(svg_safe.clean(m, ids=True), 3)


def test_tweens_allowlist_and_clamp():
    tw = [{"id": "a", "at": 99, "dur": 99, "from": {"x": -5}, "to": {"x": 9, "evil": 1}, "ease": "bad", "loop": "cycle"},
          {"id": "zz", "to": {"x": 1}},                       # unknown shape: skipped
          {"id": "a", "to": {"opacity": "<script>"}},          # not a number: nothing left to tween
          {"id": "a", "at": 0, "to": {"y": 5}, "o": [10, 20]}]
    out = svg_safe.clean_tweens(tw, {"a"})
    assert len(out) == 2 and "evil" not in str(out) and out[0]["ease"] == "power2.out" and out[0]["loop"] == "cycle" and out[0]["dur"] == 8.0 and out[1]["o"] == [10, 20]


def test_author_keeps_animated_draw_and_drops_dead_tweens():
    from pipeline import author
    svg = '<rect width="800" height="420" fill="#fff"/><g id="a"><circle cx="9" cy="9" r="9"/></g><rect id="b" x="1" y="1" width="9" height="9"/>'
    ok = {"lines": [0], "kind": "draw", "svg": svg, "tw": [{"id": "a", "to": {"x": 5}}, {"id": "b", "to": {"y": 5}, "loop": True}, {"id": "nope", "to": {"x": 1}}]}
    got = author.sanitize_widgets([ok], 1)[0]
    assert 'id="a"' in got["svg"] and len(got["tw"]) == 2
    dead = author.sanitize_widgets([dict(ok, tw=[{"id": "a", "to": {"x": 5}}])], 1)[0]
    assert "tw" not in dead and dead["kind"] == "draw"  # one tween is not an animation: kept as a floating still
    plain = author.sanitize_widgets([{"lines": [0], "kind": "draw", "svg": svg}], 1)[0]
    assert 'id="a"' not in plain["svg"]  # no tw: ids stripped as before
