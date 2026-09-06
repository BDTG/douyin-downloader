"""Adapter HTTP trực tiếp tới api:8000, duck-type đúng interface mà DouyinPage cần.

DouyinPage gọi: sup.start(MID) / sup.stop(MID) / sup.call_op(MID, op, params).
Ở bản standalone không có module pipe — gọi thẳng HTTP, tự quản resolve 2 bước.
"""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from typing import Any, Dict, Optional
from uuid import uuid4

from .stackman import StackManager, port_open

API = "http://127.0.0.1:8000"
WEB = "http://127.0.0.1:8080"


def _http(method: str, path: str, body: Optional[dict] = None,
         timeout: float = 30.0) -> Any:
    data = json.dumps(body or {}).encode() if body is not None or method == "POST" else None
    req = urllib.request.Request(API + path, data=data, method=method,
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read().decode("utf-8", "replace")
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        try:
            detail = json.loads(e.read().decode("utf-8", "replace"))
            msg = detail.get("detail", str(e))
        except Exception:
            msg = str(e)
        raise RuntimeError(f"api {path} -> {e.code}: {msg}")


class LocalStack:
    """Giả supervisor cho DouyinPage: start/stop/call_op/ping."""

    def __init__(self, stack_dir: str):
        self.man = StackManager(stack_dir)
        self._resolves: Dict[str, dict] = {}

    # -- vòng đời (khớp Supervisor.start/stop(module_id)) --
    def start(self, _mid: str = "", timeout_s: float = 60.0):
        self.man.start(timeout_s=timeout_s)

    def stop(self, _mid: str = ""):
        self.man.stop()

    def ping(self, _mid: str = "") -> bool:
        return self.man.api_ok()

    @property
    def modules(self):
        return {"douyin-downloader": object()}

    # -- ops (khớp Supervisor.call_op(module_id, op, params)) --
    def call_op(self, _mid: str, op: str, params: Optional[dict] = None,
                timeout_s: float = 30.0) -> Any:
        params = params or {}
        if op == "getStatus":
            st = self.man.status()
            return {"ok": True, "data": {
                "running": all(st.values()),
                "services": [{"name": k, "listening": v} for k, v in st.items()],
                "api": "ok" if self.man.api_ok() else "down"}}
        if op == "uiUrls":
            return {"ok": True, "data": {
                "gallery": WEB + "/gallery/",
                "files": WEB + "/files/", "apiHealth": API + "/api/v1/health"}}
        if op == "resolve":
            # api trả full ngay (không nền như module) -> gói kiểu resolveResult
            v = _http("POST", "/api/v1/resolve", {"url": params.get("url", "")},
                      timeout_s)
            rid = f"d{uuid4().hex[:8]}"
            self._resolves[rid] = v
            if len(self._resolves) > 50:
                self._resolves.pop(next(iter(self._resolves)))
            return {"ok": True, "data": {"pending": True, "id": rid}}
        if op == "resolveResult":
            v = self._resolves.get(str(params.get("id", "")))
            if v is None:
                return {"ok": False, "error": "khong co resolve id"}
            return {"ok": True, "data": {"done": True, "id": params.get("id"), "result": v}}
        if op == "download":
            try:
                j = _http("POST", "/api/v1/download", {"url": params.get("url", "")},
                          timeout_s)
            except RuntimeError as e:
                return {"ok": False, "error": str(e)}
            return {"ok": True, "data": {"job_id": j.get("job_id", ""), **j}}
        if op == "jobStatus":
            jid = str(params.get("job_id", ""))
            try:
                j = _http("GET", f"/api/v1/jobs/{jid}", timeout_s)
            except RuntimeError as e:
                if "404" in str(e):
                    return {"ok": False, "error": "job not found (404)"}
                raise
            return {"ok": True, "data": j}
        if op == "downloadImages":
            try:
                r = _http("POST", "/api/v1/download_images",
                          {"url": params.get("url", ""), "aweme_id": params.get("aweme_id", ""),
                           "indices": params.get("indices", [])}, timeout_s)
            except RuntimeError as e:
                return {"ok": False, "error": str(e)}
            return {"ok": True, "data": r}
        if op == "localinfo":
            try:
                r = _http("POST", "/api/v1/localinfo", {"path": params.get("path", "")},
                          timeout_s)
            except RuntimeError as e:
                return {"ok": False, "error": str(e)}
            return {"ok": True, "data": r}
        if op == "videsc":
            try:
                from urllib.parse import quote
                r = _http("GET", "/api/v1/videsc?text=" + quote(str(params.get("text", ""))),
                          timeout_s + 40)
            except RuntimeError:
                return {"ok": True, "data": {"desc_vi": ""}}
            return {"ok": True, "data": r}
        raise RuntimeError(f"unknown op {op}")
