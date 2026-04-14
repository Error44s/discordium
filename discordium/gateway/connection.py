"""Discord Gateway (WebSocket) handler.

Manages the full gateway lifecycle:
  - Connect → Identify → Heartbeat loop
  - Auto-resume on disconnect
  - Reconnect with exponential backoff
  - Dispatch raw events to the event emitter
"""

from __future__ import annotations

import asyncio
import logging
import platform
import sys
import time
import zlib
from enum import IntEnum
from typing import TYPE_CHECKING, Any

import aiohttp
import orjson

from ..utils.backoff import ExponentialBackoff

if TYPE_CHECKING:
    from collections.abc import Callable, Coroutine

    # The gateway accepts anything with an async emit(name, data) method.
    # In practice this is either EventEmitter or EventDispatcher.
    from typing import Protocol

    class _Emitter(Protocol):
        async def emit(self, event: str, *args: Any, **kwargs: Any) -> None: ...

logger = logging.getLogger("discordium.gateway")

GATEWAY_VERSION = 10
ZLIB_SUFFIX = b"\x00\x00\xff\xff"


class GatewayOp(IntEnum):
    DISPATCH = 0
    HEARTBEAT = 1
    IDENTIFY = 2
    PRESENCE_UPDATE = 3
    VOICE_STATE_UPDATE = 4
    RESUME = 6
    RECONNECT = 7
    REQUEST_GUILD_MEMBERS = 8
    INVALID_SESSION = 9
    HELLO = 10
    HEARTBEAT_ACK = 11


