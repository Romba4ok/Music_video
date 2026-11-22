import shutil
from pathlib import Path

from pipeline import audio_replacements, batch, fetch_songs
from pipeline.common import load_config


def test_repeat_low_confidence_until_three_ready(tmp_path, monkeypatch):
    cfg = load_config()
    audio = tmp_path / cfg["audio_dir"]
    audio.mkdir(parents=True)
    account = tmp_path / "accounts/main"
    titles = ["Bad", "Good", "Published", "Missing", "BadAgain", "GoodTwo", "GoodThree", "Extra"]
    (account / "queue.md").write_text("".join(f"A | {t} | {t} | A - {t}.mp3\n" for t in titles))
    (account / "songs-memory.md").write_text(fetch_songs.HEAD, encoding="utf-8")
    for title in titles[:2]:
        (audio / f"A - {title}.mp3").touch()
    drive = tmp_path / "drive"
    for folder in ("audio", "done", "state"):
        (drive / folder).mkdir(parents=True)
    (drive / "done/A - Published.mp3").touch()

    def rclone(cmd, src, *args):
        def path(arg):
            return drive / arg[3:] if isinstance(arg, str) and arg.startswith("gd:") else Path(arg)
        if cmd == "lsf":
            return "\n".join(p.name + ("/" if p.is_dir() else "") for p in path(src).iterdir())
        assert cmd == "copyto"
        shutil.copyfile(path(src), path(args[0]))

    queries = []
    def download(w, cfg, out, **kw):
        title = w["title"]
        queries.append(title)
        if title == "Missing":
            return None, "test:unavailable"
        name = f"A - {title}.mp3"
        (out / name).touch()
        (out / (name + ".license.json")).write_text('{"download_only": true, "analysis_only": true}')
        return name, "track"

    monkeypatch.setattr(audio_replacements, "rclone", rclone)
    monkeypatch.setattr(fetch_songs, "fetch_one", download)
    real_run = fetch_songs.run
    monkeypatch.setattr(fetch_songs, "run", lambda args, **kw: real_run(args, sleep=lambda _: None, **kw))
    analyzed = []
    def analyze(path, hook, cfg):
        analyzed.append(hook)
        return {"fragment": {"low_ratio": 0.5 if hook.startswith("Bad") else 0}}

    def build(out, n, cfg):
        video = out / f"work-{n}/final.mp4"
        video.parent.mkdir()
        video.touch()
        return "id", [], video

    def fetch(e, cfg, mode):
        path = audio / e["audio_file"]
        return (path if path.exists() else None), []

    stages = dict(fetch=fetch, check_audio=lambda path, _: (path, []), analyze=analyze,
                  author=lambda e, a, s, cfg: (a, s, "ok"), build=build)
    refill = audio_replacements.DriveReplacements(tmp_path, cfg)
    report = batch.run_batch("auto", 3, "2026-11-22", cfg, root=tmp_path, stages=stages, replace_audio=refill)
    assert queries == ["Missing", "BadAgain", "GoodTwo", "GoodThree"]
    assert analyzed == ["Bad", "Good", "BadAgain", "GoodTwo", "GoodThree"]
    assert report["succeeded"] == 3
    assert [r["ready"] for r in report["songs"] if r.get("ready")] == [
        "1 A - Good", "2 A - GoodTwo", "3 A - GoodThree"]
    assert (drive / "audio/A - GoodThree.mp3.license.json").exists()
    assert "agoodthree" in fetch_songs.load_memory(drive / "state/songs.md")["done"]


def test_verify_counts_only_unique_buffer_receipts_after_low_confidence():
    rows = [{"stages": {"analyze": "low_confidence"}}]
    report = {"requested": 3, "songs": rows, "mode": "auto"}
    for state, post_id in [("posting", "1"), ("posting", "1"), ("error", "2"), ("scheduled", "3")]:
        rows.append({"stages": {"render": "ok"}, "buffer": {"post_id": post_id, "state": state}})
    assert not audio_replacements.verify(report, "now")
    rows.append({"stages": {"render": "ok"}, "buffer": {"post_id": "4", "state": "posting"}})
    assert audio_replacements.verify(report, "now")
    assert audio_replacements.verify({"requested": 3, "songs": [], "mode": "auto"}, "now")
    assert audio_replacements.verify({"requested": 10, "songs": rows, "mode": "auto"}, "plan")
