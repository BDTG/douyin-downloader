"""FastAPI REST 服务入口。

HTTP 层薄封装：
- 接收 URL，创建 job，返回 job_id
- 实际下载委托给 cli.main.download_url 的简化复用

fastapi/uvicorn 是**可选**依赖。若未安装，导入本模块会 ImportError。
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Dict, List, Optional
import json
import re

import aiohttp
import asyncio

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from auth import CookieManager
from config import ConfigLoader
from control import QueueManager, RateLimiter, RetryHandler
from core import UNSUPPORTED_URL_TYPE_DETAIL, DouyinAPIClient, DownloaderFactory, URLParser
from server.jobs import JobManager
from storage import FileManager
from utils.logger import setup_logger
from utils.validators import is_short_url, normalize_short_url, sanitize_filename

logger = setup_logger("REST")


class DownloadRequest(BaseModel):
    url: str


class ResolveRequest(BaseModel):
    url: str


class LocalInfoRequest(BaseModel):
    # duong dan tuong doi trong thu muc tai (giong gallery api/file?path=...)
    path: str


def _load_aliases() -> Dict[str, str]:
    import os as _os
    cands = [Path('/app/aliases.json'), Path('aliases.json')]
    if _os.environ.get('ALIAS_PATH'):
        cands.insert(0, Path(_os.environ['ALIAS_PATH']))
    cands.append(Path(__file__).resolve().parents[2] / 'aliases.json')
    for p in cands:
        try:
            if p.exists():
                d = json.loads(p.read_text(encoding="utf-8"))
                if isinstance(d, dict):
                    return {k: v for k, v in d.items() if not k.startswith("_")}
        except Exception:
            pass
    return {}


def _extract_aweme_id(*urls: str) -> Optional[str]:
    for u in urls:
        if not u:
            continue
        m = re.search(r"/video/(\d+)", u)
        if m:
            return m.group(1)
        m = re.search(r"modal_id=(\d+)", u)
        if m:
            return m.group(1)
        m = re.search(r"/(?:note|slides|gallery)/(\d+)", u)
        if m:
            return m.group(1)
    return None


def _all_http(o, acc):
    """Gom TAT CA url http trong obj (giu thu tu), de chon loc (uu tien webp)."""
    if isinstance(o, str):
        if o.startswith("http"):
            acc.append(o)
    elif isinstance(o, dict):
        for k in ("url_list", "urlList"):
            v = o.get(k)
            if isinstance(v, list):
                for s in v:
                    _all_http(s, acc)
        _all_http(o.get("url", ""), acc)
    elif isinstance(o, list):
        for s in o:
            _all_http(s, acc)
    return acc


def _first_http(o):
    """Lay URL http dau tien trong obj (str/dict url_list/danh sach long nhau)."""
    if isinstance(o, str):
        return o if o.startswith("http") else ""
    if isinstance(o, dict):
        for k in ("url_list", "urlList"):
            v = o.get(k)
            if isinstance(v, list):
                for s in v:
                    if isinstance(s, str) and s.startswith("http"):
                        return s
        u = o.get("url")
        if isinstance(u, str) and u.startswith("http"):
            return u
        return ""
    if isinstance(o, list):
        for s in o:
            r = _first_http(s)
            if r:
                return r
    return ""


def _best_image_url(item):
    """Anh ngon nhat 1 item gallery: khong watermark > goc > hien thi > fallback.
    Trong cung 1 muc uu tien: chon webp truoc (cung diem anh, nhe hon jpeg ~25-30%)."""
    if not isinstance(item, dict):
        return ""
    for c in (item.get("watermark_free_download_url_list"),
              item.get("origin_image"), item.get("display_image"),
              item, item.get("download_url_list")):
        urls = _all_http(c, [])
        if urls:
            for u in urls:
                if ".webp" in u.split("?")[0]:
                    return u
            return urls[0]
    return ""


def _gallery_items(detail):
    if not isinstance(detail, dict):
        return []
    ipi = detail.get("image_post_info")
    if isinstance(ipi, dict):
        for k in ("images", "image_list"):
            c = ipi.get(k)
            if isinstance(c, list) and c:
                return c
    c = detail.get("images") or detail.get("image_list") or []
    return c if isinstance(c, list) else []


class DownloadImagesRequest(BaseModel):
    url: str = ""
    aweme_id: str = ""
    indices: List[int] = []


_IMG_EXT = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp", "image/gif": ".gif"}
_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")


async def _fetch_image(session, url, headers, dest_noext, timeout_s=90):
    """Tai 1 anh CDN ve dia, tu nhan duoi file. Tra ve ten file hoac ''."""
    async with session.get(url, headers=headers,
                           timeout=aiohttp.ClientTimeout(total=timeout_s)) as resp:
        if resp.status != 200:
            return ""
        ext = _IMG_EXT.get((resp.headers.get("Content-Type") or "").split(";")[0].strip().lower(), "")
        if not ext:
            low = url.split("?")[0].lower()
            ext = next((e for e in (".png", ".webp", ".gif", ".jpeg", ".jpg") if low.endswith(e)), ".jpg")
            if ext == ".jpeg":
                ext = ".jpg"
        dest = dest_noext.with_suffix(ext)
        if dest.exists() and dest.stat().st_size > 0:
            return dest.name  # co roi thi dung lai, tinh la saved
        with open(dest, "wb") as f:
            async for chunk in resp.content.iter_chunked(1 << 16):
                if chunk:
                    f.write(chunk)
        return dest.name if dest.stat().st_size > 0 else ""


class JobResponse(BaseModel):
    job_id: str
    status: str
    url: str


class _ServerDeps:
    """跨请求复用的重量级依赖。

    REST 服务在进程生命周期内只需要一份 FileManager / RateLimiter / RetryHandler /
    QueueManager / CookieManager；每个请求重新构造既浪费又会触发文件系统 mkdir。
    DouyinAPIClient 由于持有 aiohttp.ClientSession，依旧按请求创建，避免跨请求泄漏
    连接状态或触发 "Session is closed" 错误。
    """

    def __init__(self, config: ConfigLoader):
        self.config = config
        # Resolve the cookie file path relative to the config file's directory
        # so the sidecar can find it regardless of its working directory (which
        # on macOS is often '/' when launched by Electron).
        if config.config_path:
            from pathlib import Path

            cookie_file = str(Path(config.config_path).resolve().parent / ".cookies.json")
        else:
            cookie_file = ".cookies.json"
        self.cookie_manager = CookieManager(cookie_file=cookie_file)
        # Load cookies from the config (env var / YAML cookie key) first, then
        # fall back to whatever is already on disk in the cookie file. This
        # ensures that cookies saved by a previous session are picked up on
        # restart even when the config doesn't embed them inline.
        initial_cookies = config.get_cookies()
        if initial_cookies:
            self.cookie_manager.set_cookies(initial_cookies)
        else:
            # Trigger a load from disk so get_cookies() returns the persisted
            # session without requiring a fresh login on every app restart.
            self.cookie_manager.get_cookies()
        self.file_manager = FileManager(config.get("path"))
        self.rate_limiter = RateLimiter(max_per_second=float(config.get("rate_limit", 2) or 2))
        self.retry_handler = RetryHandler(max_retries=int(config.get("retry_times", 3) or 3))
        self.queue_manager = QueueManager(max_workers=int(config.get("thread", 5) or 5))


class _JobProgressReporter:
    """Gom tien trinh byte tu downloader ve job de GET /jobs hien thanh bar + toc do.

    Downloader goi: update_step/set_item_total/advance_item (vi tri) va
    on_item_progress(aweme_id=..., bytes_read=..., bytes_total=...) theo tung chunk.
    """

    def __init__(self, job):
        self._job = job

    def update_step(self, step, detail=""):
        return None

    def set_item_total(self, total, detail=""):
        return None

    def advance_item(self, status, detail=""):
        return None

    def on_item_progress(self, aweme_id=None, bytes_read=0, bytes_total=0, **kw):
        try:
            self._job.downloaded_bytes = int(bytes_read or 0)
            self._job.total_bytes = int(bytes_total or 0)
            if aweme_id:
                self._job.current_aweme = str(aweme_id)
        except Exception:
            pass


async def _execute_download(url: str, deps: "_ServerDeps", job=None) -> Dict[str, int]:
    """简化版 download_url：只负责执行并返回成功/失败计数。

    有意不复用 cli.main.download_url —— 后者绑定了 progress_display 的 rich 状态。
    API client 仍按请求创建（aiohttp session 不跨请求复用）；其余重量级依赖从
    _ServerDeps 共享。
    """
    # proxy 与 cli.main.download_url 对齐:API 请求、短链解析和 CDN 媒体
    # 下载(downloader_base 读 api_client.proxy)统一走配置代理。
    async with DouyinAPIClient(
        deps.cookie_manager.get_cookies(),
        proxy=deps.config.get("proxy"),
    ) as api_client:
        if is_short_url(url):
            resolved = await api_client.resolve_short_url(normalize_short_url(url))
            if not resolved:
                raise RuntimeError(f"Failed to resolve short URL: {url}")
            url = resolved

        parsed = URLParser.parse(url)
        if not parsed:
            raise RuntimeError(f"Unsupported URL: {url}")
        # 能力门禁：解析得出来但永远不会有下载器的类型，给出真实原因。
        gated_detail = UNSUPPORTED_URL_TYPE_DETAIL.get(str(parsed.get("type") or ""))
        if gated_detail:
            raise RuntimeError(gated_detail)

        downloader = DownloaderFactory.create(
            parsed["type"],
            deps.config,
            api_client,
            deps.file_manager,
            deps.cookie_manager,
            None,  # database 不在 server 场景里启用，避免单例冲突
            deps.rate_limiter,
            deps.retry_handler,
            deps.queue_manager,
            progress_reporter=_JobProgressReporter(job) if job is not None else None,
        )
        if downloader is None:
            raise RuntimeError(f"No downloader for url_type={parsed['type']}")

        result = await downloader.download(parsed)
        return {
            "total": result.total,
            "success": result.success,
            "failed": result.failed,
            "skipped": result.skipped,
        }


def build_app(config: ConfigLoader) -> FastAPI:
    deps = _ServerDeps(config)

    async def executor(url: str, job=None) -> Dict[str, int]:
        """Giong cli.main.download_url nhung chay nen cho job (co bao tien trinh byte)."""
        return await _execute_download(url, deps, job)

    server_cfg = config.get("server") or {}
    if not isinstance(server_cfg, dict):
        server_cfg = {}
    manager = JobManager(
        executor=executor,
        max_concurrency=int(config.get("thread", 2) or 2),
        max_jobs=int(server_cfg.get("max_jobs") or JobManager.DEFAULT_MAX_JOBS),
        job_ttl_seconds=float(
            server_cfg.get("job_ttl_seconds") or JobManager.DEFAULT_JOB_TTL_SECONDS
        ),
    )

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        yield
        await manager.shutdown()

    app = FastAPI(
        title="Douyin Downloader API",
        version="1.0",
        description="REST API for dispatching Douyin download jobs.",
        lifespan=lifespan,
    )
    app.state.job_manager = manager
    app.state.deps = deps

    @app.get("/api/v1/health")
    async def health() -> Dict[str, str]:
        return {"status": "ok"}

    @app.post("/api/v1/download", response_model=JobResponse)
    async def create_job(req: DownloadRequest) -> JobResponse:
        if not req.url:
            raise HTTPException(status_code=400, detail="url is required")
        # Nguoi dung hay dan ca doan share text: tach link http dau tien (giong /resolve).
        m = re.search(r"https?://[^\s\"'<>]+", req.url)
        url = m.group(0).rstrip(".,!?)]}>;") if m else req.url.strip()
        if not url.startswith("http"):
            raise HTTPException(status_code=422, detail="khong tim thay link http trong doan text")
        job = await manager.submit(url)
        return JobResponse(job_id=job.job_id, status=job.status, url=job.url)

    @app.post("/api/v1/resolve")
    async def resolve(req: ResolveRequest) -> Dict[str, Any]:
        """Nhan dien tac gia cua 1 link truoc khi tai (dung cho nut Quet link).

        Tra ve: resolved url, aweme_id, author nickname/sec_uid, code (tu aliases.json), mo ta ngan.
        """
        url = (req.url or "").strip()
        if not url:
            raise HTTPException(status_code=400, detail="url is required")
        # Nguoi dung hay dan ca doan share text (chu + link): tach link http dau tien ra.
        m = re.search(r"https?://[^\s\"'<>]+", url)
        url = m.group(0).rstrip(".,!?)]}>;") if m else url
        if not url.startswith("http"):
            raise HTTPException(status_code=422, detail="khong tim thay link http trong doan text")
        async with DouyinAPIClient(
            deps.cookie_manager.get_cookies(),
            proxy=deps.config.get("proxy"),
        ) as api_client:
            resolved = url
            try:
                if is_short_url(url):
                    r = await api_client.resolve_short_url(normalize_short_url(url))
                    if r:
                        resolved = r
            except Exception:
                pass
            parsed = URLParser.parse(resolved) or URLParser.parse(url) or {}
            utype = str(parsed.get("type") or "")
            aweme_id = (
                parsed.get("aweme_id") or parsed.get("note_id") or _extract_aweme_id(resolved, url)
            )
            sec_uid = parsed.get("sec_uid")
            out: Dict[str, Any] = {
                "original": url,
                "resolved": resolved,
                "type": utype,
                "aweme_id": aweme_id,
                "author_nickname": "",
                "author_sec_uid": sec_uid or "",
                "code": "",
                "desc": "",
                "duration_s": 0,
                "width": 0,
                "height": 0,
                "date": "",
                "play_count": 0,
                "digg_count": 0,
                "comment_count": 0,
                "share_count": 0,
                "music_title": "",
                "cover_url": "",
                "images": [],
                "spec": "",
                "media_type": "",
                "image_count": 0,
            }
            # Link trang user: lay thong tin user truc tiep
            if utype == "user" and sec_uid:
                try:
                    info = await api_client.get_user_info(sec_uid)
                    if info:
                        user = info.get("user") or info
                        out["author_nickname"] = user.get("nickname", "")
                        out["author_sec_uid"] = user.get("sec_uid", sec_uid)
                except Exception as exc:
                    out["error"] = f"{type(exc).__name__}: {exc}"
            elif aweme_id:
                try:
                    detail = await api_client.get_video_detail(aweme_id)
                    if detail:
                        author = detail.get("author") or {}
                        out["author_nickname"] = author.get("nickname", "")
                        out["author_sec_uid"] = author.get("sec_uid", "")
                        out["desc"] = str(detail.get("desc", ""))[:120]
                        video = detail.get("video") or {}
                        stat = detail.get("statistics") or {}
                        try:
                            dur = video.get("duration") or detail.get("duration") or 0
                            out["duration_s"] = round(float(dur) / 1000, 1)
                        except Exception:
                            pass
                        out["width"] = int(video.get("width") or 0)
                        out["height"] = int(video.get("height") or 0)
                        for k in ("play_count", "digg_count", "comment_count", "share_count"):
                            try:
                                out[k] = int(stat.get(k) or 0)
                            except Exception:
                                pass
                        try:
                            from datetime import datetime, timezone, timedelta
                            ct = int(detail.get("create_time") or 0)
                            if ct:
                                out["date"] = (datetime.fromtimestamp(ct, tz=timezone.utc) + timedelta(hours=7)).strftime("%Y-%m-%d")
                        except Exception:
                            pass
                        try:
                            out["music_title"] = str((detail.get("music") or {}).get("title", ""))[:80]
                        except Exception:
                            pass
                        try:
                            from core.metadata import extract_video_cover_urls
                            covers = extract_video_cover_urls(detail)
                            if covers:
                                out["cover_url"] = covers[0]
                        except Exception:
                            pass
                        def _compact(n):
                            try:
                                n = int(n)
                            except Exception:
                                return "0"
                            if n >= 1000000:
                                s = f"{n/1000000:.1f}".rstrip("0").rstrip(".")
                                return s + "M"
                            if n >= 1000:
                                s = f"{n/1000:.1f}".rstrip("0").rstrip(".")
                                return s + "k"
                            return str(n)
                        items = []
                        try:
                            ipi = detail.get("image_post_info") or {}
                            if isinstance(ipi, dict):
                                for k in ("images", "image_list"):
                                    c = ipi.get(k)
                                    if isinstance(c, list) and c:
                                        items = c
                                        break
                            if not items:
                                c = detail.get("images") or detail.get("image_list") or []
                                if isinstance(c, list):
                                    items = c
                        except Exception:
                            items = []
                        if items:
                            out["media_type"] = "gallery"
                            out["image_count"] = len(items)
                            try:
                                out["images"] = [u for u in (_best_image_url(it) for it in items[:35]) if u]
                            except Exception:
                                out["images"] = []
                            try:
                                f0 = items[0] or {}
                                for wk, hk in (("width", "height"), ("image_width", "image_height")):
                                    if f0.get(wk) and f0.get(hk):
                                        out["width"] = int(f0[wk]); out["height"] = int(f0[hk])
                                        break
                            except Exception:
                                pass
                        else:
                            out["media_type"] = "video"
                        parts = []
                        # Nhan chat luong tu canh dai nhat (video doc Douyin: 2160x3840=4K, 1440x2560=QHD, 1080x1920=FHD, 720x1280=HD)
                        try:
                            long_side = max(int(out["width"] or 0), int(out["height"] or 0))
                        except Exception:
                            long_side = 0
                        quality = ""
                        if long_side >= 3400:
                            quality = "4K"
                        elif long_side >= 2500:
                            quality = "QHD"
                        elif long_side >= 1900:
                            quality = "FHD"
                        elif long_side >= 1200:
                            quality = "HD"
                        elif long_side > 0:
                            quality = "SD"
                        out["quality"] = quality
                        if out["media_type"] == "gallery":
                            parts.append(f"{out['image_count']} anh")
                        elif out["duration_s"]:
                            parts.append(f"{out['duration_s']}s")
                        if out["width"] and out["height"]:
                            parts.append(f"{out['width']}x{out['height']}" + (f" [{quality}]" if quality else ""))
                        if out["date"]:
                            parts.append(out["date"])
                        parts.append(f"play {_compact(out['play_count'])} tim {_compact(out['digg_count'])} bl {_compact(out['comment_count'])} share {_compact(out['share_count'])}")
                        out["spec"] = " | ".join(parts)
                except Exception as exc:
                    out["error"] = f"{type(exc).__name__}: {exc}"
            aliases = _load_aliases()
            sid = out.get("author_sec_uid") or ""
            if sid and sid in aliases:
                out["code"] = aliases[sid]
            try:
                from server.viname import hanviet_name
            except ImportError:
                from .viname import hanviet_name  # type: ignore
            try:
                out["name_vi"] = hanviet_name(out.get("author_nickname") or "").get("hanviet", "")
            except Exception:
                out["name_vi"] = ""
            return out

    @app.get("/api/v1/viname")
    async def viname(name: str = "") -> Dict[str, Any]:
        """Dich nickname Trung -> am Han-Viet (offline, kem ten Trung goc)."""
        try:
            from server.viname import hanviet_name
        except ImportError:
            from .viname import hanviet_name  # type: ignore
        return hanviet_name(name)

    @app.get("/api/v1/videsc")
    async def videsc(text: str = "") -> Dict[str, Any]:
        """Dich mo ta Trung -> Viet (Gemini free tier, cache file). Khong key -> rong."""
        import os as _os
        try:
            from server.videsc import translate_desc
        except ImportError:
            from .videsc import translate_desc  # type: ignore
        key = str(deps.config.get("gemini_api_key") or "") or _os.environ.get(
            "GEMINI_API_KEY", "") or _os.environ.get("GOOGLE_API_KEY", "")
        return {"original": text, "desc_vi": translate_desc(text, key)}

    @app.post("/api/v1/user_posts")
    async def user_posts(req: Dict[str, Any]) -> Dict[str, Any]:
        """Liet ke post cua 1 acc (chon tung video de tai). Body: {url|sec_uid, cursor, count}."""
        from datetime import datetime, timezone, timedelta
        url = str((req or {}).get("url") or "").strip()
        sec_uid = str((req or {}).get("sec_uid") or "").strip()
        try:
            cursor = int((req or {}).get("cursor") or 0)
        except Exception:
            cursor = 0
        try:
            count = min(50, max(1, int((req or {}).get("count") or 20)))
        except Exception:
            count = 20
        async with DouyinAPIClient(
            deps.cookie_manager.get_cookies(),
            proxy=deps.config.get("proxy"),
        ) as api_client:
            if not sec_uid and url:
                m = re.search(r"https?://[^\s\"'<>]+", url)
                u = m.group(0).rstrip(".,!?)]}>;") if m else url
                if is_short_url(u):
                    try:
                        r = await api_client.resolve_short_url(normalize_short_url(u))
                        if r:
                            u = r
                    except Exception:
                        pass
                parsed = URLParser.parse(u) or {}
                sec_uid = str(parsed.get("sec_uid") or "")
            if not sec_uid:
                raise HTTPException(status_code=422, detail="khong tim thay user (can link trang ca nhan)")
            try:
                page = await api_client.get_user_post(sec_uid, cursor, count)
            except Exception as exc:
                raise HTTPException(status_code=502, detail=f"Douyin loi: {type(exc).__name__}")
            items = page.get("aweme_list") or page.get("items") or []
            out = []
            for it in items:
                if not isinstance(it, dict):
                    continue
                aid = str(it.get("aweme_id") or "")
                if not aid:
                    continue
                video = it.get("video") or {}
                stat = it.get("statistics") or {}
                try:
                    dur = round(float(video.get("duration") or it.get("duration") or 0) / 1000, 1)
                except Exception:
                    dur = 0
                try:
                    ct = int(it.get("create_time") or 0)
                    date = (datetime.fromtimestamp(ct, tz=timezone.utc) + timedelta(hours=7)).strftime("%Y-%m-%d") if ct else ""
                except Exception:
                    date = ""
                cover = ""
                try:
                    from core.metadata import extract_video_cover_urls
                    covers = extract_video_cover_urls(it)
                    if covers:
                        cover = covers[0]
                except Exception:
                    pass
                ipi = it.get("image_post_info") or {}
                imgs = []
                if isinstance(ipi, dict):
                    for k in ("images", "image_list"):
                        c = ipi.get(k)
                        if isinstance(c, list) and c:
                            imgs = c
                            break
                out.append({
                    "aweme_id": aid,
                    "desc": str(it.get("desc") or "")[:120],
                    "cover_url": cover,
                    "duration_s": dur,
                    "width": int(video.get("width") or 0),
                    "height": int(video.get("height") or 0),
                    "date": date,
                    "digg_count": int(stat.get("digg_count") or 0),
                    "comment_count": int(stat.get("comment_count") or 0),
                    "share_count": int(stat.get("share_count") or 0),
                    "play_count": int(stat.get("play_count") or 0),
                    "media_type": "gallery" if imgs else "video",
                    "image_count": len(imgs),
                    "music_title": str((it.get("music") or {}).get("title") or "")[:60],
                })
            return {"sec_uid": sec_uid, "cursor": cursor,
                    "next_cursor": page.get("max_cursor") or page.get("cursor") or 0,
                    "has_more": bool(page.get("has_more", True)) and bool(out),
                    "items": out}

    @app.post("/api/v1/download_images")
    async def download_images(req: DownloadImagesRequest) -> Dict[str, Any]:
        """Tai rieng cac anh trong post gallery. indices rong = tat ca (toi da 35)."""
        try:
            want = sorted({int(i) for i in (req.indices or []) if int(i) >= 0})
        except Exception:
            want = []
        async with DouyinAPIClient(
            deps.cookie_manager.get_cookies(),
            proxy=deps.config.get("proxy"),
        ) as api_client:
            aweme_id = (req.aweme_id or "").strip()
            if not aweme_id:
                raw = (req.url or "").strip()
                m = re.search(r"https?://[^\s\"'<>]+", raw)
                url = m.group(0).rstrip(".,!?)]}>;") if m else raw
                if is_short_url(url):
                    url = await api_client.resolve_short_url(normalize_short_url(url)) or url
                parsed = URLParser.parse(url) or {}
                aweme_id = str(parsed.get("aweme_id") or parsed.get("note_id")
                               or _extract_aweme_id(url) or "")
            if not aweme_id:
                raise HTTPException(status_code=422, detail="khong xac dinh duoc aweme_id")
            detail = await api_client.get_video_detail(aweme_id)
            if not detail:
                raise HTTPException(status_code=404, detail="khong lay duoc chi tiet")
            items = _gallery_items(detail)
            if not items:
                raise HTTPException(status_code=422, detail="post nay khong phai dang anh")
            all_urls = [u for u in (_best_image_url(it) for it in items) if u]
            pairs = [(i, all_urls[i]) for i in want if i < len(all_urls)] if want \
                else list(enumerate(all_urls))
            pairs = pairs[:35]
            if not pairs:
                raise HTTPException(status_code=422, detail="khong trich duoc URL anh")
            author = detail.get("author") or {}
            sec = str(author.get("sec_uid") or "unknown")
            nick = str(author.get("nickname") or "")
            try:
                from datetime import datetime, timezone, timedelta
                ct = int(detail.get("create_time") or 0)
                date = (datetime.fromtimestamp(ct, tz=timezone.utc)
                        + timedelta(hours=7)).strftime("%Y-%m-%d") if ct else ""
            except Exception:
                date = ""
            stem = sanitize_filename(
                f"{date + '_' if date else ''}{str(detail.get('desc') or '')[:60]}_{aweme_id}", 120)
            base = Path(deps.file_manager.base_path)
            folder = base / sec / stem
            folder.mkdir(parents=True, exist_ok=True)
            cookies = deps.cookie_manager.get_cookies() or {}
            headers = {"User-Agent": _UA, "Referer": "https://www.douyin.com/",
                       "Cookie": "; ".join(f"{k}={v}" for k, v in cookies.items())}
            saved: List[str] = []
            failed: List[Dict[str, Any]] = []
            sem = asyncio.Semaphore(4)

            async def one(idx: int, u: str):
                async with sem:
                    try:
                        async with aiohttp.ClientSession() as session:
                            name = await _fetch_image(
                                session, u, headers, folder / f"{stem}_img{idx:02d}")
                        if name:
                            saved.append(name)
                        else:
                            failed.append({"index": idx, "error": "empty"})
                    except Exception as exc:
                        failed.append({"index": idx, "error": f"{type(exc).__name__}"})

            await asyncio.gather(*[one(i, u) for i, u in pairs])
            try:
                tags = sorted(set(re.findall(r"#(\S+)", str(detail.get("desc") or ""))))[:10]
                rec = {"aweme_id": aweme_id, "author_sec_uid": sec, "author_name": nick,
                       "desc": str(detail.get("desc") or "")[:120], "date": date,
                       "media_type": "gallery", "tags": tags, "file_names": sorted(saved)}
                with open(base / "download_manifest.jsonl", "a", encoding="utf-8") as f:
                    f.write(json.dumps(rec, ensure_ascii=False) + "\n")
            except Exception:
                pass
            try:
                rel = str(folder.relative_to(base.resolve()))
            except Exception:
                rel = str(folder)
            return {"aweme_id": aweme_id, "saved": sorted(saved),
                    "failed": failed, "dir": rel, "total_images": len(all_urls)}

    @app.post("/api/v1/localinfo")
    async def localinfo(req: LocalInfoRequest) -> Dict[str, Any]:
        """Doc thong so tu FILE LOCAL (ffprobe) — khong goi Douyin, khong ton acc."""
        import asyncio
        from pathlib import Path as _P
        base = _P(deps.file_manager.base_path).resolve()
        try:
            rp = (base / (req.path or "")).resolve()
            rp.relative_to(base)
        except Exception:
            raise HTTPException(status_code=400, detail="bad path")
        if not rp.is_file():
            raise HTTPException(status_code=404, detail="not found")
        try:
            pr = await asyncio.create_subprocess_exec(
                "ffprobe", "-v", "quiet", "-print_format", "json",
                "-show_format", "-show_streams", str(rp),
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
            out, _ = await asyncio.wait_for(pr.communicate(), timeout=30)
            info = json.loads(out or b"{}")
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"ffprobe failed: {exc}")
        streams = info.get("streams") or []
        v = next((s for s in streams if s.get("codec_type") == "video"), {})
        fmt = info.get("format") or {}
        try:
            dur = float(fmt.get("duration") or 0)
        except Exception:
            dur = 0
        size = rp.stat().st_size
        br = 0
        try:
            br = int(fmt.get("bit_rate") or 0)
        except Exception:
            pass
        if not br and dur:
            br = int(size * 8 / dur)
        return {
            "name": rp.name,
            "size": size,
            "duration_s": round(dur, 1),
            "width": int(v.get("width") or 0),
            "height": int(v.get("height") or 0),
            "vcodec": str(v.get("codec_name") or ""),
            "bitrate_kbps": int(br // 1000),
        }

    @app.get("/api/v1/jobs/{job_id}")
    async def get_job(job_id: str) -> Dict[str, Any]:
        job = await manager.get(job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="job not found")
        return job.to_dict()

    @app.get("/api/v1/jobs")
    async def list_jobs() -> Dict[str, List[Dict[str, Any]]]:
        jobs = await manager.list_jobs()
        return {"jobs": [j.to_dict() for j in jobs]}

    return app


async def run_server(config: ConfigLoader, *, host: str, port: int) -> None:
    import uvicorn

    app = build_app(config)
    uv_config = uvicorn.Config(app, host=host, port=port, log_level="info")
    server = uvicorn.Server(uv_config)
    await server.serve()
