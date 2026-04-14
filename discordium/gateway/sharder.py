"""Automatic sharding manager for large-scale bots.

Handles multi-shard coordination, automatic shard count detection,
and per-shard lifecycle management::

    from discordium.gateway.sharder import ShardManager

    manager = ShardManager(
        token=TOKEN,
        intents=Intents.default(),
        emitter=emitter,
        rest=rest,
    )
    # Auto-detects recommended shard count from Discord
    await manager.start()

    # Or specify manually
    await manager.start(shard_count=4)
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Any

from .connection import GatewayConnection

if TYPE_CHECKING:
    from ..http.rest import RESTClient
    from ..utils.event import EventEmitter

logger = logging.getLogger("discordium.sharder")


class ShardManager:
    """Manages multiple gateway shards.

    Connects each shard sequentially (respecting Discord's 5s identify rate limit),
    monitors health, and restarts failed shards.

    Parameters
    ----------
    token:
        Bot token.
    intents:
        Gateway intents value.
    emitter:
        Shared event emitter — all shards dispatch to the same bus.
    rest:
        REST client for fetching gateway info.
    """

    __slots__ = (
        "_token", "_intents", "_emitter", "_rest",
        "_shards", "_shard_count", "_gateway_url",
        "_max_concurrency", "_closed",
    )

    def __init__(
        self,
        token: str,
        intents: int,
        emitter: EventEmitter,
        rest: RESTClient,
    ) -> None:
        self._token = token
        self._intents = intents
        self._emitter = emitter
        self._rest = rest
        self._shards: dict[int, GatewayConnection] = {}
        self._shard_count = 0
        self._gateway_url = ""
        self._max_concurrency = 1
        self._closed = False

    @property
    def shard_count(self) -> int:
        return self._shard_count

    @property
    def shards(self) -> dict[int, GatewayConnection]:
        return dict(self._shards)

    async def start(self, *, shard_count: int | None = None, shard_ids: list[int] | None = None) -> None:
        """Start all shards.

        Parameters
        ----------
        shard_count:
            Total number of shards. If None, uses Discord's recommended count.
        shard_ids:
            Specific shard IDs to launch (for distributed setups).
            If None, launches all shards 0..shard_count-1.
        """
        # Fetch gateway info
        gateway_data = await self._rest.get_gateway_bot()
        self._gateway_url = gateway_data["url"]

        if shard_count is None:
            self._shard_count = gateway_data.get("shards", 1)
        else:
            self._shard_count = shard_count

        self._max_concurrency = (
            gateway_data.get("session_start_limit", {}).get("max_concurrency", 1)
        )

        ids_to_launch = shard_ids or list(range(self._shard_count))

        logger.info(
            "Starting %d shard(s) (total: %d, concurrency: %d)",
            len(ids_to_launch), self._shard_count, self._max_concurrency,
        )

        # Launch shards in buckets of max_concurrency
        # Discord requires a 5-second gap between identifies within the same bucket
        for i in range(0, len(ids_to_launch), self._max_concurrency):
            bucket = ids_to_launch[i : i + self._max_concurrency]
            tasks = []
            for shard_id in bucket:
                conn = GatewayConnection(
                    self._token,
                    self._intents,
                    self._emitter,
                    self._gateway_url,
                    shard=(shard_id, self._shard_count),
                )
                self._shards[shard_id] = conn
                tasks.append(asyncio.create_task(
                    self._run_shard(shard_id, conn),
                    name=f"shard-{shard_id}",
                ))
                logger.info("Launching shard %d/%d", shard_id, self._shard_count)

            # Wait 5 seconds between identify buckets
            if i + self._max_concurrency < len(ids_to_launch):
                await asyncio.sleep(5)

        # Wait for all shards (they run indefinitely)
        await asyncio.gather(*tasks, return_exceptions=True)

    async def _run_shard(self, shard_id: int, conn: GatewayConnection) -> None:
        """Run a single shard with auto-restart on failure."""
        while not self._closed:
            try:
                await conn.connect()
            except Exception:
                if self._closed:
                    return
                logger.exception("Shard %d crashed, restarting in 10s", shard_id)
                await asyncio.sleep(10)

    async def close(self) -> None:
        """Gracefully shut down all shards."""
        self._closed = True
        logger.info("Shutting down %d shard(s)…", len(self._shards))
        tasks = [shard.close() for shard in self._shards.values()]
        await asyncio.gather(*tasks, return_exceptions=True)
        self._shards.clear()

    def get_shard(self, guild_id: int) -> GatewayConnection | None:
        """Get the shard responsible for a specific guild."""
        if self._shard_count == 0:
            return None
        shard_id = (guild_id >> 22) % self._shard_count
        return self._shards.get(shard_id)
