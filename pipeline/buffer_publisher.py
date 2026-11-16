"""Hands finished videos to Buffer (official GraphQL API, https://developers.buffer.com): 3 posts a day at fixed local times.

Per video: rights gate -> media checks (ffprobe + full decode) -> already sent? (sha256 in state) -> upload to a temporary Cloudinary
folder (Buffer needs a public HTTPS URL) -> check the URL like Buffer will -> createPost -> state + report.json.
Modes (VYBEX_BUFFER env/variable, else config buffer.mode; anything unknown = off):
  off    nothing        plan   read-only: checks, free slots, nothing uploaded or created
  draft  Buffer draft   queue  customScheduled post at the next free slot (12:00/17:00/21:00 Asia/Almaty); silent videos (mode tiktok) are NOT sent (state awaiting_audio)
                               unless config buffer.silent = publish | notify (reminder to add the sound by hand)
  now    shareNow: the post is published to the account right away (no slot, no queue); nothing is spread over the day
The Buffer posting schedule cannot be written through the API, so slots are set per post (`dueAt`, UTC). Existing drafts are never edited.
Hosted files must live until Buffer posts them (it fetches at publish time) and are deleted by age. The MP4 in ready/ is never touched.
Secrets only from env: BUFFER_API_KEY, CLOUDINARY_CLOUD_NAME/API_KEY/API_SECRET.

python -m pipeline buffer setup | check | publish out/<date> | summary out/<date> [--state out/buffer-state.json]"""
import hashlib
import json
import os
import re
import subprocess
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import requests

from .common import ROOT, load_config, safe_err

API = "https://api.buffer.com"
MODES = ("off", "plan", "draft", "queue", "now")
MAX_TEXT = 2200  # TikTok caption limit
DEFAULT_SLOTS = ["12:00", "17:00", "21:00"]

Q_ORGS = "query { account { organizations { id name } } }"
Q_CHANNELS = ("query($o: OrganizationId!) { channels(input: {organizationId: $o}) "
              "{ id name displayName service isQueuePaused isDisconnected isLocked timezone } }")
M_POST = """mutation($input: CreatePostInput!) { createPost(input: $input) {
  ... on PostActionSuccess { post { id } }
  ... on MutationError { message } } }"""


class BufferError(Exception):
    pass


class Ambiguous(BufferError):
    """The request may have been processed (5xx / read timeout): never blindly repeated, first look in Buffer."""


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def mode_of(cfg, env=os.environ):
    m = (env.get("VYBEX_BUFFER") or cfg.get("buffer", {}).get("mode") or "off").strip().lower()
    return m if m in MODES else "off"  # a typo must never turn into real publishing


def caption_for(txt):
    """caption.txt minus the human reminder about the AI label (the label is sent as a flag instead)."""
    paras = [p for p in txt.strip().split("\n\n") if not p.startswith("Включите")]
    return "\n\n".join(paras)[:MAX_TEXT]


def parse_dt(s):
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


# ---------- Buffer API ----------

