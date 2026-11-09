import json
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest
import requests

from pipeline import buffer_publisher as bp

ALM = ZoneInfo("Asia/Almaty")
NOW = datetime(2026, 11, 20, 5, 0, tzinfo=timezone.utc)  # 10:00 in Almaty
CFG = {"buffer": {"mode": "draft", "channel_id": "CH1", "keep_days": 7, "max_mb": 100}}
ENV = {"VYBEX_OWNER_DECLARES_RIGHTS": "1", "VYBEX_TIMEZONE": "Asia/Almaty"}
QUEUE = dict(ENV, VYBEX_BUFFER="queue")
ORIG_CHECK_URL = bp.check_url


class FakeBuf:
    def __init__(self, scheduled=(), fail=None, statuses=None, paused=False):
        self.calls, self.fail, self.sched, self.statuses, self.paused = [], fail, list(scheduled), statuses or {}, paused

    def tiktok_channels(self):
        return [{"id": "CH1", "name": "vybex.mp44", "org": "O", "paused": self.paused, "disconnected": False, "locked": False,
                 "timezone": "Europe/London"}]

    def scheduled(self, org, channel):
        return self.sched

    def post_status(self, post_id):
        s = self.statuses.get(post_id, {"status": "scheduled"})
        if isinstance(s, Exception):
            raise s
        return s

    def create_post(self, channel, text, url, mode, due=None, notify=False):
        if self.fail:
            raise self.fail
        self.calls.append({"text": text, "url": url, "mode": mode, "due": due, "notify": notify})
        return f"post{len(self.calls)}"


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
def stubs(monkeypatch):
    monkeypatch.setattr(bp, "check_url", lambda url, size, get=None: None)
    monkeypatch.setattr(bp, "check_media", lambda p, audio, b: {"duration": 30.0, "audio": audio})


def make_out(tmp_path, n=2, mode="auto", sources=None):
    out = tmp_path / "out"
    (out / "ready").mkdir(parents=True)
    songs = []
    for i in range(1, n + 1):
        name = f"{i} Баста - Песня {i}"
        (out / "ready" / f"{name}.mp4").write_bytes(b"video" + str(i).encode())
        (out / "ready" / f"{name} caption.txt").write_text(f"Подпись {i}. Сделано с ИИ\n#a #b\n\nВключите в TikTok метку «Создано ИИ».", encoding="utf-8")
        songs.append({"song": name, "ready": name, "stages": {"render": "ok"},
                      "sources": sources or [{"source": "local", "state": "ok", "detail": "x.mp3"}]})
    songs.append({"song": "failed", "stages": {"render": "FAIL"}})  # never sent
    (out / "report.json").write_text(json.dumps({"mode": mode, "songs": songs}), encoding="utf-8")
    return out


def report(out):
    return json.loads((out / "report.json").read_text(encoding="utf-8"))


def run(out, tmp_path, env=ENV, buf=None, store=None, now=NOW, cfg=CFG):
    return bp.publish_dir(out, cfg, tmp_path / "s.json", env, buf or FakeBuf(), store or FakeStore(), now)


def local(dt):
    return dt.astimezone(ALM).strftime("%Y-%m-%d %H:%M")


# ---------- modes, caption ----------

def test_draft_is_default_and_typo_never_publishes():
    assert bp.mode_of({}, {}) == "off"
    assert bp.mode_of(CFG, {}) == "draft"
    assert bp.mode_of(CFG, {"VYBEX_BUFFER": "qeue"}) == "off"
    assert bp.mode_of(CFG, {"VYBEX_BUFFER": "QUEUE"}) == "queue"
    assert bp.mode_of(CFG, {"VYBEX_BUFFER": "plan"}) == "plan"


def test_caption_drops_ai_reminder_and_is_cut():
    assert "Включите" not in bp.caption_for("Привет\n#a\n\nВключите в TikTok метку")
    assert len(bp.caption_for("x" * 5000)) == 2200


