# QA — automatic, `pipeline/qa.py`, run inside `python -m pipeline.build out/<date>`
Implemented: spec_valid, media_format, duration, audio (aac, length, LUFS, peak), no_black_frames, no_card_overlap, lyrics_confidence, cards_readable; HyperFrames lint runs before render and aborts on errors. Not yet implemented (SKIP): beat-alignment check, fragment-is-popular-line check.

Output: one line per check, `PASS|FAIL|SKIP <name> <detail>`. Claude reads only these lines. SKIP is never reported as verified.

| # | Check | Tool | Rule |
|---|-------|------|------|
| 1 | spec valid | python | schema in `docs/video-spec.md`, scenes contiguous, word/time limits |
| 2 | composition lint | `npx hyperframes check --json` | zero errors; warnings listed |
| 3 | resolution/fps/codec | ffprobe | 1080x1920, fps = config, H.264, MP4 |
| 4 | duration | ffprobe | 30–60 s and = spec.duration ±0.1 s |
| 5 | audio | ffprobe | `commentary`: no audio expected (SKIP loudness). `with_audio`: AAC present, length = video ±0.1 s, ≈ -14 LUFS, true peak ≤ -1 dBTP, fade-out at the end |
| 6 | no empty/broken frames | ffmpeg `freezedetect`/`blackdetect` + frame count | no black > 0.3 s, frame 0 not black |
| 7 | text not clipped, no overlap | hyperframes layout check from #2 | zero layout errors |
| 8 | lyric cards match words | `with_audio` only: shown text = whisper words, every word at its timestamp ±0.1 s, no low-confidence words shown | else SKIP |
| 9 | animation hits beats | `with_audio` only: librosa beats vs card/pulse times | else SKIP |
| 11 | fragment is the popular line | `with_audio` only: fragment contains `popular_line` or top chorus candidate; starts/ends on phrase boundaries | else SKIP |
| 10 | attribution/AI label | spec | `ai_label: true`; if any third-party asset, credit present in `assets/credits.json` |

Failure policy: fix the spec fields named in the FAIL line, rerun the one failed video, max 2 retries, then write `out/<date>/qa-fail.txt` and stop. Never upload a video with any FAIL.
Source files are kept until the final video passes QA and is uploaded.
