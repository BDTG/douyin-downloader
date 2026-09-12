"""API server noi bo (BDTG) — FastAPI, viet moi 100%.

Chay:  python server.py -c config.native.yml --host 127.0.0.1 --port 8000
Contract giu nguyen de app Qt khong phai sua:
  GET  /api/v1/health
  POST /api/v1/resolve {url}
  POST /api/v1/download {url}
  GET  /api/v1/jobs , GET /api/v1/jobs/{id}
  POST /api/v1/download_images {aweme_id, indices[]}
  POST /api/v1/localinfo {path}
  POST /api/v1/user_posts {sec_uid, cursor, count}
  GET  /api/v1/videsc?text= , GET /api/v1/viname?name=
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import sys
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import httpx
import yaml
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from core.douyin import (
    UA,
    base_headers,
    classify_link,
    date_from_ts,
    extract_first_url,
    extract_mix_id,
    fetch_aweme_json,
    fetch_aweme_ssr,
    fetch_mix_page,
    normalize_detail,
    random_mstoken,
    resolve_short,
)
from core.hanviet import hanviet_name
from core.storage import append_manifest, item_dir, manifest_lookup, safe_name

HERE = Path(__file__).parent
STACK = HERE.parent
DOWNLOADS = STACK / "downloads"
DATA_HANVIET = STACK / "data" / "hanviet.json"
VAR_DIR = STACK / "var"
VI_CACHE = VAR_DIR / "vi_desc.json"

app = FastAPI(title="douyin-api-bdtg")

CFG: Dict[str, Any] = {"path": str(DOWNLOADS), "thread": 5, "cookies": {}}
ALIASES: Dict[str, str] = {}


# ---------- config ----------

def load_config(path: str) -> Dict[str, Any]:
    global CFG
    try:
        d = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
        if isinstance(d, dict):
            CFG = {**CFG, **d}
    except Exception:
        pass
    cookies = CFG.get("cookies") or {}
    CFG["cookies"] = {k: str(v or "") for k, v in cookies.items() if str(v or "")}
    if not CFG["cookies"].get("msToken"):
        CFG["cookies"]["msToken"] = random_mstoken()
    dl = Path(str(CFG.get("path") or DOWNLOADS))
    try:
        dl.mkdir(parents=True, exist_ok=True)
    except Exception:
        # may test khong co o D:/ -> dung thu muc mac dinh trong repo
        dl = DOWNLOADS
        dl.mkdir(parents=True, exist_ok=True)
    CFG["path"] = str(dl)
    return CFG


def load_aliases() -> Dict[str, str]:
    global ALIASES
    for p in (STACK / "aliases.json",):
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
            ALIASES = {k: v for k, v in d.items()
                       if isinstance(v, str) and not k.startswith("_")}
            break
        except Exception:
            continue
    return ALIASES


def cookies() -> Dict[str, str]:
    return dict(CFG.get("cookies") or {})


def dl_dir() -> Path:
    return Path(str(CFG.get("path") or DOWNLOADS))


# ---------- jobs (RAM, don gian) ----------

JOBS: Dict[str, Dict[str, Any]] = {}
MAX_JOBS = 500
JOB_TTL = 24 * 3600


def _prune_jobs() -> None:
    now = time.time()
    dead = [jid for jid, j in JOBS.items()
            if j.get("status") in ("SUCCESS", "FAILED")
            and now - float(j.get("finished_at") or j.get("created_at") or now) > JOB_TTL]
    for jid in dead:
        JOBS.pop(jid, None)
    if len(JOBS) > MAX_JOBS:
        olds = sorted(
            (jid for jid, j in JOBS.items() if j.get("status") in ("SUCCESS", "FAILED")),
            key=lambda jid: float(JOBS[jid].get("finished_at") or 0))
        for jid in olds[:len(JOBS) - MAX_JOBS]:
            JOBS.pop(jid, None)


def new_job(url: str) -> Dict[str, Any]:
    _prune_jobs()
    jid = uuid.uuid4().hex[:12]
    JOBS[jid] = {"job_id": jid, "url": url, "status": "PENDING",
                 "created_at": time.time(), "total": 0, "success": 0,
                 "failed": 0, "error": "", "downloaded_bytes": 0,
                 "total_bytes": 0, "current_aweme": ""}
    return JOBS[jid]


# ---------- models ----------

class UrlBody(BaseModel):
    url: str = ""


class ImagesBody(BaseModel):
    url: str = ""
    aweme_id: str = ""
    indices: List[int] = []


class LocalInfoBody(BaseModel):
    path: str = ""


class UserPostsBody(BaseModel):
    url: str = ""
    sec_uid: str = ""
    cursor: int = 0
    count: int = 20


class MixPostsBody(BaseModel):
    url: str = ""
    mix_id: str = ""
    cursor: int = 0
    count: int = 20


# ---------- helpers ----------

async def resolve_detail_from_text(text: str) -> Dict[str, Any]:
    """Nhan ca doan share-text -> normalize detail (nem loi neu khong duoc)."""
    raw_url = extract_first_url(text or "")
    if not raw_url:
        raise HTTPException(400, "khong thay link http trong text")
    url = raw_url
    cls = classify_link(url)
    if cls["type"] == "short":
        try:
            url = await resolve_short(url)
        except Exception as e:
            raise HTTPException(502, f"khong mo duoc short-link: {e}")
        cls = classify_link(url)
    if cls["type"] == "user":
        sec = cls["id"]
        info = await fetch_user_info(sec)
        nick = str(info.get("nickname") or "")
        hv, _ = hanviet_name(nick, str(DATA_HANVIET))
        return {"type": "user", "author_nickname": nick,
                "author_sec_uid": sec, "name_vi": hv,
                "code": ALIASES.get(sec, ""),
                "resolved": url, "original": text}
    if cls["type"] == "mix":
        mid = cls["id"]
        page = await fetch_mix_page(mid, 0, 1, cookies())
        return {"type": "mix", "mix_id": mid,
                "mix_name": page.get("mix_name", ""),
                "resolved": url, "original": text}
    aid = cls["id"]
    if not aid:
        # co the la link user dang token sec_uid
        m = re.search(r"/user/([A-Za-z0-9_\-]+)", url)
        if m:
            sec = m.group(1)
            info = await fetch_user_info(sec)
            nick = str(info.get("nickname") or "")
            hv, _ = hanviet_name(nick, str(DATA_HANVIET))
            return {"type": "user", "author_nickname": nick,
                    "author_sec_uid": sec, "name_vi": hv,
                    "code": ALIASES.get(sec, ""),
                    "resolved": url, "original": text}
        raise HTTPException(422, "link khong phai video/note/user Douyin")
    ck = cookies()
    detail = await fetch_aweme_json(aid, ck) or await fetch_aweme_ssr(aid, ck)
    if not detail:
        raise HTTPException(502, "Douyin khong tra du lieu (het cookie/bi chan?)")
    norm = normalize_detail(detail, resolved_url=url, original_text=text)
    sec = str(norm.get("author_sec_uid") or "")
    nick = str(norm.get("author_nickname") or "")
    hv, _ = hanviet_name(nick, str(DATA_HANVIET))
    norm["name_vi"] = hv
    norm["code"] = ALIASES.get(sec, "")
    norm["resolved"] = url
    norm["original"] = text
    return norm


async def fetch_user_info(sec_uid: str) -> Dict[str, Any]:
    ck = cookies()
    headers = base_headers()
    if ck:
        headers["Cookie"] = "; ".join(f"{k}={v}" for k, v in ck.items() if v)
        if "msToken" not in ck:
            headers["Cookie"] += f"; msToken={random_mstoken()}"
    params = {"device_platform": "webapp", "aid": "6383",
              "sec_user_id": sec_uid, "version_code": "170400",
              "msToken": ck.get("msToken") or random_mstoken()}
    try:
        async with httpx.AsyncClient(timeout=20, headers=headers) as c:
            r = await c.get("https://www.douyin.com/aweme/v1/web/user/profile/other/",
                            params=params)
            if r.status_code != 200:
                return {}
            user = (r.json().get("user") or {})
            return {"nickname": user.get("nickname") or "",
                    "sec_uid": user.get("sec_uid") or sec_uid}
    except Exception:
        return {}


async def download_binary(url: str, dest: Path, job: Optional[Dict] = None,
                          referer: str = "https://www.douyin.com/") -> int:
    headers = {"User-Agent": UA, "Referer": referer}
    ck = cookies()
    if ck:
        headers["Cookie"] = "; ".join(f"{k}={v}" for k, v in ck.items() if v)
    total = 0
    async with httpx.AsyncClient(timeout=300, headers=headers,
                                 follow_redirects=True) as c:
        async with c.stream("GET", url) as r:
            if r.status_code != 200:
                raise RuntimeError(f"CDN {r.status_code}")
            size = int(r.headers.get("Content-Length") or 0)
            if job is not None:
                job["total_bytes"] = size
            tmp = dest.with_suffix(dest.suffix + ".tmp")
            with open(tmp, "wb") as f:
                async for chunk in r.aiter_bytes(1 << 16):
                    if not chunk:
                        continue
                    f.write(chunk)
                    total += len(chunk)
                    if job is not None:
                        job["downloaded_bytes"] = total
            if total == 0:
                raise RuntimeError("file rong (CDN chan?)")
            tmp.replace(dest)
    return total


# ---------- routes ----------

@app.get("/api/v1/health")
def health():
    return {"status": "ok"}


@app.post("/api/v1/resolve")
async def resolve(body: UrlBody):
    if not (body.url or "").strip():
        raise HTTPException(400, "thieu url")
    return await resolve_detail_from_text(body.url)


async def _run_download(job_id: str, url_text: str) -> None:
    job = JOBS.get(job_id)
    if not job:
        return
    job["status"] = "RUNNING"
    job["started_at"] = time.time()
    try:
        info = await resolve_detail_from_text(url_text)
        if info.get("type") == "user":
            raise RuntimeError("day la link trang ca nhan — dung chuc nang quet user")
        aid = str(info.get("aweme_id") or "")
        job["current_aweme"] = aid
        sec = str(info.get("author_sec_uid") or "unknown")
        folder = item_dir(dl_dir(), sec, str(info.get("date") or ""),
                          str(info.get("desc") or ""), aid)
        if info.get("media_type") == "gallery":
            imgs = list(info.get("images") or [])
            if not imgs:
                raise RuntimeError("gallery khong co anh goc")
            saved = await _save_images(aid, folder, imgs, list(range(len(imgs))), job)
            info["saved_images"] = saved
        else:
            play = str(info.get("play_url") or "")
            if not play:
                raise RuntimeError("khong lay duoc link video goc")
            dest = folder / f"{info.get('date') or 'video'}_{safe_name(info.get('desc') or '', 30)}_{aid}.mp4"
            if not (dest.exists() and dest.stat().st_size > 0):
                await download_binary(play, dest, job)
            info["saved_video"] = dest.name
        append_manifest(dl_dir(), {
            "aweme_id": aid, "author_name": info.get("author_nickname"),
            "author_sec_uid": sec, "desc": info.get("desc"),
            "date": info.get("date"), "media_type": info.get("media_type"),
            "file_paths": [str((folder / f).relative_to(dl_dir()))
                           for f in sorted(p.name for p in folder.iterdir() if p.is_file())],
        })
        job["status"] = "SUCCESS"
        job["success"] = 1
        job["total"] = 1
    except Exception as e:
        job["status"] = "FAILED"
        job["failed"] = 1
        job["error"] = str(e)[:500]
    finally:
        job["finished_at"] = time.time()


async def _save_images(aid: str, folder: Path, urls: List[str],
                       indices: List[int], job: Optional[Dict] = None) -> List[str]:
    picks = list(range(len(urls))) if not indices else [i for i in indices if 0 <= i < len(urls)]
    saved: List[str] = []
    headers = {"User-Agent": UA, "Referer": "https://www.douyin.com/"}
    ck = cookies()
    if ck:
        headers["Cookie"] = "; ".join(f"{k}={v}" for k, v in ck.items() if v)
    async with httpx.AsyncClient(timeout=120, headers=headers,
                                 follow_redirects=True) as c:
        for n, i in enumerate(picks):
            try:
                r = await c.get(urls[i])
                if r.status_code != 200 or not r.content:
                    continue
                ct = (r.headers.get("Content-Type") or "").split(";")[0]
                ext = { "image/jpeg": ".jpg", "image/png": ".png",
                        "image/webp": ".webp", "image/gif": ".gif"}.get(ct, ".jpg")
                dest = folder / f"{aid}_img{n + 1:02d}{ext}"
                if not (dest.exists() and dest.stat().st_size > 0):
                    dest.write_bytes(r.content)
                saved.append(dest.name)
                if job is not None:
                    job["downloaded_bytes"] = len(saved)
                    job["total_bytes"] = len(picks)
            except Exception:
                continue
    return saved


@app.post("/api/v1/download")
async def download(body: UrlBody):
    if not (body.url or "").strip():
        raise HTTPException(400, "thieu url")
    if not extract_first_url(body.url):
        raise HTTPException(422, "khong thay link http")
    job = new_job(body.url)
    asyncio.create_task(_run_download(job["job_id"], body.url))
    return {"job_id": job["job_id"], "status": job["status"], "url": body.url}


@app.get("/api/v1/jobs")
def list_jobs():
    return {"jobs": list(JOBS.values())}


@app.get("/api/v1/jobs/{job_id}")
def one_job(job_id: str):
    j = JOBS.get(job_id)
    if not j:
        raise HTTPException(404, "job not found (api da restart?)")
    return j


@app.post("/api/v1/download_images")
async def download_images(body: ImagesBody):
    aid = (body.aweme_id or "").strip()
    info: Optional[Dict[str, Any]] = None
    if not aid and body.url:
        info = await resolve_detail_from_text(body.url)
        aid = str(info.get("aweme_id") or "")
    if not aid and not info:
        # thu tim trong manifest (da tai truoc do)
        raise HTTPException(422, "thieu aweme_id")
    if info is None:
        ck = cookies()
        detail = await fetch_aweme_json(aid, ck) or await fetch_aweme_ssr(aid, ck)
        if not detail:
            # fallback: tim file cu trong manifest
            idx = manifest_lookup(dl_dir())
            if aid not in idx:
                raise HTTPException(502, "khong phai gallery / khong lay duoc anh")
            return {"aweme_id": aid, "saved": [], "failed": [],
                    "total_images": 0, "note": "da co trong manifest"}
        info = normalize_detail(detail)
    images = list(info.get("images") or [])
    if not images:
        raise HTTPException(422, "video nay khong phai gallery")
    images = images[:35]
    sec = str(info.get("author_sec_uid") or "unknown")
    folder = item_dir(dl_dir(), sec, str(info.get("date") or ""),
                      str(info.get("desc") or ""), aid)
    saved = await _save_images(aid, folder, images, list(body.indices or []))
    failed = [{"index": i, "error": "tai loi"} for i in (body.indices or [])
              if 0 <= i < len(images) and f"{aid}_img" not in "".join(saved)]
    append_manifest(dl_dir(), {"aweme_id": aid,
                               "author_name": info.get("author_nickname"),
                               "author_sec_uid": sec, "desc": info.get("desc"),
                               "date": info.get("date"), "media_type": "gallery"})
    rel = folder.relative_to(dl_dir()).as_posix()
    return {"aweme_id": aid, "saved": saved, "failed": failed,
            "dir": rel, "total_images": len(images)}


@app.post("/api/v1/localinfo")
def localinfo(body: LocalInfoBody):
    base = dl_dir().resolve()
    try:
        rp = (base / (body.path or "")).resolve()
        rp.relative_to(base)
    except Exception:
        raise HTTPException(400, "bad path")
    if not rp.is_file():
        raise HTTPException(404, "not found")
    out: Dict[str, Any] = {"name": rp.name, "size": rp.stat().st_size,
                           "duration_s": 0, "width": 0, "height": 0}
    # ffprobe neu co (optional), khong bat buoc
    try:
        import subprocess as _sp, json as _js
        r = _sp.run(["ffprobe", "-v", "quiet", "-print_format", "json",
                     "-show_format", "-show_streams", str(rp)],
                    capture_output=True, timeout=10)
        if r.returncode == 0:
            meta = _js.loads(r.stdout.decode("utf-8", "replace"))
            for s in (meta.get("streams") or []):
                if s.get("codec_type") == "video":
                    out["width"] = int(s.get("width") or 0)
                    out["height"] = int(s.get("height") or 0)
                    out["vcodec"] = str(s.get("codec_name") or "")
                    break
            fmt = meta.get("format") or {}
            out["duration_s"] = float(fmt.get("duration") or 0)
            out["bitrate_kbps"] = int(float(fmt.get("bit_rate") or 0) // 1000)
    except Exception:
        pass
    return out


@app.post("/api/v1/user_posts")
async def user_posts(body: UserPostsBody):
    sec = (body.sec_uid or "").strip()
    if not sec and body.url:
        m = re.search(r"/user/([A-Za-z0-9_\-]+)", body.url)
        sec = m.group(1) if m else ""
    if not sec:
        raise HTTPException(422, "thieu sec_uid")
    count = max(1, min(int(body.count or 20), 50))
    cursor = int(body.cursor or 0)
    ck = cookies()
    headers = base_headers()
    if ck:
        headers["Cookie"] = "; ".join(f"{k}={v}" for k, v in ck.items() if v)
    params = {"device_platform": "webapp", "aid": "6383",
              "sec_user_id": sec, "max_cursor": cursor, "count": count,
              "version_code": "170400",
              "msToken": ck.get("msToken") or random_mstoken()}
    try:
        async with httpx.AsyncClient(timeout=25, headers=headers) as c:
            r = await c.get("https://www.douyin.com/aweme/v1/web/aweme/post/",
                            params=params)
            if r.status_code != 200:
                raise HTTPException(502, f"douyin {r.status_code}")
            data = r.json()
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(502, f"loi mang douyin: {e}")
    items: List[Dict[str, Any]] = []
    for raw in (data.get("aweme_list") or [])[:count]:
        try:
            n = normalize_detail(raw)
            items.append({
                "aweme_id": n["aweme_id"], "desc": (n["desc"] or "")[:120],
                "date": n["date"], "digg_count": n["digg_count"],
                "comment_count": n["comment_count"], "share_count": n["share_count"],
                "play_count": n.get("play_count", 0),
                "media_type": n["media_type"], "image_count": n["image_count"],
                "cover_url": n["cover_url"], "duration_s": n["duration_s"],
                "width": n["width"], "height": n["height"],
                "music_title": n["music_title"]})
        except Exception:
            continue
    return {"sec_uid": sec, "cursor": cursor,
            "next_cursor": data.get("max_cursor") or 0,
            "has_more": bool(data.get("has_more")),
            "items": items}


def _slim_item(n: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "aweme_id": n["aweme_id"], "desc": (n["desc"] or "")[:120],
        "date": n["date"], "digg_count": n["digg_count"],
        "comment_count": n["comment_count"], "share_count": n["share_count"],
        "play_count": n.get("play_count", 0),
        "media_type": n["media_type"], "image_count": n["image_count"],
        "cover_url": n["cover_url"], "duration_s": n["duration_s"],
        "width": n["width"], "height": n["height"],
        "music_title": n["music_title"]}


@app.post("/api/v1/mix_posts")
async def mix_posts(body: MixPostsBody):
    """Danh sach video trong 1 collection/mix (viet moi, phan trang cursor)."""
    mid = (body.mix_id or "").strip() or extract_mix_id(body.url or "")
    if not mid:
        raise HTTPException(422, "thieu mix_id (link /collection/ hoac /mix/)")
    count = max(1, min(int(body.count or 20), 50))
    page = await fetch_mix_page(mid, int(body.cursor or 0), count, cookies())
    items: List[Dict[str, Any]] = []
    for raw in page["items"][:count]:
        try:
            items.append(_slim_item(normalize_detail(raw)))
        except Exception:
            continue
    return {"mix_id": mid, "mix_name": page.get("mix_name", ""),
            "cursor": int(body.cursor or 0),
            "next_cursor": page.get("next_cursor") or 0,
            "has_more": bool(page.get("has_more")),
            "items": items}


@app.get("/api/v1/viname")
def viname(name: str = ""):
    hv, unknown = hanviet_name(name or "", str(DATA_HANVIET))
    return {"original": name, "hanviet": hv, "unknown": unknown}


@app.get("/api/v1/videsc")
async def videsc(text: str = ""):
    import os
    if not text or not re.search(r"[一-鿿]", text):
        return {"original": text, "desc_vi": ""}
    key = os.environ.get("GEMINI_API_KEY", "")
    try:
        cfg_key = str((CFG.get("gemini_api_key") or ""))
    except Exception:
        cfg_key = ""
    key = key or cfg_key
    if not key:
        return {"original": text, "desc_vi": ""}
    try:
        cache: Dict[str, str] = {}
        if VI_CACHE.is_file():
            cache = json.loads(VI_CACHE.read_text(encoding="utf-8"))
    except Exception:
        cache = {}
    if text in cache:
        return {"original": text, "desc_vi": cache[text]}
    try:
        async with httpx.AsyncClient(timeout=30) as c:
            r = await c.post(
                "https://generativelanguage.googleapis.com/v1beta/models/"
                "gemini-2.0-flash:generateContent?key=" + key,
                json={"contents": [{"parts": [
                    {"text": "Dich tu nhien sang tieng Viet, giu hashtag/ten rieng:\n" + text}]}]})
            out = ""
            if r.status_code == 200:
                cands = r.json().get("candidates") or []
                if cands:
                    parts = ((cands[0].get("content") or {}).get("parts") or [])
                    out = "".join(p.get("text", "") for p in parts).strip()
        if out:
            cache[text] = out
            try:
                VAR_DIR.mkdir(parents=True, exist_ok=True)
                VI_CACHE.write_text(json.dumps(cache, ensure_ascii=False),
                                    encoding="utf-8")
            except Exception:
                pass
        return {"original": text, "desc_vi": out}
    except Exception:
        return {"original": text, "desc_vi": ""}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("-c", "--config", default=str(HERE / "config.native.yml"))
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8000)
    args = ap.parse_args()
    load_config(args.config)
    load_aliases()
    import uvicorn
    uvicorn.run(app, host=args.host, port=args.port, log_level="info")


if __name__ == "__main__":
    main()
