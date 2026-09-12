"""Client Douyin noi bo — chi dung HTTP cong khai + cookie nguoi dung.

Nguyen tac:
- Khong sinh chu ky phuc tap (a_bogus/X-Bogus). Chi gui cookie + UA trinh duyet.
- resolve short-link bang redirect 302 thuan.
- doc chi tiet video bang 2 cach (thu tu):
  1) JSON API cong khai cua Douyin web (neu cookie con han)
  2) fallback boc JSON nhung trong HTML SSR cua trang video (khong can ky)
- chon ban video goc (bitrate cao nhat), anh goc khong watermark.
"""
from __future__ import annotations

import json
import random
import re
import string
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

import httpx

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")

URL_RE = re.compile(r"https?://[^\s\"'<>`]+", re.I)
AWEME_RE = re.compile(r"/(?:video|note|slides|gallery)/(\d{6,})")
MODAL_RE = re.compile(r"modal_id=(\d{6,})")
USER_RE = re.compile(r"/user/([A-Za-z0-9_\-]+)")
MIX_RE = re.compile(r"/(?:collection|mix)/(\d{6,})")
SHORT_HOSTS = ("v.douyin.com", "v.iesdouyin.com", "iesdouyin.com")

VN_TZ = timezone(timedelta(hours=7))


def extract_first_url(text: str) -> str:
    """Lay link http dau tien trong doan share-text (nguoi dung paste ca doan)."""
    m = URL_RE.search(text or "")
    if not m:
        return ""
    return m.group(0).rstrip(".,);]}")


def random_mstoken(length: int = 107) -> str:
    alphabet = string.ascii_letters + string.digits + "=_-"
    return "".join(random.choice(alphabet) for _ in range(length))


def quality_from_size(w: int, h: int) -> str:
    # Dung canh NGAN (vi du 1080x1920 doc = 1080p = FHD)
    short_edge = min(int(w or 0), int(h or 0))
    if short_edge >= 2160:
        return "4K"
    if short_edge >= 1440:
        return "QHD"
    if short_edge >= 1080:
        return "FHD"
    if short_edge >= 720:
        return "HD"
    return "SD" if short_edge > 0 else ""


def date_from_ts(ts: Any) -> str:
    try:
        ts = int(ts)
        if ts > 10_000_000_000:  # ms -> s
            ts //= 1000
        return datetime.fromtimestamp(ts, tz=VN_TZ).strftime("%Y-%m-%d")
    except Exception:
        return ""


def base_headers(referer: str = "https://www.douyin.com/") -> Dict[str, str]:
    return {
        "User-Agent": UA,
        "Referer": referer,
        "Origin": "https://www.douyin.com",
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "zh-CN,zh;q=0.9,vi;q=0.8,en;q=0.7",
    }


def classify_link(url: str) -> Dict[str, str]:
    """Phan loai link: video / gallery / user / mix / short / unknown (thuan regex)."""
    u = (url or "").strip()
    host = urlparse(u).netloc.lower() if "://" in u else ""
    if any(h in host for h in SHORT_HOSTS):
        return {"type": "short", "id": ""}
    m = AWEME_RE.search(u) or MODAL_RE.search(u)
    if m:
        kind = "gallery" if ("/note/" in u or "/slides/" in u or "/gallery/" in u) else "video"
        return {"type": kind, "id": m.group(1)}
    m = MIX_RE.search(u)
    if m:
        return {"type": "mix", "id": m.group(1)}
    m = USER_RE.search(u)
    if m:
        return {"type": "user", "id": m.group(1)}
    return {"type": "unknown", "id": ""}


async def resolve_short(url: str, timeout: float = 15.0) -> str:
    """Follow redirect short-link -> URL that (khong can cookie)."""
    async with httpx.AsyncClient(follow_redirects=True, timeout=timeout,
                                 headers={"User-Agent": UA}) as c:
        r = await c.head(url)
        final = str(r.url)
        if final and final != url:
            return final
        r = await c.get(url)
        return str(r.url)


def _cookie_header(cookies: Dict[str, str]) -> str:
    return "; ".join(f"{k}={v}" for k, v in cookies.items() if v)


async def fetch_aweme_json(aweme_id: str, cookies: Dict[str, str],
                           timeout: float = 20.0) -> Optional[Dict[str, Any]]:
    """Goi JSON API cong khai. Tra ve dict aweme_detail hoac None neu bi chan."""
    params = {
        "device_platform": "webapp",
        "aid": "6383",
        "channel": "channel_pc_web",
        "aweme_id": aweme_id,
        "version_code": "170400",
        "version_name": "17.4.0",
        "cookie_enabled": "true",
        "platform": "PC",
        "downlink": "10",
        "msToken": cookies.get("msToken") or random_mstoken(),
    }
    headers = base_headers()
    if cookies:
        headers["Cookie"] = _cookie_header(cookies)
    try:
        async with httpx.AsyncClient(timeout=timeout, headers=headers,
                                     follow_redirects=True) as c:
            r = await c.get("https://www.douyin.com/aweme/v1/web/aweme/detail/",
                            params=params)
            if r.status_code != 200:
                return None
            data = r.json()
            detail = (data.get("aweme_detail")
                      or (data.get("aweme_details") or [None])[0])
            return detail if isinstance(detail, dict) else None
    except Exception:
        return None