# ---------- schedule ----------

def test_three_videos_take_the_three_daily_slots():
    tz, hm = bp.slot_config({}, ENV)
    got = bp.free_slots(4, [], tz, hm, NOW)
    assert [local(d) for d in got] == ["2026-11-20 12:00", "2026-11-20 17:00", "2026-11-20 21:00", "2026-11-21 12:00"]


def test_taken_slots_and_full_days_are_skipped():
    tz, hm = bp.slot_config({}, ENV)
    at = lambda d, h: datetime(2026, 11, d, h, 0, tzinfo=ALM).astimezone(timezone.utc)
    assert local(bp.free_slots(1, [at(20, 12)], tz, hm, NOW)[0]) == "2026-11-20 17:00"
    full = [at(20, 12), at(20, 17), at(20, 21)]
    assert local(bp.free_slots(1, full, tz, hm, NOW)[0]) == "2026-11-21 12:00"
    manual = [at(20, 14), at(20, 15), at(20, 16)]  # three posts at odd times also fill the day (3 per day)
    assert local(bp.free_slots(1, manual, tz, hm, NOW)[0]) == "2026-11-21 12:00"


def test_past_slots_and_near_future_are_not_used():
    tz, hm = bp.slot_config({}, ENV)
    late = datetime(2026, 11, 20, 11, 50, tzinfo=timezone.utc)  # 16:50 Almaty: 17:00 is inside the 20 min margin
    assert local(bp.free_slots(1, [], tz, hm, late)[0]) == "2026-11-20 21:00"


def test_posts_per_day_variable_limits_slots():
    tz, hm = bp.slot_config({}, dict(ENV, VYBEX_POSTS_PER_DAY="2"))
    assert [local(d) for d in bp.free_slots(3, [], tz, hm, NOW)] == ["2026-11-20 12:00", "2026-11-20 17:00", "2026-11-21 12:00"]
    with pytest.raises(bp.BufferError):
        bp.slot_config({}, dict(ENV, VYBEX_POSTS_PER_DAY="many"))


def test_queue_spreads_videos_over_slots_and_next_days(tmp_path):
    out, buf = make_out(tmp_path, n=4), FakeBuf()
    res = run(out, tmp_path, QUEUE, buf)
    assert [r["state"] for r in res] == ["scheduled"] * 4
    assert [local(c["due"]) for c in buf.calls] == ["2026-11-20 12:00", "2026-11-20 17:00", "2026-11-20 21:00", "2026-11-21 12:00"]
    assert all(c["mode"] == "queue" and not c["notify"] for c in buf.calls)
    assert report(out)["buffer"]["state"] == "queue" and not bp.failed(out)


def test_queue_goes_after_what_is_already_scheduled(tmp_path):
    old = [{"id": f"o{i}", "text": f"old {i}", "dueAt": datetime(2026, 11, 20, h, 0, tzinfo=ALM).astimezone(timezone.utc).isoformat()}
           for i, h in enumerate((12, 17, 21))]
    out, buf = make_out(tmp_path, n=1), FakeBuf(scheduled=old)
    run(out, tmp_path, QUEUE, buf)
    assert local(buf.calls[0]["due"]) == "2026-11-21 12:00"


def test_plan_changes_nothing(tmp_path):
    out, buf, st = make_out(tmp_path, n=2), FakeBuf(), FakeStore()
    res = run(out, tmp_path, dict(QUEUE, VYBEX_BUFFER="plan"), buf, st)
    assert [r["state"] for r in res] == ["plan", "plan"] and res[0]["due"].startswith("2026-11-20T12:00")
    assert not buf.calls and not st.up and not (tmp_path / "s.json").exists()


# ---------- draft / notification ----------