class Buffer:
    def __init__(self, key, post=requests.post, sleep=time.sleep):
        self.key, self._post, self._sleep = key, post, sleep

    def gql(self, query, variables=None, repeatable=True):
        """repeatable=False for createPost: only failures that prove the request was NOT processed are retried."""
        for attempt in range(4):
            last = attempt == 3
            try:
                r = self._post(API, json={"query": query, "variables": variables or {}}, timeout=60,
                               headers={"Authorization": f"Bearer {self.key}", "Content-Type": "application/json"})
            except requests.RequestException as e:
                if repeatable or isinstance(e, requests.ConnectTimeout):  # a connect timeout means nothing was sent
                    if not last:
                        self._sleep(3 * (attempt + 1))
                        continue
                    raise BufferError(f"network: {safe_err(e)}")
                raise Ambiguous(f"network: {safe_err(e)}")
            if r.status_code in (429, 502, 503, 504) and not last:  # not processed (rate limit / gateway) -> safe to repeat
                self._sleep(5 * (attempt + 1))
                continue
            if r.status_code >= 500 and repeatable and not last:
                self._sleep(5 * (attempt + 1))
                continue
            if r.status_code >= 500:
                raise (BufferError if repeatable else Ambiguous)(f"HTTP {r.status_code}")
            if r.status_code != 200:
                raise BufferError(f"HTTP {r.status_code}")
            body = r.json()
            if body.get("errors"):
                raise BufferError("; ".join(str(e.get("message", e))[:150] for e in body["errors"][:2]))
            return body["data"]
        raise BufferError("unreachable")

    def tiktok_channels(self):
        out = []
        for org in self.gql(Q_ORGS)["account"]["organizations"]:
            for ch in self.gql(Q_CHANNELS, {"o": org["id"]})["channels"]:
                if str(ch.get("service", "")).lower() == "tiktok":
                    out.append({"id": ch["id"], "name": ch.get("displayName") or ch.get("name"), "org": org["id"],
                                "paused": ch.get("isQueuePaused"), "disconnected": ch.get("isDisconnected"),
                                "locked": ch.get("isLocked"), "timezone": ch.get("timezone")})
        return out

    def scheduled(self, org, channel_id):
        """All posts of the channel in status `scheduled` (drafts are not included, so drafts are never touched). -> [{id,text,dueAt}]"""
        out, after = [], None
        for _ in range(20):
            q = ("query($first: Int, $after: String) { posts(first: $first, after: $after, input: {organizationId: %s, "
                 "filter: {status: [scheduled], channelIds: [%s]}}) { edges { node { id text dueAt } } pageInfo { hasNextPage endCursor } } }"
                 % (json.dumps(org), json.dumps(channel_id)))
            d = self.gql(q, {"first": 50, "after": after})["posts"]
            out += [e["node"] for e in d["edges"]]
            if not d["pageInfo"]["hasNextPage"]:
                return out
            after = d["pageInfo"]["endCursor"]
        raise BufferError("more than 1000 scheduled posts")

    def post_status(self, post_id):
        q = "query { post(input: {id: %s}) { id status dueAt sentAt externalLink error { message } } }" % json.dumps(post_id)
        return self.gql(q)["post"]

    def create_post(self, channel_id, text, url, mode, due=None, notify=False):
        inp = {"text": text, "channelId": channel_id, "schedulingType": "notification" if notify else "automatic",
               "mode": "shareNow" if mode == "now" else ("customScheduled" if due else "addToQueue"),
               "assets": [{"video": {"url": url, "metadata": {"thumbnailOffset": 2000}}}]}
        if due:
            inp["dueAt"] = due.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")
        if mode == "draft":
            inp["saveToDraft"] = True
        res = self.gql(M_POST, {"input": inp}, repeatable=False)["createPost"]
        if "post" not in res:
            raise BufferError(res.get("message", "createPost failed")[:200])
        return res["post"]["id"]


def resolve_channel(buf, bcfg, mode):
    chs = buf.tiktok_channels()
    want = bcfg.get("channel_id")
    ch = next((c for c in chs if c["id"] == want), None) if want else (chs[0] if len(chs) == 1 else None)
    if not ch:
        raise BufferError(f"TikTok channel {'id ' + want if want else '(expected exactly 1)'} not found among {len(chs)}; run `python -m pipeline buffer setup`")
    if ch["disconnected"] or ch["locked"]:
        raise BufferError("TikTok channel is disconnected or locked in Buffer: reconnect it")
    if ch["paused"] and mode == "queue":
        raise BufferError("the channel queue is paused in Buffer: posts would not be published")
    return ch


# ---------- temporary public host ----------

