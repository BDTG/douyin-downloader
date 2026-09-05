"""Dich mo ta video Trung -> Viet bang Gemini (free tier), co cache file.

Key: config `gemini_api_key`, hoac env GEMINI_API_KEY / GOOGLE_API_KEY.
Khong key -> tra {"desc_vi": ""} (UI giu nguyen tieng Trung).
Cache: engine/var/vi_desc.json {text: desc_vi} — khong commit.
Ten rieng (nickname) KHONG dich o day: giu am Han-Viet (viname.py),
AI hay dich ten thanh nghia, sai cach goi.
"""
from __future__ import annotations

import json
import urllib.request
from functools import lru_cache
from pathlib import Path
from typing import Dict

MODEL = "gemini-3.6-flash"
_CACHE = Path(__file__).resolve().parents[2] / "var" / "vi_desc.json"


def _load_cache() -> Dict[str, str]:
    try:
        return json.loads(_CACHE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_cache(c: Dict[str, str]) -> None:
    try:
        _CACHE.parent.mkdir(parents=True, exist_ok=True)
        _CACHE.write_text(json.dumps(c, ensure_ascii=False), encoding="utf-8")
    except Exception:
        pass


def has_cjk(s: str) -> bool:
    return any("\u4e00" <= ch <= "\u9fff" for ch in (s or ""))


def translate_desc(text: str, api_key: str, timeout_s: float = 60.0) -> str:
    text = (text or "").strip()
    if not text or not has_cjk(text) or not api_key:
        return ""
    cache = _load_cache()
    if text in cache:
        return cache[text]
    body = json.dumps({
        "contents": [{"parts": [{"text":
            "Dich mo ta video Douyin sang tieng Viet tu nhien, chi tra ban dich, "
            "giu hashtag va ten rieng goc: " + text}]}]},
    ).encode()
    url = (f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}"
           f":generateContent?key={api_key}")
    try:
        req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"})
        d = json.load(urllib.request.urlopen(req, timeout=timeout_s))
        out = str(d["candidates"][0]["content"]["parts"][0]["text"]).strip()
    except Exception:
        return ""
    if out:
        cache[text] = out
        _save_cache(cache)
    return out