def test_draft_has_no_time_and_does_not_look_at_the_queue(tmp_path):
    out, buf = make_out(tmp_path), FakeBuf()
    res = run(out, tmp_path, ENV, buf)
    assert [r["state"] for r in res] == ["draft", "draft"]
    assert all(c["mode"] == "draft" and c["due"] is None for c in buf.calls)
    assert (out / "ready" / "1 Баста - Песня 1.mp4").exists()


def test_silent_video_becomes_a_notification_not_auto_publishing(tmp_path):
    out, buf = make_out(tmp_path, n=1, mode="tiktok"), FakeBuf()
    res = run(out, tmp_path, QUEUE, buf)
    assert res[0]["state"] == "notify" and buf.calls[0]["notify"] is True


# ---------- rights, dedup, errors ----------

def test_rights_gate(tmp_path):
    out = make_out(tmp_path, n=1)
    r = run(out, tmp_path, {"VYBEX_BUFFER": "queue"}, FakeBuf())  # local file without the owner's declaration
    assert r[0]["state"] == "refused" and "declaration" in r[0]["detail"]
    lic = make_out(tmp_path / "b", n=1, sources=[{"source": "jamendo", "state": "ok", "detail": ""}])
    assert run(lic, tmp_path / "b", {"VYBEX_BUFFER": "queue"}, FakeBuf())[0]["state"] == "scheduled"
    none = make_out(tmp_path / "c", n=1, sources=[{"source": "local", "state": "empty"}])
    assert run(none, tmp_path / "c", QUEUE, FakeBuf())[0]["state"] == "refused"


def test_same_mp4_is_never_sent_twice_in_any_mode(tmp_path):
    out, st = make_out(tmp_path, n=1), FakeStore()
    run(out, tmp_path, ENV, FakeBuf(), st)  # draft
    buf2 = FakeBuf()
    r = run(out, tmp_path, QUEUE, buf2, st)  # now queue: the old test draft is NOT sent for real
    assert r[0]["state"] == "duplicate" and not buf2.calls and len(st.up) == 1


def test_error_keeps_mp4_turns_the_step_red_and_can_be_retried(tmp_path):
    out = make_out(tmp_path, n=1)
    r = run(out, tmp_path, QUEUE, FakeBuf(fail=bp.BufferError("Failed to fetch")))
    assert r[0]["state"] == "error" and "Failed to fetch" in r[0]["detail"]
    assert (out / "ready" / "1 Баста - Песня 1.mp4").exists() and bp.failed(out)
    assert run(out, tmp_path, QUEUE, FakeBuf())[0]["state"] == "scheduled"


def test_ambiguous_failure_adopts_the_post_if_it_reached_buffer(tmp_path):
    out = make_out(tmp_path, n=1)
    buf = FakeBuf(fail=bp.Ambiguous("HTTP 500"))
    # the first look (slot search) sees nothing; the look after the unclear failure sees the post that "did go through"
    cap = bp.caption_for((out / "ready" / "1 Баста - Песня 1 caption.txt").read_text(encoding="utf-8"))
    answers = iter([[], [{"id": "P9", "text": cap, "dueAt": NOW.isoformat()}]])
    buf.scheduled = lambda o, c: next(answers)
    r = run(out, tmp_path, QUEUE, buf)
    assert r[0]["state"] == "scheduled" and r[0]["post_id"] == "P9"


def test_ambiguous_failure_without_trace_is_an_error(tmp_path):
    out = make_out(tmp_path, n=1)
    r = run(out, tmp_path, QUEUE, FakeBuf(fail=bp.Ambiguous("HTTP 500")))
    assert r[0]["state"] == "error"


def test_post_already_in_buffer_queue_is_not_created_again(tmp_path):
    out = make_out(tmp_path, n=1)
    cap = bp.caption_for((out / "ready" / "1 Баста - Песня 1 caption.txt").read_text(encoding="utf-8"))
    buf = FakeBuf(scheduled=[{"id": "P7", "text": cap, "dueAt": (NOW + timedelta(days=1)).isoformat()}])
    r = run(out, tmp_path, QUEUE, buf)
    assert r[0]["state"] == "duplicate" and not buf.calls


