"""Whisper lines of a song for a Remotion composition (uses the pipeline's own `transcribe`, so the lyrics come only from the supplied audio).

  .venv/Scripts/python.exe -I remotion/scripts/transcribe.py "audio/Artist - Song.mp3" remotion/public/song-lyrics.json
  # refine one window with the big model (clean text for the chosen fragment):
  .venv/Scripts/python.exe -I remotion/scripts/transcribe.py "audio/Artist - Song.mp3" remotion/public/song-refined.json large-v3 88 122

Writes the JSON and a UTF-8 summary `<json>.txt` (index start-end min-confidence text). Read the .txt with the Read tool: the Windows
console garbles Cyrillic. Never open the full word lists.
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from pipeline.analyze import transcribe  # noqa: E402
from pipeline.common import load_config  # noqa: E402

audio, out = sys.argv[1], Path(sys.argv[2])
model = sys.argv[3] if len(sys.argv) > 3 else None
window = (float(sys.argv[4]), float(sys.argv[5])) if len(sys.argv) > 5 else None
lines = transcribe(audio, load_config(), model, window)
out.write_text(json.dumps(lines, ensure_ascii=False, indent=1), encoding="utf-8")
Path(str(out) + ".txt").write_text(
    "\n".join(f"{i} {l['start']:.1f}-{l['end']:.1f} p{min(w['p'] for w in l['words']):.2f} {l['text']}" for i, l in enumerate(lines)),
    encoding="utf-8")
print(len(lines), "lines ->", out)
