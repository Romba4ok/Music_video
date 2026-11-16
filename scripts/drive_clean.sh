#!/usr/bin/env bash
# Drive cleanup, used by generate.yml (end of a run) and drive-clean.yml (manual button). Needs rclone remote "gd" and python.
# Order matters: the memory is saved to Drive/state/songs.md BEFORE anything is deleted. Deleted files go to the Drive trash (~30 days).
# FORCE=1 cleans even when songs are still waiting in Drive/audio (those songs are never touched).
set -eo pipefail
mkdir -p out
if [ "${FORCE:-0}" != "1" ] && [ -n "$(rclone lsf gd:audio | grep -iE '\.(mp3|wav|m4a|ogg|flac|mp4|mov|mkv|webm|m4v)$' || true)" ]; then
  echo "Songs are still in Drive/audio: nothing to clean"; exit 0
fi
ROOT_LS=$(rclone lsf gd:)
if echo "$ROOT_LS" | grep -qx 'state/' && rclone lsf gd:state | grep -qx 'songs.md'; then rclone copyto gd:state/songs.md out/songs-memory.md
else cp accounts/main/songs-memory.md out/songs-memory.md; fi
: > out/done.txt
if echo "$ROOT_LS" | grep -qx 'done/'; then rclone lsf gd:done | grep -v '/$' > out/done.txt || true; fi
python -m pipeline songs --state out/songs-memory.md --record-used out/done.txt
rclone copyto out/songs-memory.md gd:state/songs.md   # saved BEFORE the deletes below
# attribution files whose song is no longer in Drive/audio
rclone lsf gd:audio | grep -v '/$' > out/audio-now.txt || true
while read -r f; do
  case "$f" in *.license.json) grep -qxF "${f%.license.json}" out/audio-now.txt || rclone deletefile "gd:audio/$f" ;; esac
done < out/audio-now.txt
if [ -s out/done.txt ]; then rclone delete gd:done; fi
if echo "$ROOT_LS" | grep -qx 'ready/'; then rclone rmdirs gd:ready --leave-root; fi   # only EMPTY date folders (sent videos are deleted by buffer drive-cleanup; unsent drafts stay)
echo "Drive cleaned: $(wc -l < out/done.txt) processed songs remembered in Drive/state/songs.md, Drive/done emptied, empty Drive/ready folders removed. Songs still waiting in Drive/audio: $(grep -ciE '\.(mp3|wav|m4a|ogg|flac|mp4|mov|mkv|webm|m4v)$' out/audio-now.txt || true)" | tee -a "${GITHUB_STEP_SUMMARY:-/dev/null}"