def test_off_and_missing_secrets(tmp_path):
    out = make_out(tmp_path)
    assert bp.publish_dir(out, CFG, tmp_path / "s.json", {"VYBEX_BUFFER": "off"}) == []
    assert report(out)["buffer"]["state"] == "off" and not bp.failed(out)
    assert bp.publish_dir(out, CFG, tmp_path / "s.json", {"VYBEX_BUFFER": "queue"}) == []
    b = report(out)["buffer"]
    assert b["state"] == "skipped" and "BUFFER_API_KEY" in b["detail"] and bp.failed(out)  # not hidden behind a green step


def test_paused_queue_and_unknown_channel_are_errors(tmp_path):
    out = make_out(tmp_path, n=1)
    assert run(out, tmp_path, QUEUE, FakeBuf(paused=True)) == []
    assert report(out)["buffer"]["state"] == "error" and "paused" in report(out)["buffer"]["detail"]
    out2 = make_out(tmp_path / "b", n=1)
    bp.publish_dir(out2, {"buffer": {"channel_id": "NOPE"}}, tmp_path / "b" / "s.json", QUEUE, FakeBuf(), FakeStore(), NOW)
    assert report(out2)["buffer"]["state"] == "error"


# ---------- real status ----------

def test_statuses_are_checked_next_run_and_errors_surface(tmp_path):
    out = make_out(tmp_path, n=2)
    run(out, tmp_path, QUEUE, FakeBuf())
    state = bp.load_state(tmp_path / "s.json")
    assert {e["status"] for e in state.values()} == {"scheduled"}
    pids = [e["post_id"] for e in state.values()]
    buf = FakeBuf(statuses={pids[0]: {"status": "sent"}, pids[1]: {"status": "error", "error": {"message": "TikTok rejected"}}})
    out2 = make_out(tmp_path / "next", n=0)  # next day's run, same state file
    bp.publish_dir(out2, CFG, tmp_path / "s.json", QUEUE, buf, FakeStore(), NOW + timedelta(days=1))
    assert any("TikTok rejected" in p for p in report(out2)["buffer"]["problems"]) and bp.failed(out2)
    assert {e["status"] for e in bp.load_state(tmp_path / "s.json").values()} == {"sent", "error"}


def test_overdue_scheduled_post_is_a_problem():
    state = {"a": {"mode": "queue", "post_id": "P", "status": "scheduled", "file": "f.mp4", "due": (NOW - timedelta(hours=3)).isoformat()}}
    assert "still 'scheduled'" in bp.refresh_statuses(state, FakeBuf(), NOW)[0]
    assert bp.refresh_statuses({"a": dict(state["a"], due=NOW.isoformat())}, FakeBuf(), NOW) == []
    unknown = {"a": dict(state["a"])}
    assert bp.refresh_statuses(unknown, FakeBuf(statuses={"P": bp.BufferError("boom")}), NOW) == [] and "status_note" in unknown["a"]


def test_cleanup_waits_for_the_post_time_and_keeps_drafts():
    old = (NOW - timedelta(days=10)).isoformat()
    state = {"gone": {"hosted": True, "mode": "queue", "public_id": "gone", "uploaded_at": old, "due": (NOW - timedelta(days=3)).isoformat()},
             "future": {"hosted": True, "mode": "queue", "public_id": "future", "uploaded_at": old, "due": (NOW + timedelta(days=2)).isoformat()},
             "fresh": {"hosted": True, "mode": "queue", "public_id": "fresh", "uploaded_at": (NOW - timedelta(days=1)).isoformat(), "due": None},
             "draft": {"hosted": True, "mode": "draft", "public_id": "draft", "uploaded_at": old, "due": None}}
    st = FakeStore()
    assert bp.cleanup(state, st, 7, NOW) == 1 and st.deleted == ["gone"]


# ---------- API client ----------

