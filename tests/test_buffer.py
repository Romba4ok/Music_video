import json
from datetime import datetime, timedelta, timezone

import pytest

from pipeline import buffer_publisher as bp

CFG = {"buffer": {"mode": "draft", "channel_id": "CH1", "keep_days": 7, "max_mb": 100}}
ENV = {}


class FakeBuf:
    def __init__(self, fail=None):
        self.calls, self.fail = [], fail

    def create_post(self, channel, text, url, mode):
        if self.fail:
            raise bp.BufferError(self.fail)
        self.calls.append((channel, text, url, mode))
        return f"post{len(self.calls)}"

    def tiktok_channels(self):
        return [{"id": "CH9", "name": "vybex.mp44", "org": "O", "paused": False}]


class FakeStore:
    def __init__(self):
        self.up, self.deleted = [], []

    def upload(self, path, pid):
        self.up.append(pid)
        return f"https://cdn.example/{pid}.mp4"

    def delete(self, pid):
        self.deleted.append(pid)
        return True


@pytest.fixture(autouse=True)
def url_ok(monkeypatch):
    monkeypatch.setattr(bp, "check_url", lambda url, size, get=None: None)


def make_out(tmp_path, n=2, same=False):
    out = tmp_path / "out"
    (out / "ready").mkdir(parents=True)
    songs = []
    for i in range(1, n + 1):
        name = f"{i} Баста - Песня {i}"
        (out / "ready" / f"{name}.mp4").write_bytes(b"video" + (b"" if same else str(i).encode()))
        (out / "ready" / f"{name} caption.txt").write_text("Подпись. Сделано с ИИ\n#a #b\n\nВключите в TikTok метку «Создано ИИ».", encoding="utf-8")
        songs.append({"song": name, "ready": name, "stages": {"render": "ok"}})
    songs.append({"song": "failed", "stages": {"render": "FAIL"}})  # never sent
    (out / "report.json").write_text(json.dumps({"songs": songs}), encoding="utf-8")
    return out


def report(out):
    return json.loads((out / "report.json").read_text(encoding="utf-8"))


def test_draft_is_default_and_typo_never_publishes():
    assert bp.mode_of({}, {}) == "off"
    assert bp.mode_of(CFG, {}) == "draft"
    assert bp.mode_of(CFG, {"VYBEX_BUFFER": "qeue"}) == "off"
    assert bp.mode_of(CFG, {"VYBEX_BUFFER": "QUEUE"}) == "queue"


def test_caption_drops_ai_reminder_and_is_cut():
    assert "Включите" not in bp.caption_for("Привет\n#a\n\nВключите в TikTok метку")
    assert len(bp.caption_for("x" * 5000)) == 2200


def test_sends_only_rendered_videos_in_draft(tmp_path):
    out, buf, st = make_out(tmp_path), FakeBuf(), FakeStore()
    res = bp.publish_dir(out, CFG, tmp_path / "s.json", ENV, buf, st)
    assert [r["state"] for r in res] == ["draft", "draft"]
    assert [c[3] for c in buf.calls] == ["draft", "draft"] and buf.calls[0][0] == "CH1"
    assert report(out)["songs"][0]["buffer"]["post_id"] == "post1"
    assert report(out)["buffer"]["state"] == "draft"
    assert (out / "ready" / "1 Баста - Песня 1.mp4").exists()


def test_same_mp4_is_not_sent_twice_even_after_restart(tmp_path):
    out, st = make_out(tmp_path, n=1), FakeStore()
    bp.publish_dir(out, CFG, tmp_path / "s.json", ENV, FakeBuf(), st)
    buf2 = FakeBuf()
    r = bp.publish_dir(out, CFG, tmp_path / "s.json", ENV, buf2, st)  # state file reloaded from disk = new Actions run
    assert r[0]["state"] == "duplicate" and not buf2.calls and len(st.up) == 1


def test_identical_content_under_two_names_is_one_post(tmp_path):
    out, buf = make_out(tmp_path, same=True), FakeBuf()
    r = bp.publish_dir(out, CFG, tmp_path / "s.json", ENV, buf, FakeStore())
    assert [x["state"] for x in r] == ["draft", "duplicate"] and len(buf.calls) == 1


def test_draft_can_later_be_sent_for_real_but_queue_never_twice(tmp_path):
    out, buf = make_out(tmp_path, n=1), FakeBuf()
    bp.publish_dir(out, CFG, tmp_path / "s.json", ENV, buf, FakeStore())
    q = dict(ENV, VYBEX_BUFFER="queue")
    assert bp.publish_dir(out, CFG, tmp_path / "s.json", q, buf, FakeStore())[0]["state"] == "queued"
    assert bp.publish_dir(out, CFG, tmp_path / "s.json", q, buf, FakeStore())[0]["state"] == "duplicate"