class Cloudinary:
    """Public id = sha256 of the file: unguessable, and the same file always gets the same URL."""

    def __init__(self, cloud, key, secret, post=requests.post):
        self.cloud, self.key, self.secret, self._post = cloud, key, secret, post

    def _sign(self, params):
        s = "&".join(f"{k}={v}" for k, v in sorted(params.items())) + self.secret
        return hashlib.sha1(s.encode()).hexdigest()

    def _call(self, kind, params, files=None):
        params = dict(params, timestamp=int(time.time()))
        data = dict(params, api_key=self.key, signature=self._sign(params))
        try:
            r = self._post(f"https://api.cloudinary.com/v1_1/{self.cloud}/video/{kind}", data=data, files=files, timeout=300)
        except requests.RequestException as e:
            raise BufferError(f"storage network: {safe_err(e)}")
        if r.status_code != 200:
            raise BufferError(f"storage HTTP {r.status_code}")
        return r.json()

    def upload(self, path, public_id):
        with open(path, "rb") as f:
            res = self._call("upload", {"public_id": public_id, "overwrite": "true"}, files={"file": f})
        return res["secure_url"]

    def delete(self, public_id):
        return self._call("destroy", {"public_id": public_id, "invalidate": "true"}).get("result") in ("ok", "not found")


def check_url(url, size, get=requests.head):
    """Buffer's rules: public, direct (no redirect), HTTPS, stable. Verified the way Buffer will request it."""
    if not url.startswith("https://"):
        raise BufferError("media URL is not HTTPS")
    try:
        r = get(url, allow_redirects=False, timeout=30)
    except requests.RequestException as e:
        raise BufferError(f"media URL unreachable: {safe_err(e)}")
    if r.status_code != 200:
        raise BufferError(f"media URL answers HTTP {r.status_code} (must be 200 without redirect)")
    if not r.headers.get("content-type", "").startswith("video/"):
        raise BufferError(f"media URL content-type {r.headers.get('content-type')!r}, expected video/*")
    if int(r.headers.get("content-length", size)) != size:
        raise BufferError("media URL serves a different size than the uploaded file")


# ---------- checks before sending ----------

def check_file(path, bcfg):
    p = Path(path)
    if p.suffix.lower() != ".mp4":
        raise BufferError("only .mp4 is sent")
    mb = p.stat().st_size / 1e6
    lim = bcfg.get("max_mb", 100)  # free Cloudinary accepts up to 100 MB per video; TikTok itself allows far more
    if mb > lim:
        raise BufferError(f"file is {mb:.0f} MB, limit {lim} MB")


class AudioMissing(BufferError):
    """The video has no usable sound track: it is held back (state awaiting_audio), never sent silent."""


def verify_audio(path, video_dur, max_diff=0.5, min_peak_db=-50.0):
    """ffprobe/ffmpeg proof that the MP4 really carries sound: an AAC stream, as long as the video (+-max_diff s), not silence. -> info dict.
    Raises AudioMissing with the reason."""
    from .qa import probe
    a = next((s for s in probe(path).get("streams", []) if s.get("codec_type") == "audio"), None)
    if not a:
        raise AudioMissing("в файле нет звуковой дорожки")
    if a.get("codec_name") != "aac":
        raise AudioMissing(f"звук {a.get('codec_name')}, нужен AAC")
    try:
        adur = float(a.get("duration") or 0)
    except ValueError:
        adur = 0.0
    if abs(adur - video_dur) > max_diff:
        raise AudioMissing(f"звук {adur:.2f} с, видео {video_dur:.2f} с: рассинхрон больше {max_diff} с")
    r = subprocess.run(["ffmpeg", "-v", "info", "-i", str(path), "-vn", "-af", "volumedetect", "-f", "null", "-"], capture_output=True, text=True, encoding="utf-8", errors="replace")
    m = re.search(r"max_volume:\s*(-?[\d.]+) dB", r.stderr or "")
    peak = float(m.group(1)) if m else None
    if peak is None or peak < min_peak_db:
        raise AudioMissing(f"дорожка есть, но это тишина (пик {peak} dB)")
    return {"codec": "aac", "rate": int(a.get("sample_rate") or 0), "channels": a.get("channels"), "duration": round(adur, 2), "peak_db": peak}


