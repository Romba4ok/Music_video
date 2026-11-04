# HyperFrames cheat sheet (replaces reading the skill; only needed when editing `template/`)

HyperFrames = HTML seeked frame by frame by a paused GSAP timeline -> deterministic MP4. CLI: `npx hyperframes <cmd>`. Replaces Puppeteer + manual ffmpeg assembly from the original ТЗ.

## Commands
- `npx hyperframes check --json` — lint; every error has a `Fix:` line. Run after every template edit.
- `npx hyperframes render -o out.mp4 --variables-file vars.json [--fps 30] [--quality looks|delivery]` — `looks` (CRF 16) is enough for TikTok.
- `npx hyperframes snapshot` — still frames (use only with `--debug-visual`).
- `npx hyperframes browser ensure` — download pinned Chrome (CI first step). Needs Node >= 22 and ffmpeg/ffprobe.
- Read the render summary's 2nd line; on Linux it shows capture path (software GL is expected on Actions).

## Contract (violations = lint errors)
1. Every timed element: `class="clip"`, `data-start`, `data-duration` (seconds). Visible in `[start, start+duration)`.
2. Video length = root `data-duration`.
3. Each composition builds ONE paused GSAP timeline and registers it: `window.__timelines["<composition-id>"] = tl`.
4. No `Date.now()`, unseeded `Math.random()`, fetch, timers, `repeat:-1`. Everything is a function of timeline time.
5. Never tween `display`/`visibility`/`autoAlpha` on a `.clip`; animate a child.
6. No CSS `transform` on an element GSAP transforms; use GSAP x/y/scale/rotation, not left/top/width/height.
7. Never play/pause/seek media. `<audio>` needs an `id`; no `crossorigin`.
8. Fonts: only bundled families by name; otherwise `@font-face` to `assets/fonts/` (relative path, no leading `/`).
9. Scene file: styles + markup + scripts inside `<template>`, root styled as `#root`.
10. Grades/grain/blur on footage via `media-treatment`, not CSS filters (we use no footage).
11. Copy and colours are variables: `data-composition-variables` on `<html>` (JSON array of `{id,type,label,default}`), read with `window.__hyperframes.getVariables()`; overridden per render by `--variables-file` (JSON object by id).

## Vertical rules
1080x1920. Text inside y 168–1330 and 90% action-safe box; below 1330 only decoration; nothing under the right rail. Frame 0 is the thumbnail and hook (never black). Text ≥ 56 px here, max ~5–7 words per line. New beat every 2–4 s.

## Template plan (`template/`)
`index.html` = root: variables (`scenes[]`, `palette`, `duration`) + mounts `compositions/<metaphor>.html` per scene by spec role/time. One composition per metaphor in `docs/video-spec.md`; palettes as CSS variables. Add a new metaphor only by new file + one line in the spec doc; never per-video HTML.