class R:
    def __init__(self, code=200, data=None):
        self.status_code, self._d = code, data

    def json(self):
        return self._d


def client(seq):
    calls = []

    def post(url, json=None, **kw):
        calls.append(json)
        x = next(seq)
        if isinstance(x, Exception):
            raise x
        return x

    return bp.Buffer("k", post, sleep=lambda s: None), calls


def test_reads_retry_on_gateway_errors_and_network_drops():
    ok = R(200, {"data": {"x": 1}})
    b, calls = client(iter([R(502), R(429), requests.ConnectionError("x"), ok]))
    assert b.gql("query { x }") == {"x": 1} and len(calls) == 4
    b, calls = client(iter([R(500), R(200, {"data": {"x": 2}})]))
    assert b.gql("query { x }") == {"x": 2}
    b, _ = client(iter([R(502)] * 4))
    with pytest.raises(bp.BufferError):
        b.gql("query { x }")


def test_create_post_is_not_blindly_repeated_after_an_unclear_failure():
    b, calls = client(iter([requests.ReadTimeout("slow"), R(200, {"data": {"createPost": {"post": {"id": "P"}}}})]))
    with pytest.raises(bp.Ambiguous):
        b.create_post("CH", "t", "https://x/v.mp4", "queue")
    assert len(calls) == 1
    b, calls = client(iter([R(500)]))
    with pytest.raises(bp.Ambiguous):
        b.create_post("CH", "t", "https://x/v.mp4", "queue")
    b, calls = client(iter([R(503), R(200, {"data": {"createPost": {"post": {"id": "P"}}}})]))  # gateway error = not processed
    assert b.create_post("CH", "t", "https://x/v.mp4", "queue") == "P" and len(calls) == 2


def test_create_post_payloads():
    ok = R(200, {"data": {"createPost": {"post": {"id": "P1"}}}})
    b, calls = client(iter([ok, ok, ok]))
    due = datetime(2026, 11, 20, 7, 0, tzinfo=timezone.utc)
    b.create_post("CH", "t", "https://x/v.mp4", "queue", due)
    q = calls[-1]["variables"]["input"]
    assert q["mode"] == "customScheduled" and q["dueAt"] == "2026-11-20T07:00:00.000Z" and q["schedulingType"] == "automatic"
    assert q["aiAssisted"] is True and q["metadata"]["tiktok"]["isAiGenerated"] is True and "saveToDraft" not in q
    b.create_post("CH", "t", "https://x/v.mp4", "queue", due, notify=True)
    assert calls[-1]["variables"]["input"]["schedulingType"] == "notification"
    b.create_post("CH", "t", "https://x/v.mp4", "draft")
    d = calls[-1]["variables"]["input"]
    assert d["saveToDraft"] is True and d["mode"] == "addToQueue" and "dueAt" not in d


def test_mutation_error_message_is_raised():
    b, _ = client(iter([R(200, {"data": {"createPost": {"message": "Failed to fetch video"}}})]))
    with pytest.raises(bp.BufferError, match="Failed to fetch"):
        b.create_post("CH", "t", "https://x/v.mp4", "queue")


def test_scheduled_reads_every_page():
    pages = iter([R(200, {"data": {"posts": {"edges": [{"node": {"id": "a", "text": "t", "dueAt": "x"}}], "pageInfo": {"hasNextPage": True, "endCursor": "c"}}}}),
                  R(200, {"data": {"posts": {"edges": [{"node": {"id": "b", "text": "t", "dueAt": "y"}}], "pageInfo": {"hasNextPage": False, "endCursor": None}}}})])
    b, calls = client(pages)
    assert [p["id"] for p in b.scheduled("O", "CH")] == ["a", "b"] and calls[1]["variables"]["after"] == "c"
    assert "scheduled" in calls[0]["query"] and "draft" not in calls[0]["query"]  # drafts are never listed, so never touched


# ---------- media and url checks ----------

