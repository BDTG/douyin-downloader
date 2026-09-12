"""Tests control mini (offline)."""
import asyncio
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "engine"))

from core.control import RateLimiter, with_retry  # noqa: E402


def test_retry_thanh_cong_sau_loi():
    calls = {"n": 0}

    async def flaky():
        calls["n"] += 1
        if calls["n"] < 3:
            raise RuntimeError("loi mang")
        return "ok"

    assert asyncio.run(with_retry(flaky, retries=3)) == "ok"
    assert calls["n"] == 3


def test_retry_het_luot():
    async def fail():
        raise RuntimeError("chet")

    try:
        asyncio.run(with_retry(fail, retries=1))
        assert False, "phai nem loi"
    except RuntimeError:
        pass


def test_rate_limiter_gian_cach():
    async def run():
        lim = RateLimiter(10.0)  # 0.1s/lan
        t0 = time.monotonic()
        await lim.acquire()
        await lim.acquire()
        return time.monotonic() - t0

    dt = asyncio.run(run())
    assert dt >= 0.09
