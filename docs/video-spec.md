# Video spec — the only thing Claude writes per video

File: `out/<date>/spec-<n>.json` (n = 1..3). Scripts turn it into `variables.json` for the template, render it, QA it.

```json
{
  "id": "2026-11-05-1",
  "mode": "with_audio",
  "song": {"artist": "Max Korzh", "title": "Сердце пацана"},
  "audio": "accounts/main/audio/Max Korzh - Сердце пацана.mp3",
  "fragment": {"start": 62.4, "end": 86.0},
  "metaphor": "loneliness",
  "palette": "dusk",
  "duration": 24,
  "caption": "≤150 chars, no hashtags here",
  "hashtags": ["#казахстан", "#рэп", "#смысл"],
  "ai_label": true
}
```
In `with_audio` mode Claude does NOT write scenes: `python -m pipeline.analyze` writes `out/<date>/analysis-<n>.json` (word timestamps + confidence, beats, BPM, chorus, and the chosen fragment) and `python -m pipeline.build` makes the lyric cards from it. Claude's job is only: song choice, metaphor + palette, caption, hashtags. The fragment is chosen by analyze (popular line, else chorus); Claude does not edit it. Low-confidence words are kept but counted: QA fails a video with more than 15% of them.

In `commentary` mode (no audio) Claude also writes `scenes`:
```json
"scenes": [
  {"role": "hook",    "text": "…", "start": 0,  "dur": 3},
  {"role": "meaning", "text": "…", "start": 3,  "dur": 5, "quote_verified": false},
  {"role": "outro",   "text": "…", "start": 18, "dur": 6}
]
```

## Modes
| `mode` | Name | Result |
|---|---|---|
| `with_audio` | AUTO | audio from an allowed source (CC0/PD/CC-BY, or the owner's file) is mixed into the mp4: full automation track -> mp4 with sound |
| `tiktok` | TIKTOK | silent mp4 timed to the song + `sync-<n>.json/.txt` ("start the official sound at M:SS.xx"); the audio file is analysed locally only, never embedded; sound is added inside TikTok |
| `commentary` | — | silent mp4 with hand-written scenes, no analysis |
Stages are independent: `fetch` (search/download/extract audio from any legally obtained mp4) -> `analyze` -> `render`. `python -m pipeline batch --mode auto|tiktok --count 3` runs all three per song without any LLM and never aborts on one failure (see `out/<date>/report.json`).

## Fragment choice (with_audio / tiktok) — most popular line wins
Pick the 30–60 s window (length follows the meaning: end where the thought of the lines ends; default ~35–45 s) that contains the line people know and listen to most:
1. `popular_line` from `queue.md`, if present: find it in the whisper lyric lines (fuzzy match) and centre the window on its first occurrence in a chorus.
2. Else the chorus: the most-repeated lyric block in `analysis` (`chorus_candidates[0]`), starting on a phrase boundary / beat, with a strong intensity rise.
3. Window starts on a phrase start and ends on a phrase end; never cut mid-word. Last 1.5 s: fade out audio and show artist – title.
If `popular_line` is not found in the transcript with confidence ≥ threshold, use rule 2 and note it in `meta.json`.

## Fields
- `mode`: `with_audio` (default) | `commentary`.
- `metaphor` (scene template in `template/scenes/`): `breakup` (chat, deleted contact, fading heart) · `loneliness` (empty place, muted notifications, one silhouette) · `love` (messages, photos, hearts) · `nostalgia` (old photos, calendar, old messages) · `money` (bank UI, balance, counters) · `time` (clocks, timers, calendar) · `inner` (rain, night city, dim light). Pick by the meaning of the fragment's lines. Differ from the last 3 log rows.
- `palette`: `cold` · `warm` · `dusk` · `contrast`.
- `duration` 30–60; = fragment length (+ outro).

## Lyric cards (built from analysis, rules the builder follows)
- Each lyric line appears 0.15–0.3 s before its first word and leaves after its last word; each word sharpens exactly at its timestamp; elements pulse on beats.
- ≤ 8 words per card; split long lines at phrase breaks. No overlap of cards/text.
- Words with whisper confidence below threshold are not shown as guessed text: the line is flagged, QA #8 fails it.

## Text rules (commentary + caption)
- Russian. hook ≤ 7 words; meaning ≤ 14 words; outro ≤ 8 words. `dur ≥ max(2.5, characters / 12)` s.
- No filler ("в этой песне автор говорит"). No invented facts.

## Layout contract (templates enforce)
1080x1920; text inside y 168–1330 and 90% safe box; nothing under the right action rail; card enters before its line, leaves after.

## Defaults live in `config.json`
fps (30; 60 doubles render time on Actions), resolution, loudness (-14 LUFS / -1 dBTP), whisper model/confidence threshold, voiceover off.
