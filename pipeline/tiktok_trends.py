"""TikTok trend analysis from OFFICIAL / permitted data only. No scraping, no browser, no logins.

Chain (config trends.order), each reports an honest status:
  research : TikTok Research API  — needs approved Research API access (TIKTOK_CLIENT_KEY/SECRET). Not verified against the
             live API (no access here); eligibility is limited by TikTok (researchers in some regions).
  local    : data/trends.json written by the owner (e.g. copied from TikTok Creative Center, which has no API).
Separate: own_stats() — your own videos' stats via the Display API (needs TIKTOK_ACCESS_TOKEN with video.list).
"""
import json
import os
import time
from collections import Counter
from pathlib import Path

import requests

from .common import ROOT, NeedsAuth, load_config, safe_err, status

API = "https://open.tiktokapis.com"
FIELDS = "id,video_description,hashtag_names,view_count,like_count,comment_count,share_count,music_id,video_duration,region_code"


def summarize_videos(videos, top=15):
    """Pure aggregation: hashtags weighted by views, duration stats, popular sounds."""
    tags, music, durs = {}, Counter(), []
    for v in videos:
        views = v.get("view_count") or 0
        for t in v.get("hashtag_names") or []:
            d = tags.setdefault(t.lower(), {"tag": t.lower(), "videos": 0, "views": 0})
            d["videos"] += 1
            d["views"] += views
        if v.get("music_id"):
            music[str(v["music_id"])] += 1
        if v.get("video_duration"):
            durs.append(v["video_duration"])
    durs.sort()
    return {
        "videos_analyzed": len(videos),
        "hashtags": sorted(tags.values(), key=lambda d: (-d["views"], -d["videos"]))[:top],
        "music_ids": [{"music_id": k, "videos": n} for k, n in music.most_common(top)],
        "duration_sec": {"median": durs[len(durs) // 2], "min": durs[0], "max": durs[-1]} if durs else None,
    }


def _research(cfg, env, http=requests):
    key, secret = env.get("TIKTOK_CLIENT_KEY"), env.get("TIKTOK_CLIENT_SECRET")
    if not (key and secret):
        raise NeedsAuth("Research API needs approved access + TIKTOK_CLIENT_KEY/TIKTOK_CLIENT_SECRET")
    tok = http.post(f"{API}/v2/oauth/token/", data={"client_key": key, "client_secret": secret,
                    "grant_type": "client_credentials"}, timeout=20)
    if tok.status_code in (401, 403):
        raise NeedsAuth("token refused: app has no Research API access")
    tok.raise_for_status()
    access = tok.json().get("access_token")
    if not access:
        raise NeedsAuth("no access_token returned")
    days = min(cfg["trends"]["days"], 30)
    end = time.strftime("%Y%m%d", time.gmtime())
    start = time.strftime("%Y%m%d", time.gmtime(time.time() - days * 86400))
    body = {"query": {"and": [{"operation": "EQ", "field_name": "region_code", "field_values": [cfg["trends"]["region"]]}]},
            "start_date": start, "end_date": end, "max_count": 100}
    r = http.post(f"{API}/v2/research/video/query/", params={"fields": FIELDS}, json=body,
                  headers={"Authorization": f"Bearer {access}"}, timeout=30)
    if r.status_code in (401, 403):
        raise NeedsAuth("Research API query not permitted for this app")
    r.raise_for_status()
    return r.json().get("data", {}).get("videos", [])


def _local(cfg, env, http=None):
    p = ROOT / cfg["trends"]["local_file"]
    if not p.exists():
        raise FileNotFoundError("no local trends file")
    return json.loads(p.read_text(encoding="utf-8"))


def fetch_trends(cfg=None, env=None, http=requests, sources=None):
    cfg = cfg or load_config()
    env = os.environ if env is None else env
    sources = sources or {"research": _research, "local": _local}
    sts, result = [], {"hashtags": [], "music_ids": [], "duration_sec": None, "songs": [], "notes": ""}
    for name in cfg["trends"]["order"]:
        try:
            data = sources[name](cfg, env, http)
        except NeedsAuth as e:
            sts.append(status(name, "needs_auth", str(e)))
            continue
        except FileNotFoundError as e:
            sts.append(status(name, "empty", str(e)))
            continue
        except Exception as e:
            sts.append(status(name, "unavailable", safe_err(e)))
            continue
        if isinstance(data, list):  # Research API videos
            result.update(summarize_videos(data))
        else:  # owner-supplied json: {"hashtags": [...], "songs": [...], "notes": "..."}
            for k in ("hashtags", "songs", "notes", "music_ids", "duration_sec"):
                if data.get(k):
                    result[k] = data[k]
        sts.append(status(name, "ok"))
        break
    result["statuses"] = sts
    return result


def own_stats(env=None, http=requests):
    """Your own recent videos (Display API, scope video.list). Feedback loop for which formats work."""
    env = os.environ if env is None else env
    tok = env.get("TIKTOK_ACCESS_TOKEN")
    if not tok:
        return {"status": status("display_api", "needs_auth", "set TIKTOK_ACCESS_TOKEN (user token with video.list)")}
    try:
        r = http.post(f"{API}/v2/video/list/", params={"fields": "id,title,view_count,like_count,duration"},
                      json={"max_count": 20}, headers={"Authorization": f"Bearer {tok}"}, timeout=20)
        r.raise_for_status()
        return {"status": status("display_api", "ok"), "videos": r.json().get("data", {}).get("videos", [])}
    except Exception as e:
        return {"status": status("display_api", "unavailable", safe_err(e))}


if __name__ == "__main__":
    print(json.dumps(fetch_trends(), ensure_ascii=False, indent=1))
