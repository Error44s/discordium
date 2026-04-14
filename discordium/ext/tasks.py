"""Recurring task loops — a clean replacement for discord.ext.tasks.

Usage::

    from discordium.ext.tasks import loop

    @loop(seconds=60)
    async def status_update():
        print("Running every 60 seconds!")

    # Start it when the bot is ready:
    @bot.on_event("ready")
    async def on_ready(data):
        status_update.start()
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable, Coroutine
from typing import Any

logger = logging.getLogger("discordium.tasks")


class Loop:
    """A managed recurring async task.

    Not instantiated directly — use the ``@loop()`` decorator.
    """

    __slots__ = (
        "_coro",
        "_seconds",
        "_minutes",
        "_hours",
        "_count",
        "_task",
        "_current_loop",
        "_is_running",
        "_before_loop",
        "_after_loop",
        "_on_error",
    )

    def __init__(
        self,
        coro: Callable[..., Coroutine[Any, Any, Any]],
        *,
        seconds: float = 0,
        minutes: float = 0,
        hours: float = 0,
        count: int | None = None,
    ) -> None:
        self._coro = coro
        self._seconds = seconds + (minutes * 60) + (hours * 3600)
        self._count = count
        self._task: asyncio.Task[None] | None = None
        self._current_loop = 0
        self._is_running = False
        self._before_loop: Callable[..., Coroutine[Any, Any, Any]] | None = None
        self._after_loop: Callable[..., Coroutine[Any, Any, Any]] | None = None
        self._on_error: Callable[[Exception], Coroutine[Any, Any, Any]] | None = None

        if self._seconds <= 0:
            raise ValueError("Loop interval must be positive")

    @property
    def is_running(self) -> bool:
        return self._is_running

    @property
    def current_loop(self) -> int:
        return self._current_loop

    def start(self, *args: Any, **kwargs: Any) -> asyncio.Task[None]:
        """Start the loop. Returns the underlying ``asyncio.Task``.

        Safe to call multiple times — if already running, returns the
        existing task without starting a second one. This prevents
        issues with multiple READY events during reconnects.
        """
        if self._is_running and self._task and not self._task.done():
            logger.debug("Loop %r already running, skipping start", self._coro.__name__)
            return self._task
        self._task = asyncio.create_task(self._run(*args, **kwargs))
        self._is_running = True
        return self._task

    def stop(self) -> None:
        """Signal the loop to stop after the current iteration."""
        self._is_running = False

    def cancel(self) -> None:
        """Cancel the loop immediately."""
        self._is_running = False
        if self._task and not self._task.done():
            self._task.cancel()

    def restart(self, *args: Any, **kwargs: Any) -> asyncio.Task[None]:
        """Cancel and restart the loop."""
        self.cancel()
        self._current_loop = 0
        return self.start(*args, **kwargs)

    # Decorators for hooks

    def before(
        self, coro: Callable[..., Coroutine[Any, Any, Any]]
    ) -> Callable[..., Coroutine[Any, Any, Any]]:
        """Register a coroutine to run before the loop starts."""
        self._before_loop = coro
        return coro

    def after(
        self, coro: Callable[..., Coroutine[Any, Any, Any]]
    ) -> Callable[..., Coroutine[Any, Any, Any]]:
        """Register a coroutine to run after the loop ends."""
        self._after_loop = coro
        return coro

    def error(
        self, coro: Callable[[Exception], Coroutine[Any, Any, Any]]
    ) -> Callable[[Exception], Coroutine[Any, Any, Any]]:
        """Register an error handler."""
        self._on_error = coro
        return coro

    # Internal

    async def _run(self, *args: Any, **kwargs: Any) -> None:
        try:
            if self._before_loop:
                await self._before_loop()

            while self._is_running:
                if self._count is not None and self._current_loop >= self._count:
                    break

                try:
                    await self._coro(*args, **kwargs)
                except Exception as exc:
                    if self._on_error:
                        await self._on_error(exc)
                    else:
                        logger.exception("Error in task loop %r", self._coro.__name__)

                self._current_loop += 1
                await asyncio.sleep(self._seconds)

        finally:
            self._is_running = False
            if self._after_loop:
                await self._after_loop()


def loop(
    *,
    seconds: float = 0,
    minutes: float = 0,
    hours: float = 0,
    count: int | None = None,
) -> Callable[
    [Callable[..., Coroutine[Any, Any, Any]]],
    Loop,
]:
    """Decorator to create a recurring task loop::

        @loop(seconds=30)
        async def my_task():
            ...
    """

    def decorator(func: Callable[..., Coroutine[Any, Any, Any]]) -> Loop:
        return Loop(func, seconds=seconds, minutes=minutes, hours=hours, count=count)

    return decorator