async def fetch_aweme_ssr(aweme_id: str, cookies: Dict[str, str],
                          timeout: float = 20.0) -> Optional[Dict[str, Any]]:
    """Fallback: tai HTML trang video roi boc JSON nhung san (SSR)."""
    headers = {"User-Agent": UA, "Referer": "https://www.douyin.com/",
               "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8"}
    if cookies:
        headers["Cookie"] = _cookie_header(cookies)
    try:
        async with httpx.AsyncClient(timeout=timeout, headers=headers,
                                     follow_redirects=True) as c:
            r = await c.get(f"https://www.douyin.com/video/{aweme_id}")
            if r.status_code != 200:
                return None
            html = r.text
            # Douyin nhung JSON trong <script id="RENDER_DATA">... (url-encoded)
            for pat in (r'<script id="RENDER_DATA"[^>]*>(.*?)</script>',
                        r"window\._ROUTER_DATA\s*=\s*(\{.*?\})\s*</script>",
                        r'"aweme_detail":(\{.*?\}),"'):
                for m in re.finditer(pat, html, re.S):
                    raw = m.group(1)
                    try:
                        from urllib.parse import unquote
                        obj = json.loads(unquote(raw))
                        # dao sau tim aweme_detail
                        found = _deep_find_aweme(obj)
                        if found:
                            return found
                    except Exception:
                        continue
            return None
    except Exception:
        return None


def _deep_find_aweme(obj: Any, depth: int = 0) -> Optional[Dict[str, Any]]:
    if depth > 6 or obj is None:
        return None
    if isinstance(obj, dict):
        if "aweme_id" in obj and ("video" in obj or "image_post_info" in obj
                                  or "author" in obj):
            return obj
        if isinstance(obj.get("aweme_detail"), dict):
            return obj["aweme_detail"]
        for v in list(obj.values())[:40]:
            found = _deep_find_aweme(v, depth + 1)
            if found:
                return found
    elif isinstance(obj, list):
        for v in obj[:20]:
            found = _deep_find_aweme(v, depth + 1)
            if found:
                return found
    return None


def _first_url(obj: Any) -> str:
    if isinstance(obj, str):
        return obj if obj.startswith("http") else ""
    if isinstance(obj, dict):
        for k in ("url_list", "urlList"):
            v = obj.get(k)
            if isinstance(v, list):
                for s in v:
                    if isinstance(s, str) and s.startswith("http"):
                        return s
        u = obj.get("url")
        if isinstance(u, str) and u.startswith("http"):
            return u
    if isinstance(obj, list):
        for s in obj:
            r = _first_url(s)
            if r:
                return r
    return ""


def _all_urls(obj: Any, acc: List[str]) -> List[str]:
    if isinstance(obj, str):
        if obj.startswith("http"):
            acc.append(obj)
    elif isinstance(obj, dict):
        for k in ("url_list", "urlList"):
            v = obj.get(k)
            if isinstance(v, list):
                for s in v:
                    _all_urls(s, acc)
        _all_urls(obj.get("url", ""), acc)
    elif isinstance(obj, list):
        for s in obj:
            _all_urls(s, acc)
    return acc


def _best_video_url(video: Dict[str, Any]) -> tuple[str, int, int]:
    """Chon bitrate cao nhat trong bit_rate[]; fallback play_addr. Tra (url,w,h)."""
    best = ""
    bw = int(video.get("width") or 0)
    bh = int(video.get("height") or 0)
    best_rate = -1
    for br in (video.get("bit_rate") or []):
        if not isinstance(br, dict):
            continue
        rate = int(br.get("bit_rate") or br.get("bitrate") or 0)
        u = _first_url(br.get("play_addr") or br)
        if u and rate >= best_rate:
            best_rate = rate
            best = u
            bw = int(br.get("width") or bw)
            bh = int(br.get("height") or bh)
    if not best:
        best = _first_url(video.get("play_addr") or {})
    return best, bw, bh


