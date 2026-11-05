import json
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from pipeline import batch, build, download, qa, sources
from pipeline.common import ROOT, Refused, load_config

CFG = load_config()


def make_mp4(path, audio=True):
    cmd = ["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", "color=c=black:s=160x90:d=1:r=10"]
    if audio:
        cmd += ["-f", "lavfi", "-i", "sine=frequency=440:duration=1"]
    subprocess.run(cmd + ["-pix_fmt", "yuv420p", str(path)], check=True)


def has_audio(p):
    out = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "a", "-show_entries", "stream=codec_name",
                          "-of", "csv=p=0", str(p)], capture_output=True, text=True).stdout
    return out.strip() == "aac"


# ---- mp4 -> audio extraction
def test_extract_audio_from_mp4_needs_rights(tmp_path):
    v = tmp_path / "clip.mp4"
    make_mp4(v)
    with pytest.raises(Refused):
        download.ensure_audio(v, rights_confirmed=False)
    a = download.ensure_audio(v, rights_confirmed=True)
    assert a.suffix == ".m4a" and has_audio(a)
    assert json.loads(Path(str(a) + ".license.json").read_text())["extracted_from"] == "clip.mp4"


def test_extract_keeps_verified_license_sidecar(tmp_path):
    v = tmp_path / "cc.mp4"
    make_mp4(v)
    Path(str(v) + ".license.json").write_text(json.dumps({"license": "by", "attribution": "X by Y"}))
    a = download.ensure_audio(v, True)
    assert json.loads(Path(str(a) + ".license.json").read_text())["attribution"] == "X by Y"


def test_extract_fails_cleanly_without_audio_track(tmp_path):
    v = tmp_path / "mute.mp4"
    make_mp4(v, audio=False)
    with pytest.raises(RuntimeError):
        download.ensure_audio(v, True)


def test_audio_files_pass_through(tmp_path):
    f = tmp_path / "a.mp3"
    f.write_bytes(b"x")
    assert download.ensure_audio(f) == f


def test_local_source_lists_video_and_marks_rights(tmp_path):
    (tmp_path / "Art - Song.mp4").write_bytes(b"x")
    (tmp_path / "Art - Other.mp3").write_bytes(b"x")
    (tmp_path / "sources.json").write_text(json.dumps({"Art - Song.mp4": {"license": "owned"}}))
    cfg = dict(CFG, audio_dir=str(tmp_path))
    monkey = sources.ROOT
    sources.ROOT = Path("/")
    try:
        res = {c.title: c for c in sources._local("art", 5, cfg, {})}
    finally:
        sources.ROOT = monkey
    assert res["Song"].rights_declared is True and res["Other"].rights_declared is False


# ---- queue / log parsing
def test_parse_queue_ignores_comments_and_blank_fields():
    real = batch.parse_queue((ROOT / "accounts/main/queue.md").read_text(encoding="utf-8"))
    assert real and real[0]["artist"] == "Max Korzh" and all(e["title"] for e in real)
    q = batch.parse_queue("# x\n<!-- a | b | c -->\nA | B | line | f.mp3 |\n | | \nC |\n")
    assert q == [{"artist": "A", "title": "B", "popular_line": "line", "audio_file": "f.mp3"}]


def test_parse_log_rows():
    log = "| date | song id |\n|---|---|\n| 2026-11-01 | 1 | Art | Song | love | cold | published | 77 |\n"
    used, recent = batch.parse_log(log)
    assert used == {("art", "song")} and recent == [("love", "cold")]


# ---- auto spec + modes
@pytest.mark.parametrize("mode,expected", [("auto", "with_audio"), ("tiktok", "tiktok")])
def test_autospec_valid_and_avoids_recent(mode, expected):
    recent = [("inner", "dusk"), ("loneliness", "cold"), ("breakup", "warm")]
    s = batch.autospec({"artist": "Max Korzh", "title": "Сердце пацана"}, 1, "2026-11-05", recent, CFG, mode,
                       "accounts/main/audio/x.mp3")
    assert s["mode"] == expected and qa.validate_spec(s, CFG) == []
    assert s["metaphor"] not in {"inner", "loneliness", "breakup"} and s["palette"] not in {"dusk", "cold", "warm"}
    assert ("audio" in s) == (mode == "auto") and "#maxkorzh" in s["hashtags"] and len(s["caption"]) <= 150


def test_sync_info_has_start_time_and_steps():
    s = build.sync_info({"song": {"artist": "A", "title": "T"}}, {"audio_start": 62.4, "duration": 37.0, "beats": [0.5, 1.0]})
    assert s["sound_start"] == "1:02.40" and "A — T" in s["steps"][1] and len(s["steps"]) >= 4


def test_validate_accepts_tiktok_mode_and_rejects_unknown():
    base = {"id": "x", "mode": "tiktok", "song": {}, "metaphor": "love", "palette": "cold", "caption": "c",
            "hashtags": ["#a", "#b", "#c"], "ai_label": True}
    assert qa.validate_spec(base, CFG) == []
    assert qa.validate_spec(dict(base, mode="spotify"), CFG)