def info(codec="h264", w=1080, h=1920, audio=True, dur="30.0"):
    st = [{"codec_type": "video", "codec_name": codec, "width": w, "height": h}] + ([{"codec_type": "audio"}] if audio else [])
    return {"streams": st, "format": {"duration": dur}}


def media(monkeypatch, tmp_path, i, audio=True, decode_err=""):
    monkeypatch.undo()  # drop the autouse stub of check_media
    import pipeline.qa as qa
    monkeypatch.setattr(qa, "probe", lambda p: i)
    monkeypatch.setattr(bp.subprocess, "run", lambda *a, **k: SimpleNamespace(returncode=1 if decode_err else 0, stderr=decode_err))
    f = tmp_path / "v.mp4"
    f.write_bytes(b"x")
    return bp.check_media(f, audio, {})


def test_check_media(monkeypatch, tmp_path):
    assert media(monkeypatch, tmp_path, info(), True) == {"duration": 30.0, "audio": True}
    assert media(monkeypatch, tmp_path, info(audio=False), False)["audio"] is False  # silent TikTok-sound video is fine
    for bad, why in ((info(codec="hevc"), "h264"), (info(w=720, h=1280), "1080x1920"), (info(audio=False), "audio"), (info(dur="1.0"), "duration")):
        with pytest.raises(bp.BufferError, match=why):
            media(monkeypatch, tmp_path, bad, True)
    with pytest.raises(bp.BufferError, match="decode"):
        media(monkeypatch, tmp_path, info(), True, decode_err="moov atom not found")


def test_non_mp4_and_huge_files_are_refused(tmp_path):
    f = tmp_path / "a.mov"
    f.write_bytes(b"x")
    with pytest.raises(bp.BufferError):
        bp.check_file(f, {})
    g = tmp_path / "b.mp4"
    g.write_bytes(b"x" * 2_000_000)
    with pytest.raises(bp.BufferError):
        bp.check_file(g, {"max_mb": 1})


def test_check_url_rules():
    class H:
        def __init__(self, code=200, ct="video/mp4", n="5"):
            self.status_code, self.headers = code, {"content-type": ct, "content-length": n}

    ORIG_CHECK_URL("https://x/v.mp4", 5, lambda *a, **k: H())
    for bad in (H(302), H(ct="text/html"), H(n="9")):
        with pytest.raises(bp.BufferError):
            ORIG_CHECK_URL("https://x/v.mp4", 5, lambda *a, **k: bad)
    with pytest.raises(bp.BufferError):
        ORIG_CHECK_URL("http://x/v.mp4", 5, lambda *a, **k: H())


def test_setup_and_check(tmp_path):
    p = tmp_path / "config.json"
    p.write_text('{"buffer": {"mode": "draft", "channel_id": "", "keep_days": 7}}', encoding="utf-8")
    bp.setup(buf=FakeBuf(), config_path=p)
    assert json.loads(p.read_text())["buffer"]["channel_id"] == "CH1"
    c = bp.check(CFG, ENV, FakeBuf(), NOW)
    assert c["scheduled"] == 0 and c["next_free"][0].startswith("2026-11-20T12:00") and c["slots_timezone"] == "Asia/Almaty"


def test_summary_lines(tmp_path):
    out = tmp_path / "o"
    out.mkdir()
    (out / "report.json").write_text(json.dumps({"songs": [{"song": "A - B", "buffer": {"state": "scheduled", "due": "2026-11-20T12:00:00+05:00"}}, {"song": "C"}],
                                                 "buffer": {"state": "queue", "slots": ["12:00", "17:00"], "timezone": "Asia/Almaty", "problems": ["f.mp4: boom"]}}), encoding="utf-8")
    assert bp.summary(out) == ["- buffer: queue  slots=12:00,17:00 Asia/Almaty", "  - PROBLEM: f.mp4: boom", "  - A - B: scheduled 2026-11-20T12:00:00+05:00"]


