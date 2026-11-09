# Music Video Factory — rules for Claude (read this first; read other files only when named here)

Goal: 3 vertical TikTok videos/day (1080x1920) about meaningful songs for Kazakhstan youth 18-25.
Automatic, free tools only, official publishing APIs only. One account now (`accounts/main`), more later (`accounts/<name>`).

## Token budget — hard rules
1. You write **JSON specs only** (`docs/video-spec.md`): song, fragment, metaphor, palette, caption. Scripts do everything heavy: whisper, beats, scenes-from-lyrics, audio mix, render, QA, upload. Never write scene HTML if a template scene fits; never hand-render frames.
2. Do NOT explore the repo, do NOT web-search (sole exception: queue REFILL in `queue.md`, max 3 searches), do NOT open the HyperFrames skill/reference docs. Never read full whisper word lists, only `summary` of `analysis-<n>.json`. `docs/hyperframes-notes.md` is the full contract you need; open it only if you must edit a template.
3. Read once, in this order, and no more: `accounts/main/brief.md`, `accounts/main/log.md` (last 30 rows), `accounts/main/queue.md`, `docs/video-spec.md`. Do not re-read after writing.
4. One pass: produce all 3 specs in a single step. No drafts, no self-review essays, no plans in output.
5. QA is automatic (`pipeline/qa.py`, run by `python -m pipeline.build`). Look only at its PASS/FAIL lines. On FAIL fix the listed spec fields once, rerun, max 2 retries, then stop and report. Never view frame images unless the task says `--debug-visual`.
6. Final reply: max 5 lines (one per video: id, song, PASS/FAIL).

## Honesty rules
- Lyrics on cards come from the whisper transcript of the supplied audio, never from memory. Never invent facts about songs or artists. Low-confidence words are flagged, not guessed.
- Audio is added by the pipeline from files the owner puts in `accounts/main/audio/`. Never fetch/download songs yourself.
- Show the song's most popular line (chorus hook), a fragment of 20–35 s (length follows the meaning: ends where the thought ends, never mid-sentence), never the whole song.
- Never claim a check passed if the script did not run it.
- If a resource is not legally available, say so; do not substitute invented data.

## Files
- `accounts/<acc>/brief.md` niche, tone, format, bans (human-edited)
- `accounts/<acc>/log.md` what was published (script-written)
- `accounts/<acc>/queue.md` candidate songs backlog
- `docs/video-spec.md` JSON schema, scene library, timing rules
- `docs/qa.md` automatic checks
- `docs/rights.md` music/image licensing, AI label, publishing
- `docs/hyperframes-notes.md` render contract cheat sheet
- `docs/claude-author.md` Claude step in the batch: cards/hook/notifications written per song (prompts/widgets.md)
- `docs/github-setup.md` reusable GitHub Actions + Drive + secrets setup, lessons learned (copy to other projects)
- `docs/remotion.md` Remotion route: card-style videos rendered locally to mp4 (setup, new-song steps, lessons)
- `docs/buffer.md` hand-over of ready videos to the Buffer TikTok queue (draft/queue, dedup, temp hosting)
- `docs/widgets-template.md` widget-edit template: layout, pacing, card kinds, how to pick pictures for lyric meaning
- `prompts/generate.md` the daily task for `claude -p`

## Secrets
Only GitHub Secrets. Never print, log or write tokens to any file.