# ---- batch: fault tolerance, independent stages
def test_batch_survives_failures_and_reports(tmp_path):
    acc = tmp_path / "accounts" / "main"
    acc.mkdir(parents=True)
    (acc / "queue.md").write_text("A | One | | |\nB | Two | | |\nC | Three | | |\nD | Four | | |\n", encoding="utf-8")
    (acc / "log.md").write_text("| 2026-11-01 | 1 | D | Four | love | cold | published | 1 |\n", encoding="utf-8")
    aud = tmp_path / "a.mp3"
    aud.write_bytes(b"x")

    def fetch(entry, cfg, mode):
        if entry["title"] == "One":
            raise RuntimeError("source exploded")
        if entry["title"] == "Two":
            return None, [{"source": "openverse", "state": "empty", "detail": "0/0"}]
        return aud, []

    frag = {"first": 0, "last": 0, "start": 0, "end": 40, "length": 40, "reason": "x"}
    built = []

    def build_stub(out, n, cfg):
        built.append(n)
        (out / f"work-{n}").mkdir(exist_ok=True)
        (out / f"work-{n}" / "final.mp4").write_bytes(b"v")
        return "id", [("PASS", "x", "")], out / "v.mp4"

    stages = {"fetch": fetch, "analyze": lambda a, p, c: {"fragment": frag, "lines": [], "beats": [], "summary": {}},
              "build": build_stub}
    rep = batch.run_batch("tiktok", 1, "2026-11-05", CFG, root=tmp_path, stages=stages)
    assert rep["succeeded"] == 1 and built == [1]
    songs = {r["song"]: r for r in rep["songs"]}
    assert "error" in songs["A — One"]["stages"]
    assert songs["B — Two"]["stages"]["fetch"] == "no_audio"
    assert songs["C — Three"]["stages"]["render"] == "ok"
    assert "D — Four" not in songs  # already in log -> skipped
    assert (tmp_path / "out" / "2026-11-05" / "report.json").exists()
    spec = json.loads((tmp_path / "out" / "2026-11-05" / "spec-1.json").read_text(encoding="utf-8"))
    assert spec["mode"] == "tiktok" and "audio" not in spec


def test_build_one_missing_files_is_a_fail_line_not_a_crash(tmp_path):
    sid, lines, video = build.build_one(tmp_path, 1, CFG)
    assert video is None and lines[0][0] == "FAIL"
    (tmp_path / "spec-1.json").write_text(json.dumps({"id": "z", "mode": "tiktok", "song": {"artist": "a", "title": "b"},
                                                      "metaphor": "love", "palette": "cold", "caption": "c",
                                                      "hashtags": ["#a", "#b", "#c"], "ai_label": True}))
    sid, lines, video = build.build_one(tmp_path, 1, CFG)
    assert video is None and "analyze stage" in lines[0][2]


def test_queue_from_audio_adds_only_uncovered_files(tmp_path):
    (tmp_path / "Basta - Sansara.mp3").write_bytes(b"x")
    (tmp_path / "Guf - Ayza.mp3").write_bytes(b"x")
    (tmp_path / "notes.txt").write_text("x")
    q = [{"artist": "Basta", "title": "Sansara", "popular_line": "", "audio_file": ""}]
    got = batch.queue_from_audio(tmp_path, q)
    assert [(e["artist"], e["title"], e["audio_file"]) for e in got] == [("Guf", "Ayza", "Guf - Ayza.mp3")]


def test_pack_names_and_caption(tmp_path):
    (tmp_path / "work-1").mkdir()
    (tmp_path / "work-1" / "final.mp4").write_bytes(b"v")
    (tmp_path / "sync-1.txt").write_text("start 0:07")
    spec = {"song": {"artist": "A/B", "title": "T"}, "caption": "cap", "hashtags": ["#a", "#b"]}
    batch.pack(tmp_path, 1, spec, "tiktok", tmp_path / "ready")
    names = sorted(p.name for p in (tmp_path / "ready").iterdir())
    assert names == ["1 AB - T caption.txt", "1 AB - T sync.txt", "1 AB - T.mp4"]
    assert "Создано ИИ" in (tmp_path / "ready" / "1 AB - T caption.txt").read_text(encoding="utf-8")


def test_intro_shifts_scenes_and_audio_start():
    from pipeline import render_widgets, script_gen
    words = [{"w": f"w{i}", "s": 10 + i * .5, "e": 10.4 + i * .5, "p": .9} for i in range(6)]
    an = {"lines": [{"start": 10, "end": 13, "text": "x", "words": words}],
          "fragment": {"first": 0, "last": 0, "start": 10.0, "end": 42.0}, "beats": [10.5]}
    cfg = load_config()
    p0, p1 = script_gen.build_scenes(an, {"artist": "A", "title": "T"}, cfg), script_gen.build_scenes(an, {"artist": "A", "title": "T"}, cfg, intro=1.6)
    assert p1["audio_start"] == 8.4 and p1["intro"] == 1.6 and p1["duration"] == round(p0["duration"] + 1.6, 2)
    assert p1["scenes"][0]["start"] == round(p0["scenes"][0]["start"] + 1.6, 3)
    page = render_widgets.build_html(p1, {"song": {"artist": "A", "title": "T"}, "palette": "dusk"}, cfg)
    assert 'id="clipIntro"' in page and 'data-composition-id="main"' in page


def test_parse_name_handles_site_filenames():
    from pipeline.common import parse_name
    assert parse_name("Basta_-_Moya_igra_2_79894643") == ("Basta", "Moya igra 2")
    assert parse_name("Баста_8800") == ("", "Баста")
    assert parse_name("Max Korzh - Сердце пацана") == ("Max Korzh", "Сердце пацана")


def test_short_audio_is_padded_to_requested_length(tmp_path):
    import subprocess
    from pipeline import render
    src = tmp_path / "s.wav"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", "sine=d=3", str(src)], check=True)
    out = tmp_path / "o.m4a"
    render.make_audio(src, 0, 6, out, load_config())
    assert abs(float(qa.probe(out)["format"]["duration"]) - 6) < 0.3
