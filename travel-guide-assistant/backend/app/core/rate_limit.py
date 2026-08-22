"""Small in-memory limits for the public demo deployment."""
from __future__ import annotations

import asyncio
import time
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass
from math import ceil
from typing import Any


@dataclass(frozen=True)
class RateLimitResult:
    allowed: bool
    retry_after: int = 0


@dataclass
class _Bucket:
    count: int
    reset_at: float


class FixedWindowRateLimiter:
    """A process-local fixed-window limiter suitable for a single demo instance."""

    def __init__(
        self,
        limit: int,
        window_seconds: int,
        *,
        clock: Callable[[], float] = time.monotonic,
    ):
        if limit < 1:
            raise ValueError("limit must be positive")
        if window_seconds < 1:
            raise ValueError("window_seconds must be positive")

        self.limit = limit
        self.window_seconds = window_seconds
        self._clock = clock
        self._buckets: dict[str, _Bucket] = {}
        self._lock = asyncio.Lock()

    async def check(self, key: str) -> RateLimitResult:
        now = self._clock()

        async with self._lock:
            self._remove_expired(now)
            bucket = self._buckets.get(key)
            if bucket is None:
                bucket = _Bucket(count=0, reset_at=now + self.window_seconds)
                self._buckets[key] = bucket

            if bucket.count >= self.limit:
                return RateLimitResult(
                    allowed=False,
                    retry_after=max(1, ceil(bucket.reset_at - now)),
                )

            bucket.count += 1
            return RateLimitResult(allowed=True)

    def _remove_expired(self, now: float) -> None:
        expired = [key for key, bucket in self._buckets.items() if bucket.reset_at <= now]
        for key in expired:
            self._buckets.pop(key, None)


class ChatRateLimitGuard:
    """Combines a per-client limit with a process-wide daily demo budget."""

    def __init__(
        self,
        *,
        per_ip_limit: int,
        per_ip_window_seconds: int,
        global_limit: int,
        global_window_seconds: int,
        clock: Callable[[], float] = time.monotonic,
    ):
        self._per_ip = FixedWindowRateLimiter(
            per_ip_limit,
            per_ip_window_seconds,
            clock=clock,
        )
        self._global = FixedWindowRateLimiter(
            global_limit,
            global_window_seconds,
            clock=clock,
        )

    async def check(self, client_key: str) -> RateLimitResult:
        per_ip = await self._per_ip.check(client_key)
        if not per_ip.allowed:
            return per_ip
        return await self._global.check("all")


class ConcurrencyLimiter:
    """Limits active async streams and releases slots on completion or cancellation."""

    def __init__(self, limit: int):
        if limit < 1:
            raise ValueError("limit must be positive")
        self._semaphore = asyncio.Semaphore(limit)

    async def stream(self, source: AsyncIterator[Any]) -> AsyncIterator[Any]:
        await self._semaphore.acquire()
        try:
            async for item in source:
                yield item
        finally:
            self._semaphore.release()


def get_client_key(request: Any) -> str:
    """Return the proxy-provided client IP, falling back to the socket peer."""
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",", 1)[0].strip()

    client = getattr(request, "client", None)
    return getattr(client, "host", None) or "unknown"
