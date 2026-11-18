import subprocess

import pytest

from pipeline import qa, render
from pipeline.common import load_config

CFG = load_config()


def _song(path, expr):
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", expr, "-ar", "44100", "-c:a", "libmp3lame", str(path)], check=True)


# a quiet melody with loud kicks (peak-to-loudness ratio ~14 dB: the real M'Dee track measured -18 LUFS with one-pass loudnorm, QA wants -16.5..-11.5)
@pytest.mark.parametrize("name,expr", [
    ("kick", "aevalsrc='0.02*sin(2*PI*300*t)+if(lt(mod(t,0.5),0.08),0.9*sin(2*PI*60*t),0)':d=26:s=44100"),
    ("loud", "aevalsrc='0.95*sin(2*PI*220*t)*(0.8+0.2*sin(2*PI*3*t))':d=26:s=44100"),
])
def test_make_audio_reaches_the_qa_loudness_window(tmp_path, name, expr):
    _song(tmp_path / "s.mp3", expr)
    render.make_audio(tmp_path / "s.mp3", 0, 25, tmp_path / "o.m4a", CFG)
    lufs, peak = qa.loudness(tmp_path / "o.m4a")
    assert abs(lufs - CFG["target_lufs"]) <= 2.5 and peak <= CFG["max_true_peak"] + 0.3, (lufs, peak)
