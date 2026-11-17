"""No audio file = no Whisper, no Claude, no render, and a normal (not failed) end; a published song is never processed again; workflows are wired as separate jobs."""
import json

import yaml

from pipeline import batch
from pipeline.common import ROOT, load_config

CFG = load_config()


def spies():
    calls = []
    def spy(name):
        return lambda *a, **k: calls.append(name) or (None, [])
    return calls, {"fetch": lambda e, c, m: (None, [{"source": "jamendo", "state": "ok", "detail": "1/1"}]), "check_audio": spy("check_audio"),
                   "analyze": spy("analyze"), "author": spy("author"), "build": spy("build")}


def acc(tmp_path, queue, log=""):
    d = tmp_path / "accounts" / "main"
    d.mkdir(parents=True)
    (d / "queue.md").write_text(queue, encoding="utf-8")
    (d / "log.md").write_text(log, encoding="utf-8")
    (tmp_path / CFG["audio_dir"]).mkdir(parents=True, exist_ok=True)


def test_without_audio_nothing_heavy_runs_and_the_status_is_no_audio_not_failed(tmp_path):
    acc(tmp_path, "Tasso | Таю | | |\nXcho | Ветер | | |\n")
    calls, stages = spies()
    rep = batch.run_batch("auto", 3, "2026-11-17", CFG, root=tmp_path, stages=stages)
    assert calls == [] and rep["succeeded"] == 0                      # whisper (analyze), Claude (author), render (build) were never called
    assert batch.batch_status(rep) == "no_audio"
    assert (tmp_path / "out" / "2026-11-17" / "report.json").exists() and not list((tmp_path / "out" / "2026-11-17").glob("**/*.mp4"))


def test_status_failed_only_for_real_problems():
    ok = {"succeeded": 1, "songs": []}
    assert batch.batch_status(ok) == "ok"
    assert batch.batch_status({"succeeded": 0, "songs": [{"stages": {"fetch": "no_audio"}}]}) == "no_audio"
    assert batch.batch_status({"succeeded": 0, "songs": []}) == "no_audio"
    for st in ({"fetch": "bad_audio"}, {"fetch": "ok", "analyze": "low_confidence"}, {"fetch": "ok", "render": "FAIL"}, {"error": "RuntimeError: x"}):
        assert batch.batch_status({"succeeded": 0, "songs": [{"stages": {"fetch": "no_audio"}}, {"stages": st}]}) == "failed"


def test_a_song_already_in_the_publish_log_is_not_fetched_or_processed_again(tmp_path):
    acc(tmp_path, "Tasso | Таю | | |\n", log="| 2026-11-16 | s1 | Tasso | Таю | metaphor | palette | published | 123 |\n")
    seen = []
    calls, stages = spies()
    stages["fetch"] = lambda e, c, m: seen.append(e["title"]) or (None, [])
    batch.run_batch("auto", 1, "2026-11-17", CFG, root=tmp_path, stages=stages)
    assert seen == []                                                 # the published song is skipped before any source / Whisper / render


def load(name):
    return yaml.safe_load((ROOT / ".github" / "workflows" / name).read_text(encoding="utf-8"))


def test_generate_has_a_light_check_job_and_the_heavy_job_needs_audio():
    g = load("generate.yml")
    assert list(g["jobs"]) == ["search", "check", "generate"]
    heavy = json.dumps(g["jobs"]["generate"]["steps"])
    light = json.dumps(g["jobs"]["check"]["steps"])
    for needle in ("npm ci", "remotion", "faster-whisper", "requirements.txt", "claude-code", "ffmpeg"):
        assert needle in heavy or needle == "faster-whisper"          # whisper comes with requirements.txt
        assert needle not in light                                    # the light job installs none of it
    assert "requirements.txt" not in light
    cond = g["jobs"]["generate"]["if"]
    assert "needs.check.outputs.audio != '0'" in cond and "needs.check.result == 'success'" in cond
    assert g["jobs"]["generate"]["needs"] == "check" and g["jobs"]["search"]["if"].endswith("== 'true' }}")   # search is optional, off by default
    assert g[True]["workflow_dispatch"]["inputs"]["search"]["default"] == "false" and "schedule" not in g[True]


def test_the_song_search_has_its_own_daily_schedule_and_generate_never_publishes_silent_video():
    f = load("fetch-songs.yml")
    assert f[True]["schedule"][0]["cron"] == "0 1 * * *" and "workflow_call" in f[True] and "workflow_dispatch" in f[True]
    assert CFG.get("buffer", {}).get("silent", "hold") == "hold"       # a silent video is held, not sent (see tests/test_buffer.py)
