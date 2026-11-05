"""Hands finished videos to Buffer (official GraphQL API, https://developers.buffer.com) so the TikTok queue publishes them during the day.

Flow per video: sha256 -> already sent? -> upload to a temporary Cloudinary folder (Buffer needs a public HTTPS URL, Drive links do not work)
-> check the URL like Buffer will -> createPost (draft | queue) -> record in a state file -> report.json.
Hosted files must live until Buffer posts them (it fetches at publish time), so they are deleted by age (`keep_days`) at the next run.
The MP4 in out/<date>/ready is never touched. Secrets only from env: BUFFER_API_KEY, CLOUDINARY_CLOUD_NAME/API_KEY/API_SECRET.

python -m pipeline buffer setup                 # finds the TikTok channel, writes its id into config.json
python -m pipeline buffer publish out/<date> [--state out/buffer-state.json]"""
import hashlib
import json
import os
import re
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

from .common import ROOT, load_config, safe_err

API = "https://api.buffer.com"
MODES = ("off", "draft", "queue")
MAX_TEXT = 2200  # TikTok caption limit

Q_ORGS = "query { account { organizations { id name } } }"
Q_CHANNELS = "query($o: OrganizationId!) { channels(input: {organizationId: $o}) { id name displayName service isQueuePaused } }"
M_POST = """mutation($input: CreatePostInput!) { createPost(input: $input) {
  ... on PostActionSuccess { post { id } }
  ... on MutationError { message } } }"""


class BufferError(Exception):
    pass


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


class Buffer:
    def __init__(self, key, post=requests.post):
        self.key, self._post = key, post

    def gql(self, query, variables=None):
        for attempt in range(3):
            try:
                r = self._post(API, json={"query": query, "variables": variables or {}}, timeout=60,
                               headers={"Authorization": f"Bearer {self.key}", "Content-Type": "application/json"})
            except requests.RequestException as e:
                raise BufferError(f"network: {safe_err(e)}")
            if r.status_code == 429 and attempt < 2:  # only 429 is retried: the request was not processed, a timeout might have been
                time.sleep(5 * (attempt + 1))
                continue
            if r.status_code != 200:
                raise BufferError(f"HTTP {r.status_code}")
            body = r.json()
            if body.get("errors"):
                raise BufferError("; ".join(str(e.get("message", e))[:150] for e in body["errors"][:2]))
            return body["data"]
        raise BufferError("rate limited")

    def tiktok_channels(self):
        out = []
        for org in self.gql(Q_ORGS)["account"]["organizations"]:
            for ch in self.gql(Q_CHANNELS, {"o": org["id"]})["channels"]:
                if str(ch.get("service", "")).lower() == "tiktok":
                    out.append({"id": ch["id"], "name": ch.get("displayName") or ch.get("name"), "org": org["id"],
                                "paused": ch.get("isQueuePaused")})
        return out

    def create_post(self, channel_id, text, url, mode):
        inp = {"text": text, "channelId": channel_id, "schedulingType": "automatic", "mode": "addToQueue", "aiAssisted": True,
               "assets": [{"video": {"url": url, "metadata": {"thumbnailOffset": 2000}}}],
               "metadata": {"tiktok": {"isAiGenerated": True}}}
        if mode == "draft":
            inp["saveToDraft"] = True
        res = self.gql(M_POST, {"input": inp})["createPost"]
        if "post" not in res:
            raise BufferError(res.get("message", "createPost failed")[:200])
        return res["post"]["id"]


class Cloudinary:
    """Temporary public host. Public id = sha256 of the file: unguessable, and the same file always gets the same URL."""

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


def check_file(path, bcfg):
    p = Path(path)
    if p.suffix.lower() != ".mp4":
        raise BufferError("only .mp4 is sent")
    mb = p.stat().st_size / 1e6
    lim = bcfg.get("max_mb", 100)  # free Cloudinary accepts up to 100 MB per video; TikTok itself allows far more
    if mb > lim:
        raise BufferError(f"file is {mb:.0f} MB, limit {lim} MB")


def load_state(path):
    p = Path(path)
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


def save_state(path, st):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(st, ensure_ascii=False, indent=1), encoding="utf-8")


def cleanup(state, storage, keep_days, now=None):
    """Delete hosted files older than keep_days (Buffer has fetched them long before). Returns how many were removed."""
    now, n = now or datetime.now(timezone.utc), 0
    for sha, e in state.items():
        if e.get("hosted") and datetime.fromisoformat(e["uploaded_at"]) < now - timedelta(days=keep_days):
            try:
                if storage.delete(e["public_id"]):
                    e["hosted"], n = False, n + 1
            except BufferError:
                pass  # tried again at the next run
    return n


