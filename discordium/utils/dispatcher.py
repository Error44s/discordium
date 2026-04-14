"""Typed event dispatcher — bridges raw gateway payloads and typed event objects.

This replaces the runtime monkeypatch of ``EventEmitter.emit``. Instead, the
``GatewayConnection`` emits raw events to the ``EventDispatcher``, which
converts them into typed ``GatewayEvent`` objects and then dispatches
to user handlers through the ``EventEmitter``.

Architecture::

    Gateway (raw dict) → EventDispatcher (parse + hooks) → EventEmitter (user handlers)

The dispatcher also handles:
  - before/after middleware hooks
  - error routing to registered error handlers
  - internal client state updates (ready, guild cache, etc.)
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable, Coroutine
from typing import TYPE_CHECKING, Any

from ..models.events import GatewayEvent, parse_event

if TYPE_CHECKING:
    from ..http.rest import RESTClient
    from .event import EventEmitter

logger = logging.getLogger("discordium.dispatch")

ErrorHandler = Callable[[str, Exception], Coroutine[Any, Any, None]]
MiddlewareHook = Callable[[str, GatewayEvent], Coroutine[Any, Any, bool | None]]
InternalHandler = Callable[[GatewayEvent], Coroutine[Any, Any, None]]


class EventDispatcher:
    """Converts raw gateway payloads into typed events and dispatches them.

    Sits between the gateway connection (which emits raw dicts) and the
    user-facing EventEmitter (which delivers typed event objects).

    This is a first-class architectural component, not a monkey-patch.
    """

    __slots__ = (
        "_emitter",
        "_rest",
        "_error_handlers",
        "_before_hooks",
        "_after_hooks",
        "_internal_handlers",
    )

    def __init__(self, emitter: EventEmitter, rest: RESTClient) -> None:
        self._emitter = emitter
        self._rest = rest
        self._error_handlers: list[ErrorHandler] = []
        self._before_hooks: list[MiddlewareHook] = []
        self._after_hooks: list[MiddlewareHook] = []
        self._internal_handlers: dict[str, list[InternalHandler]] = {}

    # Registration

    def add_error_handler(self, handler: ErrorHandler) -> None:
        self._error_handlers.append(handler)

    def add_before_hook(self, hook: MiddlewareHook) -> None:
        self._before_hooks.append(hook)

    def add_after_hook(self, hook: MiddlewareHook) -> None:
        self._after_hooks.append(hook)

    def add_internal_handler(self, event_name: str, handler: InternalHandler) -> None:
        """Register an internal handler that runs before user handlers.

        Used by the client to update its own state (guild cache, etc.)
        without polluting the user-facing event system.
        """
        if event_name not in self._internal_handlers:
            self._internal_handlers[event_name] = []
        self._internal_handlers[event_name].append(handler)

    # Dispatch (called by gateway)

    async def emit(self, event_name: str, *args: Any, **kwargs: Any) -> None:
        """Gateway-compatible entry point.

        The ``GatewayConnection`` calls ``emitter.emit(event_name, raw_data)``.
        By swapping in the dispatcher, raw dicts are automatically parsed
        into typed events without any monkeypatching.
        """
        if args and isinstance(args[0], dict):
            await self.dispatch(event_name, args[0])
        else:
            # Already typed or other args — pass through
            await self._emitter.emit(event_name, *args, **kwargs)

    async def dispatch(self, event_name: str, raw_data: dict[str, Any]) -> None:
        """Parse a raw gateway payload and dispatch to all handlers.

        This is the single entry point from the gateway connection.

        Flow:
          1. Parse raw dict → typed GatewayEvent
          2. Run internal handlers (client state updates)
          3. Run before-hooks (can cancel dispatch)
          4. Run user handlers via EventEmitter
          5. Run after-hooks
        """
        # 1. Parse
        typed_event = parse_event(event_name, raw_data, rest=self._rest)

        # 2. Internal handlers (client state — always run, errors logged)
        internal = self._internal_handlers.get(event_name, [])
        for handler in internal:
            try:
                await handler(typed_event)
            except Exception as exc:
                logger.error(
                    "Error in internal %s handler: %s", event_name, exc, exc_info=exc
                )

        # 3. Before hooks (can cancel)
        for hook in self._before_hooks:
            try:
                result = await hook(event_name, typed_event)
                if result is False:
                    return  # cancelled
            except Exception as exc:
                logger.error("Error in before_event hook: %s", exc, exc_info=exc)

        # 4. User handlers (use emit_raising so errors propagate to our handler)
        try:
            await self._emitter.emit_raising(event_name, typed_event)
        except Exception as exc:
            await self._handle_error(event_name, exc)

        # 5. After hooks
        for hook in self._after_hooks:
            try:
                await hook(event_name, typed_event)
            except Exception as exc:
                logger.error("Error in after_event hook: %s", exc, exc_info=exc)

    async def dispatch_typed(self, event_name: str, event: GatewayEvent) -> None:
        """Dispatch an already-typed event (for internal use)."""
        await self._emitter.emit(event_name, event)

    # Error routing

    async def _handle_error(self, event_name: str, error: Exception) -> None:
        if self._error_handlers:
            for handler in self._error_handlers:
                try:
                    await handler(event_name, error)
                except Exception:
                    logger.exception("Error in error handler")
        else:
            logger.error(
                "Unhandled error in %s: %s", event_name, error, exc_info=error
            )
