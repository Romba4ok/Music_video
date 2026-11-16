"""Song ideas for the owner: YouTube's official "most popular music" chart for a region -> ideas.md (uploaded to Drive by the workflow).
This is NOT a TikTok chart (TikTok has no public one); it is the closest free official signal. The owner reads the file and drops audio into Drive/audio.
python -m pipeline ideas [--have-file names.txt] [-o out/ideas.md]   needs env YOUTUBE_API_KEY (YouTube Data API v3, free quota)
"""
import argparse
import os
import re
import sys
import time

from .common import NeedsAuth, get_json, load_config, safe_err

API = "https://www.googleapis.com/youtube/v3/videos"


def _key(s):
    return re.sub(r"[\W_]+", "", s.lower())


def clean_title(t):
    return re.sub(r"\s*[\(\[][^\)\]]*[\)\]]", "", t).strip(" -|")  # drops "(Official Video)", "[4K]"


def pick(items, have=(), top=20):
    """Pure: API items -> [{title, channel, views, url}] without songs already in `have` (file stems)."""
    have = [k for k in (_key(h) for h in have) if len(k) > 3]
    out = []
    for it in items:
        title = clean_title(it["snippet"]["title"])
        k = _key(title)
        if not k or any(h in k or k in h for h in have):
            continue
        out.append({"title": title, "channel": it["snippet"]["channelTitle"],
                    "views": int(it.get("statistics", {}).get("viewCount", 0)), "sec": 0,
                    "url": f"https://youtu.be/{it['id']}"})
    return out[:top]


def render_md(rows, region, status="ok"):
    head = f"# Идеи песен ({region}) - {time.strftime('%Y-%m-%d', time.gmtime())}\n\n" \
           "Источник: чарт YouTube «Популярная музыка» (официальный API) или, без ключа, неофициальный чарт KZ в Deezer; не TikTok. Бери то, что подходит по вкусу, " \
           "и клади `Артист - Название.mp3` в Drive/audio.\n\n"
    if status != "ok":
        return head + f"Сегодня данных нет: {status}\n"
    lines = [f"{i}. **{r['title']}** - {r['channel']}{f", {r['views']:,} просм." if r['views'] else ""} [ссылка]({r['url']})".replace(",", " ")
             for i, r in enumerate(rows, 1)]
    return head + "\n".join(lines) + "\n"


# shortcut: unofficial user-made copy of a KZ chart (no official keyless one exists), may vanish; upgrade: set YOUTUBE_API_KEY
DEEZER_KZ = "https://api.deezer.com/playlist/14867126923"


def fetch_deezer(http_get=get_json):
    """No-key fallback: same row shape as pick(); `views` is 0 (the playlist has no counts), order = chart order."""
    return [{"title": f"{t['artist']['name']} - {t['title']}", "channel": "Deezer (неофициальный чарт KZ)", "views": 0, "url": t["link"], "sec": t.get("duration", 0)}
            for t in http_get(DEEZER_KZ)["tracks"]["data"]]


def fetch(region, key, http_get=get_json):
    d = http_get(API, params={"part": "snippet,statistics", "chart": "mostPopular", "videoCategoryId": "10",
                              "regionCode": region, "maxResults": 50, "key": key})
    return d.get("items", [])


def main(argv):
    ap = argparse.ArgumentParser(prog="pipeline ideas")
    ap.add_argument("--have-file", help="text file, one existing audio/done name per line (skipped in the list)")
    ap.add_argument("-o", default="out/ideas.md")
    a = ap.parse_args(argv)
    region = load_config().get("trends", {}).get("region", "KZ")
    have = []
    if a.have_file and os.path.exists(a.have_file):
        have = [os.path.splitext(l.strip())[0] for l in open(a.have_file, encoding="utf-8") if l.strip()]
    try:
        key = os.environ.get("YOUTUBE_API_KEY")
        if key:
            rows = pick(fetch(region, key), have)
        else:
            hk = [k for k in (_key(h) for h in have) if len(k) > 3]
            rows = [r for r in fetch_deezer() if not any(h in _key(r["title"]) for h in hk)][:50]
            print("ideas: YOUTUBE_API_KEY not set, using the unofficial Deezer KZ chart", file=sys.stderr)
        md = render_md(rows, region)
    except Exception as e:  # optional feature: report in the file, never break the video job
        why = str(e) if isinstance(e, NeedsAuth) else safe_err(e)
        md = render_md([], region, status=why)
        print("ideas:", why, file=sys.stderr)
    os.makedirs(os.path.dirname(a.o) or ".", exist_ok=True)
    open(a.o, "w", encoding="utf-8").write(md)
    print(md)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