def check_media(path, expect_audio, bcfg):
    """MP4 + H.264 + 1080x1920 (+ audio when the video must carry music) + sane duration + decodes without errors. -> info dict."""
    from .qa import probe
    check_file(path, bcfg)
    info = probe(path)
    v = next((s for s in info.get("streams", []) if s.get("codec_type") == "video"), None)
    if not v:
        raise BufferError("no video stream (broken file)")
    if v.get("codec_name") != "h264":
        raise BufferError(f"codec {v.get('codec_name')}, TikTok needs h264")
    if (v.get("width"), v.get("height")) != (1080, 1920):
        raise BufferError(f"resolution {v.get('width')}x{v.get('height')}, expected 1080x1920")
    has_audio = any(s.get("codec_type") == "audio" for s in info["streams"])
    dur = float(info.get("format", {}).get("duration", 0))
    audio = verify_audio(path, dur) if expect_audio else None
    if not 3 <= dur <= bcfg.get("max_sec", 180):
        raise BufferError(f"duration {dur:.1f}s outside 3..{bcfg.get('max_sec', 180)}s")
    r = subprocess.run(["ffmpeg", "-v", "error", "-i", str(path), "-f", "null", "-"], capture_output=True, text=True)
    if r.returncode or r.stderr.strip():
        raise BufferError("file does not decode cleanly: " + r.stderr.strip()[:120])
    return {"duration": round(dur, 1), "audio": has_audio, "audio_info": audio}


def rights_ok(rec, env):
    """Gate: a track from a licence-checked source passes; a file you dropped into Drive passes only with the owner's declaration.
    shortcut: this checks the declaration, it cannot prove the rights themselves."""
    ok = [s for s in rec.get("sources", []) if s.get("state") == "ok"]
    if not ok:
        return False, "no confirmed audio source in the report"
    if all(s.get("source") == "local" for s in ok) and env.get("VYBEX_OWNER_DECLARES_RIGHTS") != "1":
        return False, "owner declaration of rights is missing (VYBEX_OWNER_DECLARES_RIGHTS=1)"
    return True, ""


# ---------- schedule ----------

def slot_config(bcfg, env):
    tz = ZoneInfo(env.get("VYBEX_TIMEZONE") or bcfg.get("timezone") or "Asia/Almaty")
    slots = bcfg.get("slots") or DEFAULT_SLOTS
    try:
        n = int(env.get("VYBEX_POSTS_PER_DAY") or bcfg.get("posts_per_day") or len(slots))
    except ValueError:
        raise BufferError("VYBEX_POSTS_PER_DAY must be a number")
    n = max(1, min(n, len(slots)))  # shortcut: the first N slots are used, not an even spread
    return tz, [tuple(int(x) for x in s.split(":")) for s in slots[:n]]


def free_slots(count, taken, tz, hm, now, margin_min=20, horizon_days=60):
    """Next `count` slots (UTC datetimes) not already used by `taken` posts and not above hm-per-day. Raises when none within the horizon."""
    out, per_day = [], len(hm)
    day0 = now.astimezone(tz).date()
    for d in range(horizon_days):
        day = day0 + timedelta(days=d)
        busy = sum(1 for t in taken + out if t.astimezone(tz).date() == day)
        for h, m in hm:
            if len(out) == count:
                return out
            if busy >= per_day:
                break
            dt = datetime(day.year, day.month, day.day, h, m, tzinfo=tz)
            if dt <= now + timedelta(minutes=margin_min) or any(abs(t - dt) < timedelta(minutes=30) for t in taken + out):
                continue
            out.append(dt.astimezone(timezone.utc))
            busy += 1
    if len(out) < count:
        raise BufferError(f"no free slot within {horizon_days} days")
    return out


# ---------- state ----------

def load_state(path):
    p = Path(path)
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


def save_state(path, st):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(st, ensure_ascii=False, indent=1), encoding="utf-8")