# ---------- Drive cleanup after the post was SENT ----------

def _entry(**kw):
    e = {"mode": "queue", "post_id": "P", "status": "sent", "file": "1 Баста - Песня 1.mp4", "hosted": False,
         "drive": {"dir": "ready/2026-11-19", "files": ["1 A.mp4", "1 A caption.txt", "1 A sync.txt"], "song": "A - T.mp3"}}
    e.update(kw)
    return e


class Drive:
    ALL = ["ready/2026-11-19/1 A.mp4", "ready/2026-11-19/1 A caption.txt", "ready/2026-11-19/1 A sync.txt", "done/A - T.mp3"]

    def __init__(self, fail=(), left=(), present=None, broken=False):
        self.removed, self.purged, self.fail, self.left = [], [], set(fail), list(left)
        self.present, self.broken = set(self.ALL if present is None else present), broken

    def remove(self, p):
        self.removed.append(p)
        if p in self.fail:
            return False
        self.present.discard(p)
        return True

    def ls(self, d):
        if self.broken:
            return None
        return [p.rpartition("/")[2] for p in self.present if p.rpartition("/")[0] == d] + self.left

    def purge(self, d):
        self.purged.append(d)
        return True


def test_publish_records_exactly_which_drive_files_belong_to_the_post(tmp_path):
    out = make_out(tmp_path, n=1)
    run(out, tmp_path, QUEUE)
    e = next(iter(bp.load_state(tmp_path / "s.json").values()))
    assert e["drive"]["dir"] == "ready/out" and e["drive"]["files"] == ["1 Баста - Песня 1.mp4", "1 Баста - Песня 1 caption.txt", "1 Баста - Песня 1 sync.txt"]


def test_sent_post_deletes_its_drive_files_and_the_empty_day_folder():
    d, st = Drive(), {"a": _entry()}
    n, problems = bp.drive_cleanup(st, {}, NOW, d.remove, d.ls, d.purge)
    assert n == 1 and problems == []
    assert d.removed == ["ready/2026-11-19/1 A.mp4", "ready/2026-11-19/1 A caption.txt", "ready/2026-11-19/1 A sync.txt"]  # not the song in done/
    assert d.purged == ["ready/2026-11-19"] and st["a"]["drive_deleted"]
    assert bp.drive_cleanup(st, {}, NOW, d.remove, d.ls, d.purge) == (0, [])  # once only


def test_day_folder_stays_while_another_video_is_still_in_it():
    d = Drive(left=["2 B.mp4", "report.json"])
    bp.drive_cleanup({"a": _entry()}, {}, NOW, d.remove, d.ls, d.purge)
    assert d.purged == []


def test_nothing_is_deleted_for_drafts_scheduled_notifications_or_old_entries():
    d = Drive()
    st = {"draft": _entry(mode="draft", status="draft"), "sched": _entry(status="scheduled"), "err": _entry(status="error"),
          "hand": _entry(notification=True), "old": {"mode": "queue", "post_id": "X", "status": "sent"}}
    assert bp.drive_cleanup(st, {}, NOW, d.remove, d.ls, d.purge) == (0, []) and d.removed == [] and d.purged == []


def test_source_song_is_removed_only_when_asked():
    d = Drive()
    bp.drive_cleanup({"a": _entry()}, {"delete_song_after_sent": True}, NOW, d.remove, d.ls, d.purge)
    assert d.removed[-1] == "done/A - T.mp3"


def test_failed_delete_is_reported_kept_and_retried():
    d, st = Drive(fail={"ready/2026-11-19/1 A caption.txt"}), {"a": _entry()}
    n, problems = bp.drive_cleanup(st, {}, NOW, d.remove, d.ls, d.purge)
    assert n == 0 and "caption.txt" in problems[0] and not st["a"].get("drive_deleted") and d.purged == []
    d2 = Drive()
    assert bp.drive_cleanup(st, {}, NOW, d2.remove, d2.ls, d2.purge)[0] == 1 and "drive_note" not in st["a"]