def _gallery_urls(detail: Dict[str, Any]) -> List[str]:
    ipi = detail.get("image_post_info") or {}
    items: List[Any] = []
    if isinstance(ipi, dict):
        for k in ("images", "image_list"):
            v = ipi.get(k)
            if isinstance(v, list) and v:
                items = v
                break
    if not items:
        v = detail.get("images") or detail.get("image_list") or []
        items = v if isinstance(v, list) else []
    out: List[str] = []
    for it in items[:35]:
        if not isinstance(it, dict):
            continue
        # uu tien ban goc khong watermark
        cand = None
        for key in ("watermark_free_download_url_list", "origin_image",
                    "display_image", "download_url_list"):
            urls = _all_urls(it.get(key), [])
            if urls:
                webp = [u for u in urls if ".webp" in u.split("?")[0]]
                cand = (webp[0] if webp else urls[0])
                break
        if not cand:
            urls = _all_urls(it, [])
            cand = urls[0] if urls else ""
        if cand:
            out.append(cand)
    return out


def normalize_detail(detail: Dict[str, Any], resolved_url: str = "",
                     original_text: str = "") -> Dict[str, Any]:
    """Chuan hoa aweme_detail tho -> schema UI dang dung (giong contract cu)."""
    author = detail.get("author") or {}
    stats = detail.get("statistics") or {}
    video = detail.get("video") or {}
    music = detail.get("music") or {}
    aweme_id = str(detail.get("aweme_id") or "")
    nickname = str(author.get("nickname") or "")
    sec_uid = str(author.get("sec_uid") or author.get("sec_id") or "")
    desc = str(detail.get("desc") or "")[:500]
    create_ts = detail.get("create_time")

    images = _gallery_urls(detail)
    is_gallery = bool(images) or "image_post_info" in detail
    if is_gallery:
        media_type = "gallery"
        play_url, w, h = "", 0, 0
        duration = 0.0
    else:
        media_type = "video"
        play_url, w, h = _best_video_url(video)
        try:
            duration = float(video.get("duration") or detail.get("duration") or 0) / 1000.0
            if duration <= 0:
                duration = float(detail.get("duration") or 0)
        except Exception:
            duration = 0.0

    cover = _first_url(video.get("cover") or detail.get("video_cover") or {})
    if not cover:
        cover = _first_url((video.get("origin_cover") or {}))

    return {
        "type": "gallery" if is_gallery else "video",
        "media_type": media_type,
        "aweme_id": aweme_id,
        "author_nickname": nickname,
        "author_sec_uid": sec_uid,
        "desc": desc,
        "duration_s": round(duration, 1),
        "width": w,
        "height": h,
        "quality": quality_from_size(w, h),
        "date": date_from_ts(create_ts),
        "create_timestamp": int(create_ts) if str(create_ts).isdigit() else 0,
        "play_count": int(stats.get("play_count") or 0),
        "digg_count": int(stats.get("digg_count") or 0),
        "comment_count": int(stats.get("comment_count") or 0),
        "share_count": int(stats.get("share_count") or 0),
        "music_title": str(music.get("title") or "")[:80],
        "cover_url": cover,
        "images": images,
        "image_count": len(images),
        "play_url": play_url,  # noi bo: server dung de tai
        "resolved": resolved_url,
        "original": original_text,
    }


def extract_mix_id(text: str) -> str:
    """Lay mix_id tu URL hoac doan share-text (collection/mix)."""
    m = MIX_RE.search(text or "")
    return m.group(1) if m else ""


async def fetch_mix_page(mix_id: str, cursor: int, count: int,
                         cookies: Dict[str, str],
                         timeout: float = 25.0) -> Dict[str, Any]:
    """Lay 1 trang danh sach video trong collection (viet moi, chi dung HTTP cong khai).

    Tra ve {"items": [aweme_detail, ...], "next_cursor": int, "has_more": bool,
            "mix_name": str}. Bi chan -> items rong, has_more False.
    """
    headers = base_headers()
    if cookies:
        headers["Cookie"] = _cookie_header(cookies)
    params = {
        "device_platform": "webapp",
        "aid": "6383",
        "mix_id": mix_id,
        "cursor": int(cursor or 0),
        "count": max(1, min(int(count or 20), 50)),
        "version_code": "170400",
        "msToken": cookies.get("msToken") or random_mstoken(),
    }
    try:
        async with httpx.AsyncClient(timeout=timeout, headers=headers,
                                     follow_redirects=True) as c:
            r = await c.get("https://www.douyin.com/aweme/v1/web/mix/aweme/",
                            params=params)
            if r.status_code != 200:
                return {"items": [], "next_cursor": cursor,
                        "has_more": False, "mix_name": ""}
            data = r.json()
    except Exception:
        return {"items": [], "next_cursor": cursor,
                "has_more": False, "mix_name": ""}
    items = data.get("aweme_list") or data.get("aweme_details") or []
    if not isinstance(items, list):
        items = []
    mix_info = data.get("mix_info") or data.get("mix_detail") or {}
    name = ""
    if isinstance(mix_info, dict):
        name = str(mix_info.get("mix_name") or mix_info.get("name") or "")
    return {"items": items,
            "next_cursor": data.get("max_cursor") or data.get("cursor") or 0,
            "has_more": bool(data.get("has_more")),
            "mix_name": name}