def refresh_statuses(state, buf, now):
    """Ask Buffer what really happened to the queued posts. -> list of problems (error posts, overdue posts)."""
    problems = []
    for sha, e in state.items():
        if e.get("mode") not in ("queue", "now") or not e.get("post_id") or e.get("status") in ("sent", "error"):
            continue
        try:
            p = buf.post_status(e["post_id"])
        except BufferError as ex:
            e["status_note"] = f"status check failed: {str(ex)[:80]}"  # shortcut: the check query is unverified live, a failure is only noted
            continue
        e["status"] = p.get("status", e.get("status"))
        e.pop("status_note", None)
        if e["status"] == "error":
            e["error"] = ((p.get("error") or {}).get("message") or "unknown")[:200]
            problems.append(f"{e.get('file')}: Buffer failed to publish: {e['error']}")
        elif e["status"] in ("scheduled", "sending") and (e.get("due") or e.get("uploaded_at")) and parse_dt(e.get("due") or e["uploaded_at"]) < now - timedelta(hours=1):
            problems.append(f"{e.get('file')}: still '{e['status']}' an hour after its time")
    return problems


def cleanup(state, storage, keep_days, now):
    """Delete hosted files once their post time is over by a day AND they are older than keep_days. Drafts are kept (you may schedule them later)."""
    n = 0
    for e in state.values():
        if not e.get("hosted") or e.get("mode") == "draft":
            continue
        up = parse_dt(e["uploaded_at"])
        ref = parse_dt(e["due"]) if e.get("due") else up
        sent = e.get("status") == "sent" and not e.get("notification")  # published: Buffer has taken the file, the hosted copy is not needed
        if sent or (up < now - timedelta(days=keep_days) and ref < now - timedelta(days=1)):
            try:
                if storage.delete(e["public_id"]):
                    e["hosted"], n = False, n + 1
            except BufferError:
                pass  # tried again at the next run
    return n


def rclone_remove(path):
    """Delete one Drive file (it goes to the Drive trash, kept ~30 days). True also when it is already gone (rclone exit 3 / 4)."""
    return subprocess.run(["rclone", "deletefile", f"gd:{path}"], capture_output=True, text=True).returncode in (0, 3, 4)


def rclone_ls(path):
    r = subprocess.run(["rclone", "lsf", f"gd:{path}"], capture_output=True, text=True)
    return r.stdout.split("\n") if r.returncode == 0 else ([] if r.returncode in (3, 4) else None)


def rclone_purge(path):
    return subprocess.run(["rclone", "purge", f"gd:{path}"], capture_output=True, text=True).returncode in (0, 3)


def drive_cleanup(state, bcfg, now, remove=rclone_remove, ls=rclone_ls, purge=rclone_purge):
    """Once Buffer says a post was SENT to TikTok, delete what belongs to it in Drive: the mp4, caption.txt and sync.txt in ready/<date>/, and that
    folder (with its report.json) when no video is left in it. The source song in done/ is deleted only with buffer.delete_song_after_sent.
    Notification-only posts (silent videos you publish by hand) and drafts are never touched. Only exact paths recorded for a sent post are deleted.
    A failure is kept in the state (`drive_note`) and retried at the next run. -> (deleted_count, problems)."""
    n, problems, dirs, listed = 0, [], set(), {}

    def gone_or_removed(path):
        """A file that is not in Drive any more (or never existed, like sync.txt of a video with sound) counts as deleted: rclone's exit code for a missing file is not reliable.
        A listing error is NOT 'gone': the entry stays pending and the step stays red."""
        folder, _, name = path.rpartition("/")
        if folder not in listed:
            listed[folder] = ls(folder)
        names = listed[folder]
        if names is None:
            return False
        return name not in {x.strip() for x in names} or remove(path)

    for e in state.values():
        d = e.get("drive")
        if e.get("status") != "sent" or not d or e.get("drive_deleted") or e.get("notification"):
            continue
        paths = [f'{d["dir"]}/{f}' for f in d["files"]]
        if bcfg.get("delete_song_after_sent") and d.get("song"):
            paths.append(f'done/{d["song"]}')
        bad = [p for p in paths if not gone_or_removed(p)]
        if bad:
            e["drive_note"] = "could not delete: " + ", ".join(bad)[:150]
            problems.append(f'{e.get("file")}: {e["drive_note"]}')
            continue
        e["drive_deleted"], n = now.isoformat(), n + 1
        e.pop("drive_note", None)
        dirs.add(d["dir"])
    for d in sorted(dirs):
        left = ls(d)
        if left is not None and not any(x.strip().lower().endswith(".mp4") for x in left):
            purge(d)
    return n, problems


