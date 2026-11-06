# QA — automatic, `pipeline/qa.py`, run inside `python -m pipeline.build out/<date>`
Implemented: spec_valid, media_format, duration, audio (aac, length, LUFS, peak), no_black_frames, no_card_overlap, lyrics_confidence, cards_readable; HyperFrames check runs before render and aborts on errors AND on `contrast_aa_failure`, `text_not_painted`, `text_occluded` (even when the installed HyperFrames files them as warnings); the full report is saved as `work-N/check.json`; audio files are validated (ffprobe + full decode) before whisper; lyrics confidence is checked right after analysis. Not yet implemented (SKIP): beat-alignment check, fragment-is-popular-line check.

Output: one line per check, `PASS|FAIL|SKIP <name> <detail>`. Claude reads only these lines. SKIP is never reported as verified.

| # | Check | Tool | Rule |
|---|-------|------|------|
| 1 | spec valid | python | schema in `docs/video-spec.md`, scenes contiguous, word/time limits |
| 2 | composition check | `npx hyperframes check --json` | zero errors and zero contrast / unpainted / occluded text; other warnings counted, never hidden |
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

## Stability rules (daily run)
- **Readable cards.** Unsung words use `GREY` (6:1 on the card), the accent flash is darkened by `readable()` until it reads on the brightest background (`WORST_BG`), cards slide in opaque (a fade-in put text over the previous card), the island/clock slide instead of fading. Never use `color:transparent`, gradient text or white text on bright fills. After any template edit run `python -m pipeline.build` on a real spec: it runs the real HyperFrames check.
- **Audio.** `download.check_audio` (ffprobe + full ffmpeg decode): unreadable / no audio / shorter than `min_len` / longer than 25 min -> `fetch: bad_audio` in report.json, the song is skipped, the rest go on. Decoder warnings (`Illegal Audio-MPEG-Header`) with >= 95% of the track decoded are accepted and kept in `audio_notes`; less -> one ffmpeg re-encode into `out/audio-fixed/`, otherwise rejected.
- **Lyrics.** Words are never replaced or guessed. `pick_reliable` looks for another window of the same song with <= `whisper.max_low_ratio` (15%) low-confidence words; none -> `analyze: low_confidence`, nothing is rendered. QA enforces the same limit on the final video.
- **One song never stops the batch:** every stage error is written to that song's record in `report.json` (`stages`, `note`) and the loop continues. A song that failed stays in Drive `audio/` (only `render: ok` songs move to `done/`).
- **Pictures drawn by Claude (`draw`).** Claude may write an SVG picture for any line (no per-video cap). `pipeline/svg_safe.py` rebuilds it from an allowlist (shapes, gradients; no text/script/style/links/entities; <= 6000 chars, <= 120 elements) in the author step and again in the renderer; an unusable drawing becomes a template picture, the video still renders. Author timeout is 480 s.
- **No empty stretches.** `pick_reliable` also avoids windows with a pause longer than `whisper.max_gap_sec` (5 s) between lines (an instrumental break is an empty screen).
- **Variety.** 15 pictures (`ART_KEYS`), a picture is not repeated inside a video, the keyword fallback rotates widget kinds per song, and the Claude step is told which kinds the day's earlier videos used.
