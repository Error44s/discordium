"""Per-route rate limiter respecting Discord's bucket system.

Handles both per-route and global rate limits using asyncio primitives.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections import defaultdict

logger = logging.getLogger("discordium.http")


class RateLimiter:
    """Async rate limiter that mirrors Discord's bucket model.

    Each route gets its own semaphore. On 429 responses the limiter
    sleeps for the ``Retry-After`` duration automatically.
    """

    __slots__ = ("_locks", "_global_event", "_global_until")

    def __init__(self) -> None:
        self._locks: dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)
        self._global_event = asyncio.Event()
        self._global_event.set()  # not rate-limited initially
        self._global_until: float = 0.0

    def _bucket_key(self, method: str, path: str) -> str:
        """Derive a bucket key from method + major parameters."""
        parts = path.split("/")
        # Major params: channel_id, guild_id, webhook_id
        major = []
        for i, segment in enumerate(parts):
            if i > 0 and parts[i - 1] in ("channels", "guilds", "webhooks"):
                major.append(segment)
        return f"{method}:{':'.join(major) or path}"

    async def acquire(self, method: str, path: str) -> str:
        """Wait until this route is safe to call. Returns the bucket key."""
        # Wait for global rate limit to clear
        await self._global_event.wait()

        key = self._bucket_key(method, path)
        await self._locks[key].acquire()
        return key

    def release(
        self,
        key: str,
        *,
        remaining: int | None = None,
        reset_after: float | None = None,
        is_global: bool = False,
    ) -> None:
        """Release the lock, optionally scheduling a delay for the next request."""
        if is_global and reset_after:
            self._global_event.clear()
            self._global_until = time.monotonic() + reset_after
            asyncio.get_event_loop().call_later(reset_after, self._global_event.set)
            logger.warning("Global rate limit hit — pausing %.2fs", reset_after)

        lock = self._locks.get(key)
        if lock and lock.locked():
            if remaining == 0 and reset_after:
                # Schedule release after the reset window
                asyncio.get_event_loop().call_later(
                    reset_after, self._release_lock, key
                )
            else:
                lock.release()

    def _release_lock(self, key: str) -> None:
        lock = self._locks.get(key)
        if lock and lock.locked():
            lock.release()

    async def handle_429(self, retry_after: float, *, is_global: bool = False) -> None:
        """Sleep when a 429 is received."""
        if is_global:
            self._global_event.clear()
            logger.warning("Global 429 — sleeping %.2fs", retry_after)
            await asyncio.sleep(retry_after)
            self._global_event.set()
        else:
            logger.warning("Route 429 — sleeping %.2fs", retry_after)
            await asyncio.sleep(retry_after)