# ---------- publishing ----------

def publish_one(c, mp4, caption, rec, silent):
    """-> result dict for report.json. Never raises."""
    try:
        ok, why = rights_ok(rec, c.env)
        if not ok:
            return {"state": "refused", "detail": why}
        policy = c.bcfg.get("silent", "hold")  # silent video (mode tiktok): hold = never sent, wait for audio | publish | notify (reminder, you add the sound by hand)
        if silent and policy == "hold":
            return {"state": "awaiting_audio", "detail": "ролик без звука не уходит в TikTok: ждёт аудиофайл (mode auto)"}
        notify = bool(silent and policy == "notify")
        info = check_media(mp4, not silent, c.bcfg)
        sha = sha256(mp4)
        old = c.state.get(sha)
        if old and old.get("post_id"):  # the same file is never sent twice, in any mode (a test draft is not re-sent for real either)
            return {"state": "duplicate", "detail": f"already sent as {old['mode']} {old['post_id']}"}
        twin = next((p for p in c.taken_posts if p["text"] == caption), None)
        if twin:  # an earlier attempt reached Buffer although we never saw the answer
            c.state[sha] = {"mode": c.mode, "post_id": twin["id"], "file": Path(mp4).name, "hosted": False, "adopted": True}
            return {"state": "duplicate", "detail": f"already in the Buffer queue as {twin['id']}"}
        due = free_slots(1, c.taken, c.tz, c.hm, c.now)[0] if c.mode in ("queue", "plan") else None
        if c.mode == "plan":
            c.taken.append(due)
            return {"state": "plan", "due": due.astimezone(c.tz).isoformat(), "notification": notify, "media": info}
        pid, size = f"vybex/{sha[:40]}", Path(mp4).stat().st_size
        url = c.storage.upload(mp4, pid)
        base = rec.get("ready") or Path(mp4).stem
        c.state[sha] = {"public_id": pid, "uploaded_at": c.now.isoformat(), "hosted": True, "mode": c.mode, "file": Path(mp4).name,
                        "due": due.isoformat() if due else None,
                        "drive": {"dir": f"ready/{c.date}", "files": [f"{base}.mp4", f"{base} caption.txt", f"{base} sync.txt"], "song": rec.get("audio_name")}}
        check_url(url, size)
        try:
            post_id = c.buf.create_post(c.channel["id"], caption, url, c.mode, due, notify)
        except Ambiguous:  # maybe it did go through: look in the queue before anyone repeats it
            twin = next((p for p in c.buf.scheduled(c.channel["org"], c.channel["id"]) if p["text"] == caption), None) if c.mode == "queue" else None
            if not twin:
                raise
            post_id = twin["id"]
        c.state[sha].update(post_id=post_id, status={"draft": "draft", "now": "sending"}.get(c.mode, "scheduled"), notification=notify)
        if due:
            c.taken.append(due)
        res = {"state": "draft" if c.mode == "draft" else ("notify" if notify else "posting" if c.mode == "now" else "scheduled"), "post_id": post_id}
        if due:
            res["due"] = due.astimezone(c.tz).isoformat()
        return res
    except AudioMissing as e:  # the file has no proper sound: nothing is sent, the video waits for audio
        return {"state": "awaiting_audio", "detail": str(e)[:200]}
    except (BufferError, OSError, KeyError, ValueError) as e:
        return {"state": "error", "detail": f"{type(e).__name__}: {str(e)[:200]}"}