def publish_one(mp4, caption, channel_id, mode, state, buf, storage, bcfg, now=None):
    """-> result dict for report.json. Never raises."""
    now = now or datetime.now(timezone.utc)
    try:
        check_file(mp4, bcfg)
        sha = sha256(mp4)
        old = state.get(sha)
        if old and old.get("post_id") and not (old["mode"] == "draft" and mode == "queue"):  # a draft may later be sent for real
            return {"state": "duplicate", "detail": f"already sent as {old['mode']} {old['post_id']}"}
        size, pid = Path(mp4).stat().st_size, f"vybex/{sha[:40]}"
        url = storage.upload(mp4, pid)
        state[sha] = {"public_id": pid, "uploaded_at": now.isoformat(), "hosted": True, "mode": mode, "file": Path(mp4).name}
        check_url(url, size)
        post_id = buf.create_post(channel_id, caption, url, mode)
        state[sha]["post_id"] = post_id
        until = now + timedelta(days=bcfg.get("keep_days", 7))
        return {"state": "draft" if mode == "draft" else "queued", "post_id": post_id, "hosted_until": until.date().isoformat()}
    except (BufferError, OSError, KeyError, ValueError) as e:
        return {"state": "error", "detail": f"{type(e).__name__}: {str(e)[:200]}"}



def publish_dir(out, cfg, state_path, env=os.environ, buf=None, storage=None, now=None):
    """Send every video of out/ready that report.json lists. Writes the result into report.json. -> list of results."""
    bcfg = cfg.get("buffer", {})
    out = Path(out)
    rep_path = out / "report.json"
    report = json.loads(rep_path.read_text(encoding="utf-8"))
    mode = mode_of(cfg, env)
    todo = [r for r in report["songs"] if r.get("ready") and r["stages"].get("render") == "ok"]
    if mode == "off" or not todo:
        report["buffer"] = {"state": "off" if mode == "off" else "nothing to send"}
        rep_path.write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
        return []
    missing = [k for k in ("BUFFER_API_KEY", "CLOUDINARY_CLOUD_NAME", "CLOUDINARY_API_KEY", "CLOUDINARY_API_SECRET") if not env.get(k)]
    if missing and not (buf and storage):
        report["buffer"] = {"state": "skipped", "detail": "missing secrets: " + ", ".join(missing)}
        rep_path.write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
        return []
    buf = buf or Buffer(env["BUFFER_API_KEY"])
    storage = storage or Cloudinary(env["CLOUDINARY_CLOUD_NAME"], env["CLOUDINARY_API_KEY"], env["CLOUDINARY_API_SECRET"])
    state = load_state(state_path)
    results = []
    try:
        channel = bcfg.get("channel_id") or _only_channel(buf)
        cleaned = cleanup(state, storage, bcfg.get("keep_days", 7), now)
        report["buffer"] = {"state": mode, "channel": channel, "cleaned": cleaned}
        for r in todo:
            mp4 = out / "ready" / f"{r['ready']}.mp4"
            cap = out / "ready" / f"{r['ready']} caption.txt"
            r["buffer"] = publish_one(mp4, caption_for(cap.read_text(encoding="utf-8")), channel, mode, state, buf, storage, bcfg, now)
            results.append(r["buffer"])
    except BufferError as e:  # no channel / API down: the videos stay in ready/ and Drive
        report["buffer"] = {"state": "error", "detail": str(e)[:200]}
    finally:
        save_state(state_path, state)
        rep_path.write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    return results


def _only_channel(buf):
    chs = buf.tiktok_channels()
    if len(chs) != 1:
        raise BufferError(f"expected exactly 1 TikTok channel in Buffer, found {len(chs)}; run `python -m pipeline buffer setup`")
    return chs[0]["id"]


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


def main(argv):
    import argparse
    ap = argparse.ArgumentParser(prog="pipeline buffer")
    ap.add_argument("cmd", choices=["setup", "publish"])
    ap.add_argument("out", nargs="?")
    ap.add_argument("--state", default=str(ROOT / "out" / "buffer-state.json"))
    a = ap.parse_args(argv)
    cfg = load_config()
    try:
        if a.cmd == "setup":
            if not os.environ.get("BUFFER_API_KEY"):
                print("set BUFFER_API_KEY in the environment first (never paste it in chat)")
                return 2
            for c in setup():
                print(f'TikTok channel: {c["name"]} id={c["id"]} (saved to config.json)' + (" QUEUE PAUSED" if c["paused"] else ""))
            return 0
        if not a.out:
            ap.error("publish needs out/<date>")
        res = publish_dir(a.out, cfg, a.state)
        print(json.dumps(res, ensure_ascii=False))
        return 1 if any(r["state"] == "error" for r in res) else 0  # state "error" never deletes anything
    except BufferError as e:
        print(f"buffer: {e}")
        return 1