def test_error_keeps_mp4_and_is_recorded_and_can_be_retried(tmp_path):
    out = make_out(tmp_path, n=1)
    r = bp.publish_dir(out, CFG, tmp_path / "s.json", ENV, FakeBuf(fail="Failed to fetch"), FakeStore())
    assert r[0]["state"] == "error" and "Failed to fetch" in r[0]["detail"]
    assert (out / "ready" / "1 Баста - Песня 1.mp4").exists()
    again = FakeBuf()
    assert bp.publish_dir(out, CFG, tmp_path / "s.json", ENV, again, FakeStore())[0]["state"] == "draft"  # no post_id was saved -> not a duplicate


def test_off_and_missing_secrets_do_nothing(tmp_path):
    out = make_out(tmp_path)
    assert bp.publish_dir(out, CFG, tmp_path / "s.json", {"VYBEX_BUFFER": "off"}) == []
    assert report(out)["buffer"]["state"] == "off"
    assert bp.publish_dir(out, CFG, tmp_path / "s.json", {}) == []
    assert "missing secrets" in report(out)["buffer"]["detail"] and "BUFFER_API_KEY" in report(out)["buffer"]["detail"]


def test_non_mp4_and_huge_files_are_refused(tmp_path):
    f = tmp_path / "a.mov"
    f.write_bytes(b"x")
    with pytest.raises(bp.BufferError):
        bp.check_file(f, {})
    g = tmp_path / "b.mp4"
    g.write_bytes(b"x" * 2_000_000)
    with pytest.raises(bp.BufferError):
        bp.check_file(g, {"max_mb": 1})


def test_cleanup_deletes_only_old_hosted_files():
    now = datetime(2026, 11, 20, tzinfo=timezone.utc)
    state = {"a": {"hosted": True, "public_id": "old", "uploaded_at": (now - timedelta(days=8)).isoformat()},
             "b": {"hosted": True, "public_id": "new", "uploaded_at": (now - timedelta(days=2)).isoformat()},
             "c": {"hosted": False, "public_id": "gone", "uploaded_at": (now - timedelta(days=30)).isoformat()}}
    st = FakeStore()
    assert bp.cleanup(state, st, 7, now) == 1 and st.deleted == ["old"] and state["a"]["hosted"] is False and state["b"]["hosted"] is True


def test_create_post_payload_has_ai_label_and_draft_flag():
    sent = {}

    class R:
        status_code = 200
        def json(self): return {"data": {"createPost": {"post": {"id": "P1"}}}}

    def post(url, json=None, **kw):
        sent.update(json)
        return R()

    assert bp.Buffer("k", post).create_post("CH", "t", "https://x/v.mp4", "draft") == "P1"
    i = sent["variables"]["input"]
    assert i["saveToDraft"] is True and i["schedulingType"] == "automatic" and i["mode"] == "addToQueue"
    assert i["aiAssisted"] is True and i["metadata"]["tiktok"]["isAiGenerated"] is True
    assert i["assets"][0]["video"]["url"] == "https://x/v.mp4"
    sent.clear()
    bp.Buffer("k", post).create_post("CH", "t", "https://x/v.mp4", "queue")
    assert "saveToDraft" not in sent["variables"]["input"]


def test_mutation_error_message_is_raised():
    class R:
        status_code = 200
        def json(self): return {"data": {"createPost": {"message": "Failed to fetch video"}}}

    with pytest.raises(bp.BufferError, match="Failed to fetch"):
        bp.Buffer("k", lambda *a, **k: R()).create_post("CH", "t", "https://x/v.mp4", "queue")


def test_check_url_rules():
    class R:
        def __init__(self, code=200, ct="video/mp4", n="5"):
            self.status_code, self.headers = code, {"content-type": ct, "content-length": n}

    import importlib
    importlib.reload(bp)  # undo the autouse stub
    bp.check_url("https://x/v.mp4", 5, lambda *a, **k: R())
    for bad, size in ((R(302), 5), (R(ct="text/html"), 5), (R(n="9"), 5)):
        with pytest.raises(bp.BufferError):
            bp.check_url("https://x/v.mp4", size, lambda *a, **k: bad)
    with pytest.raises(bp.BufferError):
        bp.check_url("http://x/v.mp4", 5, lambda *a, **k: R())


def test_setup_writes_channel_id_into_config(tmp_path):
    p = tmp_path / "config.json"
    p.write_text('{"buffer": {"mode": "draft", "channel_id": "", "keep_days": 7}}', encoding="utf-8")
    bp.setup(buf=FakeBuf(), config_path=p)
    assert json.loads(p.read_text())["buffer"]["channel_id"] == "CH9"
