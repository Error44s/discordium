"""Exponential backoff with jitter for reconnection logic."""

from __future__ import annotations

import random


class ExponentialBackoff:
    """Compute exponential backoff delays with full jitter.

    Usage::

        backoff = ExponentialBackoff()
        delay = backoff.compute()   # 1-2s
        delay = backoff.compute()   # 2-4s
        delay = backoff.compute()   # 4-8s
        backoff.reset()             # back to base
    """

    __slots__ = ("_base", "_max", "_attempt", "_jitter")

    def __init__(
        self,
        base: float = 1.0,
        maximum: float = 60.0,
        jitter: bool = True,
    ) -> None:
        self._base = base
        self._max = maximum
        self._attempt = 0
        self._jitter = jitter

    def compute(self) -> float:
        """Return the next backoff delay in seconds."""
        delay = min(self._base * (2**self._attempt), self._max)
        if self._jitter:
            delay = random.uniform(0, delay)  # noqa: S311
        self._attempt += 1
        return delay

    def reset(self) -> None:
        """Reset the attempt counter."""
        self._attempt = 0
