"""python -m pipeline <stage> ...   Independent stages: fetch -> analyze -> render, or batch for all of it."""
import json
import sys

USAGE = """stages:
  fetch "<artist> <title>"     search allowed sources, download, extract audio from video files
  analyze <audio> [--popular "line"] [--lang ru] -o analysis.json
  render out/<date> [--only N]   (= pipeline.build)
  batch --mode auto|tiktok --count 3 [--date D] [--lang ru]
  buffer setup | publish out/<date>   send ready videos to the Buffer TikTok queue (docs/buffer.md)
  trends                          TikTok trends from official/permitted data
  ideas [--have-file f] [-o out/ideas.md]   song ideas from the YouTube music chart (needs YOUTUBE_API_KEY) -> Drive/ideas.md
  songs [--out out/fetched] [--max 5]   daily: queue + KZ chart -> licensed full tracks (cc0/pd/by) -> mp3 + journal (workflow uploads to Drive)
  insights [--acc main]          views by card recipe (accounts/<acc>/cards.jsonl + views.csv)
"""


def main(argv):
    if not argv or argv[0] in ("-h", "--help"):
        print(USAGE)
        return 0
    cmd, rest = argv[0], argv[1:]
    if cmd == "fetch":
        from . import batch, common
        cfg = common.load_config()
        q = " ".join(rest)
        entry = {"artist": q, "title": "", "popular_line": "", "audio_file": ""}
        path, sts = batch.fetch_audio(entry, cfg, "auto")
        print(json.dumps({"audio": str(path) if path else None, "statuses": sts}, ensure_ascii=False, indent=1))
        return 0 if path else 1
    if cmd == "analyze":
        import argparse
        from . import analyze, common
        ap = argparse.ArgumentParser(prog="pipeline analyze")
        ap.add_argument("audio")
        ap.add_argument("--popular", default="")
        ap.add_argument("--lang")
        ap.add_argument("-o", default="analysis.json")
        a = ap.parse_args(rest)
        cfg = common.load_config()
        if a.lang:
            cfg["language"] = a.lang
        res = analyze.analyze(a.audio, a.popular, cfg)
        open(a.o, "w", encoding="utf-8").write(json.dumps(res, ensure_ascii=False))
        print(json.dumps(res["summary"], ensure_ascii=False))
        return 0
    if cmd == "render":
        from . import build
        build.main(rest)
        return 0
    if cmd == "batch":
        from . import batch
        return batch.main(rest)
    if cmd == "buffer":
        from . import buffer_publisher
        return buffer_publisher.main(rest)
    if cmd == "trends":
        from . import tiktok_trends
        print(json.dumps(tiktok_trends.fetch_trends(), ensure_ascii=False, indent=1))
        return 0
    if cmd == "ideas":
        from . import song_ideas
        return song_ideas.main(rest)
    if cmd == "songs":
        from . import fetch_songs
        return fetch_songs.main(rest)
    if cmd == "insights":
        from . import insights
        return insights.main(rest)
    print(USAGE)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
