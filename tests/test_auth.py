"""Tests auth noi bo (offline)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "engine"))

from core.auth import (  # noqa: E402
    auth_status,
    ensure_mstoken,
    sanitize_cookies,
    validate_cookies,
)


def test_sanitize():
    out = sanitize_cookies({"ttwid": " abc ", "x": "", "y": None, " k ": "v"})
    assert out == {"ttwid": "abc", "k": "v"}


def test_validate_missing():
    ok, missing = validate_cookies({})
    assert not ok
    assert "ttwid" in missing and "msToken" in missing


def test_validate_ok():
    ck = {"ttwid": "a", "msToken": "m" * 107, "odin_tt": "b",
          "passport_csrf_token": "c"}
    ok, missing = validate_cookies(ck)
    assert ok and missing == []


def test_ensure_mstoken():
    out = ensure_mstoken({"ttwid": "a"})
    assert len(out["msToken"]) >= 50
    keep = {"msToken": "m" * 107}
    assert ensure_mstoken(keep)["msToken"] == "m" * 107


def test_auth_status_shape():
    st = auth_status({"ttwid": "a"})
    assert st["has_cookie"] is True
    assert st["ok"] is False
    assert "msToken" in st["missing"]