def test_files_already_gone_are_not_a_problem_but_a_drive_error_is():
    d = Drive(present=["ready/2026-11-19/1 A.mp4"])  # caption and sync.txt are not there (sync.txt never exists for a video with sound)
    st = {"a": _entry()}
    assert bp.drive_cleanup(st, {}, NOW, d.remove, d.ls, d.purge) == (1, []) and d.removed == ["ready/2026-11-19/1 A.mp4"]
    broken = Drive(broken=True)
    st2 = {"a": _entry()}
    n, problems = bp.drive_cleanup(st2, {}, NOW, broken.remove, broken.ls, broken.purge)
    assert n == 0 and problems and not st2["a"].get("drive_deleted") and broken.removed == []


def test_hosted_copy_goes_as_soon_as_the_post_is_sent_not_after_keep_days():
    recent = (NOW - timedelta(hours=2)).isoformat()
    st = {"s": {"hosted": True, "mode": "queue", "public_id": "s", "uploaded_at": recent, "due": recent, "status": "sent"},
          "n": {"hosted": True, "mode": "queue", "public_id": "n", "uploaded_at": recent, "due": recent, "status": "sent", "notification": True},
          "q": {"hosted": True, "mode": "queue", "public_id": "q", "uploaded_at": recent, "due": recent, "status": "scheduled"}}
    store = FakeStore()
    assert bp.cleanup(st, store, 7, NOW) == 1 and store.deleted == ["s"]


def test_rclone_exit_codes_mean_gone(monkeypatch):
    codes = iter([0, 3, 4, 1])
    monkeypatch.setattr(bp.subprocess, "run", lambda *a, **k: SimpleNamespace(returncode=next(codes), stdout=""))
    assert [bp.rclone_remove("x") for _ in range(4)] == [True, True, True, False]  # 3/4 = already absent


# ---------- mode "now": publish to the account right away ----------
NOW_ENV = dict(ENV, VYBEX_BUFFER="now")


def test_now_is_a_known_mode_and_a_typo_still_means_off():
    assert bp.mode_of(CFG, NOW_ENV) == "now" and bp.mode_of(CFG, {"VYBEX_BUFFER": "nov"}) == "off"


def test_now_publishes_at_once_without_slots_or_the_queue(tmp_path):
    out, buf = make_out(tmp_path), FakeBuf()
    res = run(out, tmp_path, NOW_ENV, buf)
    assert [r["state"] for r in res] == ["posting", "posting"] and all("due" not in r for r in res)
    assert all(c["mode"] == "now" and c["due"] is None for c in buf.calls)


def test_create_post_payload_for_now_is_sharenow_without_a_time():
    ok = R(200, {"data": {"createPost": {"post": {"id": "P1"}}}})
    b, calls = client(iter([ok]))
    b.create_post("CH", "t", "https://x/v.mp4", "now")
    q = calls[-1]["variables"]["input"]
    assert q["mode"] == "shareNow" and "dueAt" not in q and "saveToDraft" not in q and q["schedulingType"] == "automatic"
    assert q["aiAssisted"] is True and q["metadata"]["tiktok"]["isAiGenerated"] is True


def test_a_now_post_that_stays_unsent_for_an_hour_is_a_problem():
    t0 = NOW - timedelta(hours=2)
    st = {"a": {"mode": "now", "post_id": "p1", "status": "sending", "uploaded_at": t0.isoformat(), "file": "a.mp4"},
          "b": {"mode": "now", "post_id": "p2", "status": "sending", "uploaded_at": NOW.isoformat(), "file": "b.mp4"}}
    probs = bp.refresh_statuses(st, FakeBuf(statuses={"p1": {"status": "sending"}, "p2": {"status": "sent"}}), NOW)
    assert len(probs) == 1 and "a.mp4" in probs[0] and "sending" in probs[0] and st["b"]["status"] == "sent"
