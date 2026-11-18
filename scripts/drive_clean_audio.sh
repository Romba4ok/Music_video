#!/usr/bin/env bash
# After a generate run: delete from Drive/audio every file whose song the batch LOOKED AT (built, refused, failed QA) plus its .license.json.
# Songs the batch never reached (count limit) stay. Nothing is deleted when report.json is missing (batch crashed / cancelled).
# Deleted files go to the Drive trash (~30 days). Usage: drive_clean_audio.sh out/<date>/report.json
set -eo pipefail
REPORT="$1"
[ -f "$REPORT" ] || { echo "no report.json: Drive/audio is left as it is" | tee -a "${GITHUB_STEP_SUMMARY:-/dev/null}"; exit 0; }
mkdir -p out
rclone lsf gd:audio | grep -v '/$' | grep -v '\.license\.json$' > out/audio-before.txt || true
python - "$REPORT" out/audio-before.txt > out/audio-delete.txt <<'PY'
import json, os, sys
from pipeline.common import parse_name
from pipeline.fetch_songs import key
rep = json.load(open(sys.argv[1], encoding="utf-8"))
seen = {key(*[x.strip() for x in s["song"].split(" — ", 1)]) for s in rep["songs"] if " — " in s["song"]}
seen |= {key(*parse_name(os.path.splitext(s["audio_name"])[0])) for s in rep["songs"] if s.get("audio_name")}
for f in open(sys.argv[2], encoding="utf-8").read().splitlines():
    if f.strip() and key(*parse_name(os.path.splitext(f)[0])) in seen:
        print(f)
PY
n=0
while read -r f; do
  [ -z "$f" ] && continue
  rclone deletefile "gd:audio/$f" && n=$((n+1))
  rclone deletefile "gd:audio/$f.license.json" 2>/dev/null || true
done < out/audio-delete.txt
echo "exit code: Drive/audio cleanup deleted $n file(s); left in Drive/audio: $(( $(wc -l < out/audio-before.txt) - n ))" | tee -a "${GITHUB_STEP_SUMMARY:-/dev/null}"
sed 's/^/  deleted: /' out/audio-delete.txt | tee -a "${GITHUB_STEP_SUMMARY:-/dev/null}"