class GatewayConnection:
    """Manages a single WebSocket connection to the Discord gateway.

    Parameters
    ----------
    token:
        Bot token.
    intents:
        Bitfield of gateway intents.
    emitter:
        Event emitter for dispatching parsed events.
    gateway_url:
        WebSocket URL (fetched from REST if not provided).
    shard:
        (shard_id, num_shards) tuple, or None for no sharding.
    """

    __slots__ = (
        "_token",
        "_intents",
        "_emitter",
        "_gateway_url",
        "_shard",
        "_ws",
        "_session",
        "_session_id",
        "_seq",
        "_resume_url",
        "_heartbeat_interval",
        "_heartbeat_task",
        "_ack_received",
        "_inflator",
        "_backoff",
        "_closed",
        "_latency",
        "_heartbeat_sent_at",
    )

    def __init__(
        self,
        token: str,
        intents: int,
        emitter: _Emitter,
        gateway_url: str,
        *,
        shard: tuple[int, int] | None = None,
    ) -> None:
        self._token = token
        self._intents = intents
        self._emitter = emitter
        self._gateway_url = gateway_url
        self._shard = shard

        self._ws: aiohttp.ClientWebSocketResponse | None = None
        self._session: aiohttp.ClientSession | None = None
        self._session_id: str | None = None
        self._seq: int | None = None
        self._resume_url: str | None = None
        self._heartbeat_interval: float = 41.25
        self._heartbeat_task: asyncio.Task[None] | None = None
        self._ack_received = True
        self._inflator = zlib.decompressobj()
        self._backoff = ExponentialBackoff()
        self._closed = False
        self._latency: float | None = None
        self._heartbeat_sent_at: float | None = None

    @property
    def latency(self) -> float | None:
        """Heartbeat round-trip latency in seconds."""
        return self._latency

    # Public API

    async def connect(self) -> None:
        """Connect to the gateway and begin the read loop."""
        while not self._closed:
            try:
                await self._do_connect()
                await self._read_loop()
            except (
                aiohttp.WSServerHandshakeError,
                aiohttp.ClientConnectionError,
                ConnectionResetError,
                asyncio.TimeoutError,
            ) as exc:
                if self._closed:
                    return
                delay = self._backoff.compute()
                logger.warning("Gateway disconnected (%s), reconnecting in %.1fs", exc, delay)
                await asyncio.sleep(delay)
            except Exception:
                if self._closed:
                    return
                logger.exception("Unexpected gateway error")
                delay = self._backoff.compute()
                await asyncio.sleep(delay)
            finally:
                self._stop_heartbeat()

    async def close(self) -> None:
        """Cleanly close the gateway connection."""
        self._closed = True
        self._stop_heartbeat()
        if self._ws and not self._ws.closed:
            await self._ws.close(code=1000)
        if self._session and not self._session.closed:
            await self._session.close()

    # Connection

    async def _do_connect(self) -> None:
        url = self._resume_url or self._gateway_url
        url = f"{url}?v={GATEWAY_VERSION}&encoding=json&compress=zlib-stream"

        self._inflator = zlib.decompressobj()
        self._session = aiohttp.ClientSession()
        self._ws = await self._session.ws_connect(url, max_msg_size=0)
        logger.info("Connected to gateway: %s", url)

    # Read loop

    async def _read_loop(self) -> None:
        assert self._ws is not None
        buffer = bytearray()

        async for msg in self._ws:
            if msg.type == aiohttp.WSMsgType.BINARY:
                buffer.extend(msg.data)
                if len(msg.data) >= 4 and msg.data[-4:] == ZLIB_SUFFIX:
                    try:
                        raw = self._inflator.decompress(buffer)
                    except zlib.error:
                        buffer.clear()
                        continue
                    buffer.clear()
                    payload = orjson.loads(raw)
                    await self._handle_payload(payload)

            elif msg.type == aiohttp.WSMsgType.TEXT:
                payload = orjson.loads(msg.data)
                await self._handle_payload(payload)

            elif msg.type in (aiohttp.WSMsgType.CLOSE, aiohttp.WSMsgType.CLOSING, aiohttp.WSMsgType.CLOSED):
                logger.info("WebSocket closed with code %s", msg.data)
                break

            elif msg.type == aiohttp.WSMsgType.ERROR:
                logger.error("WebSocket error: %s", self._ws.exception())
                break

    # Payload dispatch

    async def _handle_payload(self, data: dict[str, Any]) -> None:
        op = data["op"]
        seq = data.get("s")
        event_name = data.get("t")
        payload = data.get("d")

        if seq is not None:
            self._seq = seq

        match op:
            case GatewayOp.HELLO:
                self._heartbeat_interval = payload["heartbeat_interval"] / 1000
                self._start_heartbeat()
                if self._session_id and self._seq:
                    await self._resume()
                else:
                    await self._identify()

            case GatewayOp.HEARTBEAT_ACK:
                self._ack_received = True
                if self._heartbeat_sent_at is not None:
                    self._latency = time.monotonic() - self._heartbeat_sent_at

            case GatewayOp.HEARTBEAT:
                await self._send_heartbeat()

            case GatewayOp.DISPATCH:
                self._backoff.reset()
                await self._handle_dispatch(event_name, payload)

            case GatewayOp.RECONNECT:
                logger.info("Server requested reconnect")
                if self._ws:
                    await self._ws.close(code=4000)

            case GatewayOp.INVALID_SESSION:
                resumable = payload if isinstance(payload, bool) else False
                if not resumable:
                    self._session_id = None
                    self._seq = None
                    self._resume_url = None
                await asyncio.sleep(1 + 4 * (not resumable))
                if self._ws:
                    await self._ws.close(code=4000)

    async def _handle_dispatch(self, event: str | None, data: Any) -> None:
        if event is None:
            return

        if event == "READY":
            self._session_id = data.get("session_id")
            self._resume_url = data.get("resume_gateway_url")
            logger.info("Gateway READY — session %s", self._session_id)

        # Emit the raw event as a lowercase name
        # e.g. MESSAGE_CREATE → message_create
        await self._emitter.emit(event.lower(), data)

    # Identify / Resume

    async def _identify(self) -> None:
        payload: dict[str, Any] = {
            "op": GatewayOp.IDENTIFY,
            "d": {
                "token": self._token,
                "intents": self._intents,
                "properties": {
                    "os": platform.system().lower(),
                    "browser": "discordium",
                    "device": "discordium",
                },
                "compress": True,
                "large_threshold": 250,
            },
        }
        if self._shard:
            payload["d"]["shard"] = list(self._shard)
        await self._send(payload)
        logger.info("Sent IDENTIFY")

    async def _resume(self) -> None:
        payload = {
            "op": GatewayOp.RESUME,
            "d": {
                "token": self._token,
                "session_id": self._session_id,
                "seq": self._seq,
            },
        }
        await self._send(payload)
        logger.info("Sent RESUME (session=%s, seq=%s)", self._session_id, self._seq)

    # Heartbeat

    def _start_heartbeat(self) -> None:
        self._stop_heartbeat()
        self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())

    def _stop_heartbeat(self) -> None:
        if self._heartbeat_task and not self._heartbeat_task.done():
            self._heartbeat_task.cancel()
            self._heartbeat_task = None

    async def _heartbeat_loop(self) -> None:
        # Initial jitter
        await asyncio.sleep(self._heartbeat_interval * 0.5)
        while True:
            if not self._ack_received:
                logger.warning("No heartbeat ACK — zombie connection, reconnecting")
                if self._ws:
                    await self._ws.close(code=4000)
                return
            self._ack_received = False
            await self._send_heartbeat()
            await asyncio.sleep(self._heartbeat_interval)

    async def _send_heartbeat(self) -> None:
        self._heartbeat_sent_at = time.monotonic()
        await self._send({"op": GatewayOp.HEARTBEAT, "d": self._seq})

    # Send

    async def _send(self, data: dict[str, Any]) -> None:
        if self._ws and not self._ws.closed:
            await self._ws.send_bytes(orjson.dumps(data))

    # Presence

    async def update_presence(
        self,
        *,
        status: str = "online",
        activity_name: str | None = None,
        activity_type: int = 0,
        afk: bool = False,
    ) -> None:
        """Update the bot's presence / status."""
        activity = None
        if activity_name:
            activity = {"name": activity_name, "type": activity_type}
        payload = {
            "op": GatewayOp.PRESENCE_UPDATE,
            "d": {
                "since": None,
                "activities": [activity] if activity else [],
                "status": status,
                "afk": afk,
            },
        }
        await self._send(payload)
