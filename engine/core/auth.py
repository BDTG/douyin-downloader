"""Quan ly cookie + msToken noi bo (viet moi, chi dung stdlib).

- sanitize: cat khoang trang, bo value rong
- validate: bao thieu key quan trong (khong chan cung, de resolve public van chay)
- ensure_mstoken: thieu/ngan qua -> sinh random du dai
"""
from __future__ import annotations

from typing import Dict, List, Tuple

from core.douyin import random_mstoken

IMPORTANT_KEYS = ("ttwid", "msToken", "odin_tt", "passport_csrf_token")
OPTIONAL_KEYS = ("sid_guard", "sid_tt", "ssid", "passport_csrf_token_default")


def sanitize_cookies(raw: Dict[str, object]) -> Dict[str, str]:
    clean: Dict[str, str] = {}
    for k, v in (raw or {}).items():
        key = str(k or "").strip()
        val = str(v or "").strip().strip('"').strip("'")
        if key and val:
            clean[key] = val
    return clean


def validate_cookies(cookies: Dict[str, str]) -> Tuple[bool, List[str]]:
    """Tra (ok, missing). ok=True khi du 4 key quan trong + msToken dai."""
    missing = [k for k in IMPORTANT_KEYS if not (cookies.get(k) or "").strip()]
    ms = (cookies.get("msToken") or "")
    if "msToken" not in missing and len(ms) < 50:
        missing.append("msToken")
    return (len(missing) == 0, missing)


def ensure_mstoken(cookies: Dict[str, str]) -> Dict[str, str]:
    out = dict(cookies or {})
    ms = str(out.get("msToken") or "")
    if len(ms) < 50:
        out["msToken"] = random_mstoken()
    return out


def auth_status(cookies: Dict[str, str]) -> Dict[str, object]:
    ok, missing = validate_cookies(cookies or {})
    keys = sorted((cookies or {}).keys())
    return {"ok": ok, "missing": missing, "keys": keys,
            "has_cookie": len(keys) > 0}