def publish_dir(out, cfg, state_path, env=os.environ, buf=None, storage=None, now=None):
    """Send every video of out/ready that report.json lists. Writes the result into report.json. -> list of results."""
    bcfg, out = cfg.get("buffer", {}), Path(out)
    rep_path = out / "report.json"
    report = json.loads(rep_path.read_text(encoding="utf-8"))
    mode, now = mode_of(cfg, env), now or datetime.now(timezone.utc)

    def finish(**b):
        report["buffer"] = b
        rep_path.write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")

    todo = [r for r in report["songs"] if r.get("ready") and r["stages"].get("render") == "ok"]
    if mode == "off":
        finish(state="off")
        return []
    need = ["BUFFER_API_KEY"] + (["CLOUDINARY_CLOUD_NAME", "CLOUDINARY_API_KEY", "CLOUDINARY_API_SECRET"] if mode in ("draft", "queue", "now") else [])
    missing = [k for k in need if not env.get(k)]
    if missing and not (buf and (storage or mode == "plan")):
        finish(state="skipped", detail="missing secrets: " + ", ".join(missing))
        return []
    buf = buf or Buffer(env["BUFFER_API_KEY"])
    if mode in ("draft", "queue", "now"):
        storage = storage or Cloudinary(env["CLOUDINARY_CLOUD_NAME"], env["CLOUDINARY_API_KEY"], env["CLOUDINARY_API_SECRET"])
    state, results = load_state(state_path), []
    try:
        ch = resolve_channel(buf, bcfg, mode)
        tz, hm = slot_config(bcfg, env)
        sched = buf.scheduled(ch["org"], ch["id"]) if mode in ("queue", "plan") else []
        taken = [parse_dt(p["dueAt"]) for p in sched if p.get("dueAt")]
        info = {"state": mode, "channel": ch["name"], "timezone": tz.key, "slots": [f"{h:02d}:{m:02d}" for h, m in hm], "scheduled_before": len(sched)}
        if mode != "plan":
            info["problems"] = refresh_statuses(state, buf, now) if mode in ("queue", "now") else []
            info["cleaned"] = cleanup(state, storage, bcfg.get("keep_days", 7), now)
        report["buffer"] = info
        c = SimpleNamespace(mode=mode, channel=ch, state=state, buf=buf, storage=storage, bcfg=bcfg, now=now, tz=tz, hm=hm, taken=taken,
                            taken_posts=sched, env=env, date=report.get("date") or out.name)
        for r in todo:
            mp4, cap = out / "ready" / f"{r['ready']}.mp4", out / "ready" / f"{r['ready']} caption.txt"
            r["buffer"] = publish_one(c, mp4, caption_for(cap.read_text(encoding="utf-8")), rec=r, silent=report.get("mode") == "tiktok")
            results.append(r["buffer"])
    except BufferError as e:  # no channel / API down: the videos stay in ready/ and Drive
        report["buffer"] = dict(report.get("buffer") or {"state": mode}, state="error", detail=str(e)[:200])
    finally:
        if mode != "plan":
            save_state(state_path, state)
        rep_path.write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    return results


def failed(out):
    """True when report.json says something went wrong that a human must see (the CI step must not end green)."""
    rep = json.loads((Path(out) / "report.json").read_text(encoding="utf-8"))
    b = rep.get("buffer") or {}
    return b.get("state") in ("error", "skipped") or bool(b.get("problems")) or any((s.get("buffer") or {}).get("state") == "error" for s in rep["songs"])


