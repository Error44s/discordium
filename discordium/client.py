"""High-level bot client — the main entry point for discordium.

Architecture::

    Gateway (WebSocket) → EventDispatcher (parse + hooks) → EventEmitter (user handlers)

The client does NOT monkeypatch the EventEmitter. Instead, a dedicated
``EventDispatcher`` sits between the gateway and the emitter, handling:
  - raw dict → typed GatewayEvent conversion
  - internal state updates (guild cache, etc.)
  - before/after middleware hooks
  - error routing

Usage::

    import discordium
    from discordium.models.events import MessageCreateEvent, ReadyEvent

    bot = discordium.GatewayClient(
        token="YOUR_TOKEN",
        intents=discordium.Intents.default() | discordium.Intents.MESSAGE_CONTENT,
    )

    @bot.on_event("message_create")
    async def on_message(event: MessageCreateEvent) -> None:
        if event.message.content == "!ping":
            await event.message.reply("Pong!")

    bot.run()
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Callable, Coroutine
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

from .cache.base import CachePolicy, NoCache, TTLCache
from .errors import AlreadyConnected, NotReady
from .gateway.connection import GatewayConnection
from .http.rest import RESTClient
from .models.channel import Channel
from .models.events import (
    GatewayEvent,
    GuildCreateEvent,
    GuildDeleteEvent,
    GuildUpdateEvent,
    ReadyEvent,
)
from .models.guild import Guild
from .models.intents import Intents
from .models.member import Member
from .models.role import Role
from .models.snowflake import Snowflake
from .models.user import User
from .utils.dispatcher import EventDispatcher, ErrorHandler, MiddlewareHook
from .utils.event import EventEmitter, Handler

logger = logging.getLogger("discordium")


# Protocol for syncable routers


@runtime_checkable
class SyncableRouter(Protocol):
    """Protocol that any router must implement to be syncable."""

    async def sync(
        self,
        client: GatewayClient,
        *,
        guild_id: int | None = None,
    ) -> list[dict[str, Any]]: ...


class GatewayClient:
    """Full-featured Discord bot client.

    Ties together the REST client, gateway, typed event dispatcher,
    and cache into a single ergonomic interface.

    Parameters
    ----------
    token:
        Bot token.
    intents:
        Gateway intents (use ``Intents.default()`` for non-privileged).
    cache:
        Cache backend; defaults to ``TTLCache()``. Pass ``NoCache()`` to disable.
    shard:
        Optional ``(shard_id, num_shards)`` for manual sharding.
    """

    __slots__ = (
        "_token",
        "_intents",
        "_emitter",
        "_dispatcher",
        "_rest",
        "_gateway",
        "_cache",
        "_shard",
        "_user",
        "_application_id",
        "_session_id",
        "_is_ready",
        "_is_closed",
        "_internals_registered",
        "_guilds",
        "_latency",
        "_guild_count",
        "_start_time",
    )

    def __init__(
        self,
        token: str,
        *,
        intents: Intents = Intents.default(),
        cache: CachePolicy[Any, Any] | None = None,
        shard: tuple[int, int] | None = None,
    ) -> None:
        self._token = token
        self._intents = intents
        self._emitter = EventEmitter()
        self._rest = RESTClient(token)
        self._dispatcher = EventDispatcher(self._emitter, self._rest)
        self._cache: CachePolicy[Any, Any] = cache or TTLCache()
        self._shard = shard
        self._gateway: GatewayConnection | None = None

        # State
        self._user: User | None = None
        self._application_id: Snowflake | None = None
        self._session_id: str | None = None
        self._is_ready = False
        self._is_closed = False
        self._internals_registered = False
        self._guilds: dict[int, Guild] = {}
        self._latency: float | None = None
        self._guild_count = 0
        self._start_time: float | None = None

    #  Properties

    @property
    def rest(self) -> RESTClient:
        """The underlying REST client for direct API access."""
        return self._rest

    @property
    def user(self) -> User | None:
        """The bot's own user, available after READY."""
        return self._user

    @property
    def application_id(self) -> Snowflake | None:
        """The bot's application ID, available after READY."""
        return self._application_id

    @property
    def cache(self) -> CachePolicy[Any, Any]:
        """The active cache backend."""
        return self._cache

    @property
    def latency(self) -> float | None:
        """Gateway heartbeat latency in seconds, or None if not yet measured."""
        if self._gateway:
            return self._gateway.latency
        return None

    @property
    def is_ready(self) -> bool:
        """Whether the client has received the READY event."""
        return self._is_ready

    @property
    def is_closed(self) -> bool:
        """Whether the client has been closed."""
        return self._is_closed

    @property
    def guild_count(self) -> int:
        """Number of guilds the bot is in."""
        return self._guild_count or len(self._guilds)

    @property
    def uptime(self) -> float | None:
        """Seconds since the bot started, or None if not started."""
        if self._start_time is None:
            return None
        return time.monotonic() - self._start_time

    @property
    def emitter(self) -> EventEmitter:
        """Direct access to the event emitter (advanced usage)."""
        return self._emitter

    @property
    def dispatcher(self) -> EventDispatcher:
        """Direct access to the event dispatcher (advanced usage)."""
        return self._dispatcher

    #  Guild Access

    def get_guild(self, guild_id: int | Snowflake) -> Guild | None:
        """Get a cached guild by ID."""
        return self._guilds.get(int(guild_id))

    def get_all_guilds(self) -> list[Guild]:
        """Get all cached guilds as a list."""
        return list(self._guilds.values())

    async def fetch_guild(self, guild_id: int | Snowflake) -> Guild:
        """Fetch a guild from the API (bypasses cache)."""
        return await self._rest.get_guild(Snowflake(int(guild_id)))

    async def fetch_channel(self, channel_id: int | Snowflake) -> Channel:
        """Fetch a channel from the API."""
        return await self._rest.get_channel(Snowflake(int(channel_id)))

    async def fetch_user(self, user_id: int | Snowflake) -> User:
        """Fetch a user from the API."""
        return await self._rest.get_user(Snowflake(int(user_id)))

    async def fetch_member(
        self, guild_id: int | Snowflake, user_id: int | Snowflake
    ) -> Member:
        """Fetch a guild member from the API."""
        return await self._rest.get_member(
            Snowflake(int(guild_id)), Snowflake(int(user_id))
        )

    async def fetch_roles(self, guild_id: int | Snowflake) -> list[Role]:
        """Fetch all roles for a guild."""
        return await self._rest.get_roles(Snowflake(int(guild_id)))

    #  Event Registration

    def on_event(self, event: str) -> Callable[[Handler], Handler]:
        """Register a typed event handler::

            @bot.on_event("message_create")
            async def on_msg(event: MessageCreateEvent) -> None:
                print(event.message.content)
        """

        def decorator(func: Handler) -> Handler:
            self._emitter.on(event, func)
            return func

        return decorator

    def once_event(self, event: str) -> Callable[[Handler], Handler]:
        """Register a one-shot typed event handler."""

        def decorator(func: Handler) -> Handler:
            self._emitter.on_once(event, func)
            return func

        return decorator

    async def wait_for(
        self,
        event: str,
        *,
        check: Callable[..., bool] | None = None,
        timeout: float | None = None,
    ) -> GatewayEvent:
        """Block until a specific event fires.

        Parameters
        ----------
        event:
            Event name (e.g. ``"message_create"``).
        check:
            Optional predicate receiving the typed event object.
        timeout:
            Seconds to wait before raising ``asyncio.TimeoutError``.
        """
        return await self._emitter.wait_for(event, check=check, timeout=timeout)

    #  Error Handlers & Middleware

    def on_error(self, handler: ErrorHandler) -> ErrorHandler:
        """Register a global error handler::

            @bot.on_error
            async def handle_error(event_name: str, error: Exception) -> None:
                print(f"Error in {event_name}: {error}")
        """
        self._dispatcher.add_error_handler(handler)
        return handler

    def before_event(self, hook: MiddlewareHook) -> MiddlewareHook:
        """Register a before-event middleware. Return ``False`` to cancel::

            @bot.before_event
            async def log_events(name: str, event: GatewayEvent) -> None:
                logger.debug("Event: %s", name)
        """
        self._dispatcher.add_before_hook(hook)
        return hook

    def after_event(self, hook: MiddlewareHook) -> MiddlewareHook:
        """Register an after-event middleware::

            @bot.after_event
            async def track(name: str, event: GatewayEvent) -> None:
                metrics.inc(name)
        """
        self._dispatcher.add_after_hook(hook)
        return hook

    #  Presence

    async def set_presence(
        self,
        *,
        status: str = "online",
        activity_name: str | None = None,
        activity_type: int = 0,
        afk: bool = False,
    ) -> None:
        """Update the bot's presence/status."""
        if self._gateway:
            await self._gateway.update_presence(
                status=status,
                activity_name=activity_name,
                activity_type=activity_type,
                afk=afk,
            )

    #  Lifecycle

    async def start(self) -> None:
        """Connect to the gateway and begin processing events.

        Raises
        ------
        AlreadyConnected:
            If the client is already connected.
        """
        if self._gateway and not self._is_closed:
            raise AlreadyConnected("Client is already connected")

        self._is_closed = False
        self._start_time = time.monotonic()

        # Register internal handlers exactly once
        self._register_internals()

        # Fetch gateway URL
        gateway_data = await self._rest.get_gateway_bot()
        gateway_url = gateway_data["url"]

        logger.info(
            "Gateway: url=%s, recommended_shards=%d",
            gateway_url,
            gateway_data.get("shards", 1),
        )

        # The gateway emits raw events to our dispatcher (not the emitter)
        self._gateway = GatewayConnection(
            self._token,
            int(self._intents),
            self._dispatcher,  # dispatcher has same .emit() signature
            gateway_url,
            shard=self._shard,
        )

        logger.info("Starting discordium bot...")
        await self._gateway.connect()

    async def close(self) -> None:
        """Shut down the bot gracefully."""
        if self._is_closed:
            return

        self._is_closed = True
        self._is_ready = False
        logger.info("Shutting down...")

        if self._gateway:
            await self._gateway.close()
        await self._rest.close()

    def run(self) -> None:
        """Blocking entry point — runs the bot until interrupted::

            bot = GatewayClient(token="...")
            bot.run()
        """

        async def _runner() -> None:
            try:
                await self.start()
            except KeyboardInterrupt:
                pass
            finally:
                await self.close()

        try:
            asyncio.run(_runner())
        except KeyboardInterrupt:
            pass

    #  Sync Helpers

    async def sync_commands(
        self,
        router: SyncableRouter,
        *,
        guild_id: int | None = None,
    ) -> list[dict[str, Any]]:
        """Sync slash commands safely.

        Parameters
        ----------
        router:
            A ``SlashRouter`` (or any ``SyncableRouter``).
        guild_id:
            If set, sync to a specific guild (instant).
            If None, sync globally (up to 1hr propagation).

        Raises
        ------
        NotReady:
            If called before the bot has received READY.
        """
        if not self._is_ready:
            raise NotReady("Cannot sync commands before the bot is ready")
        return await router.sync(self, guild_id=guild_id)

    #  Internal State Handlers (registered once)

    def _register_internals(self) -> None:
        """Register internal event handlers exactly once."""
        if self._internals_registered:
            return
        self._internals_registered = True

        self._dispatcher.add_internal_handler("ready", self._on_ready)
        self._dispatcher.add_internal_handler("guild_create", self._on_guild_create)
        self._dispatcher.add_internal_handler("guild_update", self._on_guild_update)
        self._dispatcher.add_internal_handler("guild_delete", self._on_guild_delete)

    async def _on_ready(self, event: GatewayEvent) -> None:
        if not isinstance(event, ReadyEvent):
            return
        self._user = event.user
        self._session_id = event.session_id
        self._application_id = event.application_id
        self._is_ready = True
        self._guild_count = len(event.guilds)

        logger.info(
            "Logged in as %s (ID: %s) — %d guild(s)",
            self._user.display_name,
            self._user.id,
            len(event.guilds),
        )

    async def _on_guild_create(self, event: GatewayEvent) -> None:
        if not isinstance(event, GuildCreateEvent):
            return
        guild = event.guild
        self._guilds[int(guild.id)] = guild

        # Cache members, channels, roles
        for member in event.members:
            if member.id:
                self._cache.set(f"member:{guild.id}:{member.id}", member)
        for channel in event.channels:
            self._cache.set(f"channel:{channel.id}", channel)
        for role in event.roles:
            self._cache.set(f"role:{guild.id}:{role.id}", role)

    async def _on_guild_update(self, event: GatewayEvent) -> None:
        if not isinstance(event, GuildUpdateEvent):
            return
        self._guilds[int(event.guild.id)] = event.guild

    async def _on_guild_delete(self, event: GatewayEvent) -> None:
        if not isinstance(event, GuildDeleteEvent):
            return
        self._guilds.pop(int(event.guild_id), None)
