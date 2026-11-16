# Rights, sources, AI label, publishing

## Music (mode `with_audio`, default)
- The song audio is added to the video by our pipeline. The audio file is **supplied by the account owner** in `accounts/main/audio/<artist> - <title>.<mp3|wav|m4a>`. The owner is responsible for having the right to publish it.
- The pipeline never downloads songs from streaming platforms/YouTube, never bypasses DRM or access limits. No file in `audio/` => that song is skipped and reported ("need audio: <artist> – <title>"), never replaced with invented data.
- `accounts/main/audio/sources.json` (owner-maintained, one entry per file): `{"<file>": {"source": "where it came from", "license": "owned|purchased|licensed|other"}}`. `pipeline/sources.py` reads it for the local source; a missing entry is labelled `owner-supplied`.
- Allowed automatic sources (`config.json`): Openverse and Jamendo (only CC0/PD/CC-BY results pass; NC/ND/SA/unknown are rejected), yt-dlp only on allowlisted domains and only if the page itself declares CC-BY/CC0. Attribution is written to `meta-<n>.json` and must go into the caption. Commercial songs are never fetched.
- Daily prefetch (`.github/workflows/fetch-songs.yml`, `python -m pipeline songs`): songs from `queue.md` + the KZ chart are searched in Openverse, Jamendo, Internet Archive and SoundCloud (official APIs, license in `licenses_allowed`; SoundCloud also needs the uploader's download flag). Remixes, covers, previews (<90 s) and a wrong title/artist/length are refused; the full track goes through `check_audio`, becomes an MP3 and goes to Drive/audio with its `.license.json` (attribution reaches the caption). No match = the song is skipped and written to the journal `Drive/state/fetch.json` (retried after 14 days). Commercial catalogs are not searched, YouTube/streaming is not ripped. Secrets: `JAMENDO_CLIENT_ID`, `SOUNDCLOUD_CLIENT_ID`, optional `YOUTUBE_API_KEY` (chart).
- Official previews (`pipeline songs --previews`, queue.md songs only): when no licensed full file exists, the 30 s promo clip that Apple Music / Deezer publish through their public APIs is saved to Drive/audio with a `.license.json` marked `analysis_only`. It is used ONLY to time the lyrics: `batch` refuses such a file in mode `auto` (it would put the clip into a video) and in mode `tiktok` the video is silent, the official sound is added in the TikTok app. The preview starts at an unknown point of the song, so `sync.txt` says to align the sound by ear. Terms of use of the clips were not reviewed.
- The workflow guard (`pipeline songs --check-list`) stops `generate` if Drive/audio holds a song that is not in queue.md.
- Standing rights declaration: `VYBEX_OWNER_DECLARES_RIGHTS=1` in the workflow env covers files the owner puts in Drive/audio. It is set once and is never asked for again, per song or per run. It does not turn a source that forbids downloading (YouTube, streaming, paid stores) into an allowed one: for such songs the job writes the reason to `Drive/state/songs.md` (`skipped`) and goes on to the next song.
- Known risk (state once to the owner, do not repeat in outputs): TikTok may mute, restrict or claim videos with commercial tracks. The built-in TikTok sound library is the zero-risk alternative: set `mode: commentary` (no audio in file) and add the sound in the app when confirming the post.
- Mode `tiktok`: the audio file is used only for local analysis (lyrics timing, beats, chorus); it is not mixed into the video and not uploaded anywhere. The official sound is added inside TikTok.
- Any legally obtained mp4/mov/mkv/webm is converted to audio with ffmpeg (`download.ensure_audio`). A local video needs an entry in `audio/sources.json` (or `--i-have-rights`); a video from a verified CC download inherits its license sidecar.
- Fallback `commentary`: silent video, our own text about the meaning.

## Lyrics
- Lyric text on cards comes from `pipeline/analyze.py` (faster-whisper word timestamps on the supplied file), never from memory. Low-confidence words are kept, counted and flagged; QA fails a video with more than 15% of them (the owner then edits the words or skips the song).
- Show only the chosen 30–60 s fragment (the most recognisable part, see `docs/video-spec.md`), not the whole song.
- In `commentary` mode: no quotes from memory unless certain; paraphrase.

## Images and fonts
- Default: no third-party images. Visuals are React/SVG drawn in `remotion/src/widgets/`; fonts are Google Fonts (Montserrat, OFL) loaded by Remotion.
- Third-party image only if CC0/clearly permissive, recorded in `assets/credits.json` (`{file, source_url, license, author}`); QA check #10 fails without it.
- No cover art, artist photos, logos, clip screenshots.

## AI label
Since 2026-11-10 the owner publishes WITHOUT the AI label: no text note, no `aiAssisted`/`isAiGenerated` flags, no reminders in `caption.txt`, the steps or the run summary. This is the owner's decision; TikTok's rules still ask to label realistic AI-generated content, and the risk is the owner's. The spec field `ai_label` stays as an internal marker.

## Publishing (official only)
- `inbox`: `POST /v2/post/publish/inbox/video/init/` (scope `video.upload`, no audit). Video lands in the creator's inbox; owner finishes the post. Caption is not sendable via this API: it is stored in the Release as `caption.txt` and shown in the run summary. Limit: 5 pending shares / 24 h.
- `direct`: `POST /v2/post/publish/video/init/` (scope `video.publish`). Unaudited app => private posts only. Switch via `publish_mode` in `config.json` after audit.
- `manual`: no API; owner downloads from the Release.
- Browser automation / password login: not used.

## Storage and cleanup
Videos + `meta.json` (caption, hashtags, slot) go to GitHub Release `d-<date>` in the private repo. Audio files in `accounts/main/audio/` live in the repo (private) and are never put in the Release. After confirmed publish/inbox success: delete the Release assets, append to `log.md`, remove the song from `queue.md`. Delete nothing before upload is confirmed.

## Secrets
GitHub Secrets only: `CLAUDE_CODE_OAUTH_TOKEN`, `TIKTOK_CLIENT_KEY`, `TIKTOK_CLIENT_SECRET`, `TIKTOK_REFRESH_TOKEN`. Never echo them.
