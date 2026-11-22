"""Refill an AUTO batch from its Drive queue after an unreliable transcription."""
import argparse
import json
import os
import shutil
import subprocess
import time
from pathlib import Path

from . import fetch_songs
from .batch import parse_queue


def rclone(*args):
    return subprocess.run(["rclone", *args], check=True, stdout=subprocess.PIPE,
                          text=True, encoding="utf-8").stdout


class DriveReplacements:
    def __init__(self, root, cfg):
        self.account = root / "accounts" / "main"
        self.audio = root / cfg["audio_dir"]
        self.work = root / "out" / "audio-replacements"
        self.queue = self.account / "queue.md"
        self.state = self.work / "songs-memory.md"
        self.have = self.work / "have.txt"
        self.checked = set()
        self.initialized = False
        # The generate job has 90 minutes, including rendering and Buffer.
        self.stop_at = time.monotonic() + 55 * 60

    def prepare(self):
        self.work.mkdir(parents=True, exist_ok=True)
        folders = rclone("lsf", "gd:", "--dirs-only").splitlines()
        if "state/" in folders and "songs.md" in rclone("lsf", "gd:state", "--files-only").splitlines():
            rclone("copyto", "gd:state/songs.md", self.state)
        else:
            shutil.copyfile(self.account / "songs-memory.md", self.state)
        done = rclone("lsf", "gd:done", "--files-only") if "done/" in folders else ""
        existing = [p.name for p in self.audio.iterdir() if p.is_file()]
        self.have.write_text("\n".join(done.splitlines() + existing), encoding="utf-8")
        self.initialized = True

    def __call__(self, missing, attempted_audio):
        if time.monotonic() >= self.stop_at:
            return []
        if not self.initialized:
            self.prepare()
        self.checked.update(fetch_songs.key(*song) for song in attempted_audio)
        args = fetch_songs.arguments(["--download-only", "--queue", str(self.queue), "--out", str(self.audio),
                                      "--state", str(self.state), "--have-file", str(self.have), "--max", str(missing)])
        print(f"low_confidence: searching the queue for {missing} more track(s)", flush=True)
        names = fetch_songs.run(args, replacement_attempts=self.checked, stop_at=self.stop_at)
        rows = {row["file"]: key for key, row in fetch_songs.load_memory(self.state)["done"].items()}
        entries = {fetch_songs.key(e["artist"], e["title"]): e
                   for e in reversed(parse_queue(self.queue.read_text(encoding="utf-8")))}
        extra = []
        for name in names:
            entry = dict(entries[rows[name]], audio_file=name)
            # Upload the sidecar first so an interrupted transfer cannot leave an unmarked track.
            for filename in (name + ".license.json", name):
                rclone("copyto", self.audio / filename, "gd:audio/" + filename)
            extra.append(entry)
            print(f"low_confidence replacement: {entry['artist']} — {entry['title']}", flush=True)
        rclone("copyto", self.state, "gd:state/songs.md")
        return extra


def verify(report, buffer_mode):
    if report["mode"] != "auto" or buffer_mode not in ("now", "queue"):
        return True
    if not any(row["stages"].get("analyze") == "low_confidence" for row in report["songs"]):
        return True
    receipts = {post["post_id"] for row in report["songs"] if (post := row.get("buffer") or {}).get("post_id")
                and post.get("state") in ("posting", "scheduled", "notify")}
    print(f"After low_confidence: Buffer accepted {len(receipts)}/{report['requested']} unique posts.")
    return len(receipts) == report["requested"]


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verify", type=Path, required=True)
    report = json.loads(parser.parse_args().verify.read_text(encoding="utf-8"))
    raise SystemExit(0 if verify(report, os.environ.get("VYBEX_BUFFER")) else 1)
