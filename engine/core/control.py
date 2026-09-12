"""Dieu toc + thu lai mini (viet moi, chi dung stdlib asyncio/time).

- RateLimiter: dam bao khong goi API qua nhanh (mac dinh 2 req/s).
- with_retry: thu lai loi mang voi backoff 1s, 2s, 5s.
"""
from __future__ import annotations

import asyncio
import time
from typing import Any, Awaitable, Callable

BACKOFFS = (1.0, 2.0, 5.0)


class RateLimiter:
    def __init__(self, rate_per_sec: float = 2.0):
        self.interval = 1.0 / max(float(rate_per_sec or 1), 0.01)
        self._lock = asyncio.Lock()
        self._last = 0.0

    async def acquire(self) -> None:
        async with self._lock:
            now = time.monotonic()
            wait = self._last + self.interval - now
            if wait > 0:
                await asyncio.sleep(wait)
            self._last = time.monotonic()


async def with_retry(fn: Callable[[], Awaitable[Any]],
                     retries: int = 3) -> Any:
    """Goi fn() toi da 1+retries lan, nghi theo BACKOFFS giua cac lan loi."""
    last: Exception | None = None
    for attempt in range(max(0, int(retries)) + 1):
        try:
            return await fn()
        except Exception as e:  # noqa: BLE001
            last = e
            if attempt < retries:
                await asyncio.sleep(BACKOFFS[min(attempt, len(BACKOFFS) - 1)])
    if last is not None:
        raise last
    raise RuntimeError("retry that bai")