def summary(out):
    """Markdown lines for the GitHub Actions summary."""
    rep = json.loads((Path(out) / "report.json").read_text(encoding="utf-8"))
    b = rep.get("buffer") or {}
    lines = [f"- buffer: {b.get('state', 'n/a')} {b.get('detail', '')} slots={','.join(b.get('slots', []))} {b.get('timezone', '')}".rstrip()]
    lines += [f"  - PROBLEM: {p}" for p in b.get("problems", [])]
    lines += [f"  - {s['song']}: {s['buffer']['state']} {s['buffer'].get('due', '')} {s['buffer'].get('detail', '')}".rstrip() for s in rep["songs"] if s.get("buffer")]
    lines += [f"  - {s['song']}: ожидает аудио (fetch: {s.get('stages', {}).get('fetch', 'n/a')})" for s in rep["songs"]
              if not s.get("buffer") and (s.get("stages") or {}).get("fetch") not in (None, "ok")]
    return lines


def setup(env=os.environ, buf=None, config_path=None):
    """Find the TikTok channel and store its id in config.json (the id is not a secret)."""
    buf = buf or Buffer(env["BUFFER_API_KEY"])
    chs = buf.tiktok_channels()
    if not chs:
        raise BufferError("no TikTok channel connected to this Buffer account")
    ch = chs[0]
    p = Path(config_path or ROOT / "config.json")
    txt = p.read_text(encoding="utf-8")
    new = re.sub(r'("channel_id":\s*)"[^"]*"', lambda m: f'{m.group(1)}"{ch["id"]}"', txt, count=1)
    if new == txt and ch["id"] not in txt:
        raise BufferError('config.json has no "channel_id" under "buffer"')
    p.write_text(new, encoding="utf-8")
    return chs


def check(cfg, env=os.environ, buf=None, now=None):
    """Read-only look at the real account: channel state, how many posts are scheduled, where the next 3 would go."""
    buf, now, bcfg = buf or Buffer(env["BUFFER_API_KEY"]), now or datetime.now(timezone.utc), cfg.get("buffer", {})
    ch = resolve_channel(buf, bcfg, "plan")
    tz, hm = slot_config(bcfg, env)
    sched = buf.scheduled(ch["org"], ch["id"])
    nxt = free_slots(3, [parse_dt(p["dueAt"]) for p in sched if p.get("dueAt")], tz, hm, now)
    return {"channel": ch["name"], "queue_paused": ch["paused"], "channel_timezone": ch["timezone"], "slots_timezone": tz.key,
            "scheduled": len(sched), "next_free": [t.astimezone(tz).isoformat() for t in nxt]}


def main(argv):
    import argparse
    ap = argparse.ArgumentParser(prog="pipeline buffer")
    ap.add_argument("cmd", choices=["setup", "check", "publish", "summary", "drive-cleanup"])
    ap.add_argument("out", nargs="?")
    ap.add_argument("--state", default=str(ROOT / "out" / "buffer-state.json"))
    a = ap.parse_args(argv)
    cfg = load_config()
    try:
        if a.cmd in ("setup", "check"):
            if not os.environ.get("BUFFER_API_KEY"):
                print("set BUFFER_API_KEY in the environment first (never paste it in chat)")
                return 2
            if a.cmd == "check":
                print(json.dumps(check(cfg), ensure_ascii=False, indent=1))
                return 0
            for c in setup():
                print(f'TikTok channel: {c["name"]} id={c["id"]} (saved to config.json)' + (" QUEUE PAUSED" if c["paused"] else ""))
            return 0
        if a.cmd == "drive-cleanup":
            st = load_state(a.state)
            n, problems = drive_cleanup(st, cfg.get("buffer", {}), datetime.now(timezone.utc))
            save_state(a.state, st)
            print(json.dumps({"deleted_from_drive": n, "problems": problems}, ensure_ascii=False))
            return 1 if problems else 0  # a file that could not be deleted is not hidden: red step, retried next run
        if not a.out:
            ap.error("publish/summary need out/<date>")
        if a.cmd == "summary":
            print(*summary(a.out), sep="\n")
            return 0
        res = publish_dir(a.out, cfg, a.state)
        print(json.dumps(res, ensure_ascii=False))
        return 1 if failed(a.out) else 0  # an error is never swallowed: the workflow step goes red, the mp4 stays in ready/
    except BufferError as e:
        print(f"buffer: {e}")
        return 1
