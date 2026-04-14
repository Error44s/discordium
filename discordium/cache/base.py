"""Pluggable cache layer for discordium.

Two built-in policies:
  - ``NoCache``  - pass-through, stores nothing (lowest memory)
  - ``TTLCache`` - time-based eviction with O(1) get/set

Custom policies just need to implement the ``CachePolicy`` protocol.
"""

from __future__ import annotations

import time
from collections import OrderedDict
from typing import Any, Protocol, TypeVar, runtime_checkable

K = TypeVar("K")
V = TypeVar("V")


@runtime_checkable
class CachePolicy(Protocol[K, V]):
    """Interface that all cache backends must satisfy."""

    def get(self, key: K) -> V | None: ...
    def set(self, key: K, value: V) -> None: ...
    def delete(self, key: K) -> bool: ...
    def clear(self) -> None: ...
    def __len__(self) -> int: ...
    def __contains__(self, key: K) -> bool: ...


class NoCache:
    """Null-object cache - stores nothing, always misses."""

    def get(self, key: Any) -> None:
        return None

    def set(self, key: Any, value: Any) -> None:
        pass

    def delete(self, key: Any) -> bool:
        return False

    def clear(self) -> None:
        pass

    def __len__(self) -> int:
        return 0

    def __contains__(self, key: Any) -> bool:
        return False


class TTLCache:
    """In-memory cache with per-entry TTL and optional max-size eviction.

    Parameters
    ----------
    ttl:
        Default time-to-live in seconds for each entry.
    max_size:
        Maximum number of entries; oldest are evicted first (LRU-ish).
    """

    __slots__ = ("_ttl", "_max_size", "_store")

    def __init__(self, ttl: float = 300.0, max_size: int = 10_000) -> None:
        self._ttl = ttl
        self._max_size = max_size
        # OrderedDict keeps insertion order for cheap LRU eviction
        self._store: OrderedDict[Any, tuple[float, Any]] = OrderedDict()

    def get(self, key: Any) -> Any | None:
        entry = self._store.get(key)
        if entry is None:
            return None
        expires, value = entry
        if time.monotonic() > expires:
            del self._store[key]
            return None
        # Move to end (most recently used)
        self._store.move_to_end(key)
        return value

    def set(self, key: Any, value: Any, *, ttl: float | None = None) -> None:
        self._store[key] = (time.monotonic() + (ttl or self._ttl), value)
        self._store.move_to_end(key)
        # Evict oldest if over capacity
        while len(self._store) > self._max_size:
            self._store.popitem(last=False)

    def delete(self, key: Any) -> bool:
        try:
            del self._store[key]
            return True
        except KeyError:
            return False

    def clear(self) -> None:
        self._store.clear()

    def __len__(self) -> int:
        return len(self._store)

    def __contains__(self, key: Any) -> bool:
        entry = self._store.get(key)
        if entry is None:
            return False
        if time.monotonic() > entry[0]:
            del self._store[key]
            return False
        return True
