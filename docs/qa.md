# QA — automatic, `pipeline/qa.py`, run inside `python -m pipeline.build out/<date>`
Implemented: spec_valid, media_format, duration, audio (aac, length, LUFS, peak), no_black_frames, no_card_overlap, lyrics_confidence, cards_readable; props check (`render.check_props`) runs before the Remotion render and aborts on an empty scenario; `text_occluded` (even when the installed HyperFrames files them as warnings); the full report is saved as `work-N/check.json`; audio files are validated (ffprobe + full decode) before whisper; lyrics confidence is checked right after analysis. Not yet implemented (SKIP): beat-alignment check, fragment-is-popular-line check.

Output: one line per check, `PASS|FAIL|SKIP <name> <detail>`. Claude reads only these lines. SKIP is never reported as verified.

| # | Check | Tool | Rule |
|---|-------|------|------|
| 1 | spec valid | python | schema in `docs/video-spec.md`, scenes contiguous, word/time limits |
| 2 | props check | `render.check_props` | at least one card, positive duration, end card inside the video (Remotion itself fails the render on a React error) |
| 3 | resolution/fps/codec | ffprobe | 1080x1920, fps = config, H.264, MP4 |
| 4 | duration | ffprobe | `min_len`..`max_total` (config: 20 s .. max_len + close_overrun + 4 = 42 s) and = plan ±0.25 s; the file may be 1.5 frames off the limit (MP4 is whole frames), nothing more |
| 5 | audio | ffprobe | `commentary`: no audio expected (SKIP loudness). `with_audio`: AAC present, length = video ±0.1 s, ≈ -14 LUFS, true peak ≤ -1 dBTP, fade-out at the end |
| 6 | no empty/broken frames | ffmpeg `freezedetect`/`blackdetect` + frame count | no black > 0.3 s, frame 0 not black |
| 7 | text not clipped | not automated since the move to Remotion: text is cut to fit by construction (`clip` in `Bodies.tsx`); check frames when a template changes (`docs/remotion.md`) | SKIP |
| 8 | lyric cards match words | `with_audio` only: shown text = whisper words, every word at its timestamp ±0.1 s, no low-confidence words shown | else SKIP |
| 9 | animation hits beats | `with_audio` only: librosa beats vs card/pulse times | else SKIP |
| 11 | fragment is the popular line | `with_audio` only: fragment contains `popular_line` or top chorus candidate; starts/ends on phrase boundaries | else SKIP |
| 10 | attribution/AI label | spec | `ai_label: true`; if any third-party asset, credit present in `assets/credits.json` |

Failure policy: fix the spec fields named in the FAIL line, rerun the one failed video, max 2 retries, then write `out/<date>/qa-fail.txt` and stop. Never upload a video with any FAIL.
Source files are kept until the final video passes QA and is uploaded.

## Duration (never relaxed)
Why 15.08 s once reached QA (Серёга — Чёрный Бумер): a 12.58 s fragment + 2.5 s end card. Nothing enforced `min_len` after the fragment was picked: `pick_fragment` stops growing when it cannot, a start pinned in the file name cannot go back, and the second recognition pass (`refine_fragment`) recomputes the window from the new lines and can shorten it. The scenario was then rendered in full and refused by QA.
Now three layers, none of which stretches audio or adds empty frames:
1. `analyze.ensure_min_len` grows the window over neighbouring REAL lyric lines (forward first, then back; a pinned start moves only when nothing else is left and the reason says so), after the first choice and after the second recognition pass. Lyrics too short for min_len: the fragment is marked `short`.
2. `script_gen.fit_duration` adds REAL song audio around the lyrics until the video is `min_len + 0.12 s`: a lead-in before the first line (`preroll_max` 3 s; the first card is on screen from frame 0) and music after the last line under the last card (`hold_max` 4 s), both limited by what the song really has. Words and beats keep their place against the music (`audio_start` moves, nothing is retimed).
3. `qa.plan_duration_errors` runs in `build` BEFORE the render: a scenario that still does not fit (or is too long) fails at once as `scenario_duration` with the reason; the render never starts.
Tests: `tests/test_duration.py` (including the 15.08 s case).

## Stability rules (daily run)
- **Readable cards.** Unsung words use `GREY` (6:1 on the card), the accent flash is darkened by `readable()` until it reads on the brightest background (`WORST_BG`), cards slide in opaque (a fade-in put text over the previous card), the island/clock slide instead of fading. Never use `color:transparent`, gradient text or white text on bright fills. After any template edit run `python -m pipeline.build` on a copy of a real spec and look at frames (`docs/remotion.md`): the old HyperFrames contrast check is gone, so readability is checked by eye.
- **Audio.** `download.check_audio` (ffprobe + full ffmpeg decode): unreadable / no audio / shorter than `min_len` / longer than 25 min -> `fetch: bad_audio` in report.json, the song is skipped, the rest go on. Decoder warnings (`Illegal Audio-MPEG-Header`) with >= 95% of the track decoded are accepted and kept in `audio_notes`; less -> one ffmpeg re-encode into `out/audio-fixed/`, otherwise rejected.
- **Lyrics.** Words are never replaced or guessed. `pick_reliable` looks for another window of the same song with <= `whisper.max_low_ratio` (15%) low-confidence words; none -> `analyze: low_confidence`, nothing is rendered. QA enforces the same limit on the final video.
- **Second recognition pass.** `small` finds the window, then `whisper.refine_model` (`large-v3`) re-reads only that window (+2 s) and its lines replace the first-pass ones (`analyze.refine_fragment`); a failed or near-empty second pass keeps the first one, the reason in report.json says which. Measured locally on one song: ~100 s per song with the model cached, 12% of the words changed, mean confidence 0.88 -> 0.92; not every misheard word is fixed. Whisper credit lines ("Редактор субтитров…") are filtered out. Switch off: `whisper.refine_model: ""`.
- **One song never stops the batch:** every stage error is written to that song's record in `report.json` (`stages`, `note`) and the loop continues. A song that failed stays in Drive `audio/` (only `render: ok` songs move to `done/`).
- **Pictures drawn by Claude (`draw`).** Claude may write an SVG picture for any line (no per-video cap). `pipeline/svg_safe.py` rebuilds it from an allowlist (shapes, gradients; no text/script/style/links/entities; <= 6000 chars, <= 120 elements) in the author step and again in the renderer; an unusable drawing becomes a template picture, the video still renders. Author timeout is 480 s.
- **No empty stretches.** `pick_reliable` also avoids windows with a pause longer than `whisper.max_gap_sec` (5 s) between lines (an instrumental break is an empty screen).
- **Variety.** `draw` plus 8 animated scenes (`widget_kinds.SCENE_KINDS`); a scene is not repeated inside a video, the keyword fallback picks scenes by meaning and rotates them per song, and the Claude step is told which kinds the day's earlier videos used. The old template cards are removed.
