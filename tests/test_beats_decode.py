import shutil
import struct
import subprocess

import pytest

from pipeline import analyze


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg not installed")
def test_beats_reads_an_mp3_with_a_huge_id3_cover(tmp_path):
    """CI run 2026-11-16: libsndfile gave up on mp3s with >64 KB before the first frame ("Giving up searching valid MPEG header"), so librosa.load
    failed for every song although check_audio (ffmpeg) accepted them."""
    plain = tmp_path / "plain.mp3"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "sine=frequency=440:duration=6", "-c:a", "libmp3lame", str(plain)], check=True)
    n = 150_000
    body = b"APIC" + struct.pack(">I", n) + b"\0\0" + b"\0image/jpeg\0\3\0" + b"\xff" * (n - 14)
    size = bytes([(len(body) >> s) & 127 for s in (21, 14, 7, 0)])  # ID3v2 sizes are 4 x 7 bits
    big = tmp_path / "big.mp3"
    big.write_bytes(b"ID3\x03\x00\x00" + size + body + plain.read_bytes())
    assert abs(analyze.beats(big)["duration"] - 6) < 0.3
