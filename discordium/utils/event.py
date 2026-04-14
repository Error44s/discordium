"""Typed event emitter with decorator registration.

Design goals:
  - Zero inheritance required — decorators do everything
  - Full asyncio — all handlers are coroutines
  - Wildcard listeners for debugging / logging
  - `once` decorator for one-shot handlers
"""

from __future__ import annotations

import asyncio
import inspect
import logging
from collections import defaultdict
from collections.abc import Callable, Coroutine
from functools import wraps
from typing import Any, ParamSpec, TypeVar

logger = logging.getLogger("discordium.events")

P = ParamSpec("P")
T = TypeVar("T")

Handler = Callable[..., Coroutine[Any, Any, Any]]

_ATTR_EVENT = "__discordium_event__"
_ATTR_ONCE = "__discordium_once__"

# Decorators

def listener(event: str | None = None) -> Callable[[Handler], Handler]:
    """Mark an async function as an event listener.

    If *event* is ``None``, the function name (minus a leading ``on_``) is used::

        @listener()
        async def on_message(msg: Message) -> None: ...

        @listener("message_create")
        async def handle_msg(msg: Message) -> None: ...
    """

    def decorator(func: Handler) -> Handler:
        if not inspect.iscoroutinefunction(func):
            raise TypeError(f"Listener {func.__name__!r} must be an async function")
        name = event or func.__name__.removeprefix("on_")
        setattr(func, _ATTR_EVENT, name)
        setattr(func, _ATTR_ONCE, False)
        return func

    return decorator


def once(event: str | None = None) -> Callable[[Handler], Handler]:
    """Like ``@listener`` but the handler fires only once then auto-removes."""

    def decorator(func: Handler) -> Handler:
        if not inspect.iscoroutinefunction(func):
            raise TypeError(f"Once-listener {func.__name__!r} must be an async function")
        name = event or func.__name__.removeprefix("on_")
        setattr(func, _ATTR_EVENT, name)
        setattr(func, _ATTR_ONCE, True)
        return func

    return decorator

# Emitter

class EventEmitter:
    """Core event bus.

    Can be used standalone or mixed into a client class.
    """

    def __init__(self) -> None:
        self._listeners: dict[str, list[Handler]] = defaultdict(list)
        self._once_listeners: dict[str, list[Handler]] = defaultdict(list)
        self._wildcards: list[Handler] = []

    # Registration

    def on(self, event: str, handler: Handler) -> None:
        """Register a permanent listener for *event*."""
        self._listeners[event].append(handler)

    def on_once(self, event: str, handler: Handler) -> None:
        """Register a one-shot listener for *event*."""
        self._once_listeners[event].append(handler)

    def on_any(self, handler: Handler) -> None:
        """Register a wildcard listener that receives **every** event."""
        self._wildcards.append(handler)

    def remove(self, event: str, handler: Handler) -> None:
        """Remove a specific handler from *event*."""
        try:
            self._listeners[event].remove(handler)
        except ValueError:
            pass
        try:
            self._once_listeners[event].remove(handler)
        except ValueError:
            pass

    def collect_listeners(self, obj: object) -> None:
        """Scan *obj* for methods decorated with ``@listener`` / ``@once``."""
        for name in dir(obj):
            method = getattr(obj, name, None)
            if method is None:
                continue
            event_name = getattr(method, _ATTR_EVENT, None)
            if event_name is None:
                continue
            if getattr(method, _ATTR_ONCE, False):
                self.on_once(event_name, method)
            else:
                self.on(event_name, method)

    # Dispatch

    async def emit(self, event: str, *args: Any, **kwargs: Any) -> None:
        """Fire all listeners for *event* concurrently. Errors are logged."""
        handlers: list[Handler] = list(self._listeners.get(event, []))

        # Pop once-listeners
        once = self._once_listeners.pop(event, [])
        handlers.extend(once)

        # Wildcards receive (event_name, *args)
        for wc in self._wildcards:
            handlers.append(lambda *a, _wc=wc, _ev=event, **kw: _wc(_ev, *a, **kw))

        if not handlers:
            return

        tasks = [asyncio.create_task(h(*args, **kwargs)) for h in handlers]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        for result in results:
            if isinstance(result, BaseException):
                logger.error("Error in %s handler: %s", event, result, exc_info=result)

    async def emit_raising(self, event: str, *args: Any, **kwargs: Any) -> None:
        """Like ``emit``, but re-raises the first error instead of logging.

        Used by the ``EventDispatcher`` so errors reach the error handler chain.
        """
        handlers: list[Handler] = list(self._listeners.get(event, []))

        once = self._once_listeners.pop(event, [])
        handlers.extend(once)

        for wc in self._wildcards:
            handlers.append(lambda *a, _wc=wc, _ev=event, **kw: _wc(_ev, *a, **kw))

        if not handlers:
            return

        tasks = [asyncio.create_task(h(*args, **kwargs)) for h in handlers]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        for result in results:
            if isinstance(result, BaseException):
                raise result

    async def wait_for(
        self,
        event: str,
        *,
        check: Callable[..., bool] | None = None,
        timeout: float | None = None,
    ) -> Any:
        """Block until *event* fires (optionally matching *check*), with timeout.

        Returns the event payload. Raises ``asyncio.TimeoutError`` on timeout.
        """
        future: asyncio.Future[Any] = asyncio.get_running_loop().create_future()

        async def _waiter(*args: Any) -> None:
            if check is not None and not check(*args):
                # Re-register — we haven't matched yet
                self.on_once(event, _waiter)
                return
            payload = args[0] if len(args) == 1 else args
            if not future.done():
                future.set_result(payload)

        self.on_once(event, _waiter)
        return await asyncio.wait_for(future, timeout=timeout)
