#!/usr/bin/env bash
# After a generate run: EMPTY Drive/audio completely (every song and .license.json), whether or not a video was built from it.
# Nothing is deleted when report.json is missing (batch crashed / cancelled before it started: the songs were never tried).
# Deleted files go to the Drive trash (~30 days). Usage: drive_clean_audio.sh out/<date>/report.json
set -eo pipefail
REPORT="$1"
[ -f "$REPORT" ] || { echo "no report.json: Drive/audio is left as it is" | tee -a "${GITHUB_STEP_SUMMARY:-/dev/null}"; exit 0; }
mkdir -p out
rclone lsf gd:audio | grep -v '/$' > out/audio-delete.txt || true
rclone delete gd:audio
echo "exit code: Drive/audio emptied, deleted $(wc -l < out/audio-delete.txt) file(s)" | tee -a "${GITHUB_STEP_SUMMARY:-/dev/null}"
sed 's/^/  deleted: /' out/audio-delete.txt | tee -a "${GITHUB_STEP_SUMMARY:-/dev/null}"
