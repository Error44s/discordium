"""Async HTTP client for the Discord REST API.

Built on aiohttp with automatic rate limiting, orjson serialisation,
multipart file uploads, and typed return values.
"""

from __future__ import annotations

import io
import logging
import sys
import urllib.parse
from typing import TYPE_CHECKING, Any

import aiohttp
import orjson

from .ratelimit import RateLimiter
from ..errors import Forbidden, HTTPError, NotFound, RateLimited, ServerError

if TYPE_CHECKING:
    from ..models.audit_log import AuditLog, AuditLogEvent
    from ..models.automod import AutoModAction, AutoModRule
    from ..models.embed import Embed
    from ..models.file import File
    from ..models.permissions import PermissionOverwrite
    from ..models.snowflake import Snowflake
    from ..models.thread import Thread
    from ..models.webhook import Webhook

logger = logging.getLogger("discordium.http")

API_BASE = "https://discord.com/api/v10"

# Client

class RESTClient:
    """Low-level async HTTP interface to Discord's REST API.

    Handles authentication, rate limiting, serialisation, multipart uploads
    and retries.
    """

    __slots__ = ("_token", "_session", "_limiter", "_max_retries", "_closed")

    def __init__(self, token: str, *, max_retries: int = 3) -> None:
        self._token = token
        self._session: aiohttp.ClientSession | None = None
        self._limiter = RateLimiter()
        self._max_retries = max_retries
        self._closed = False

    # Lifecycle

    async def _ensure_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                headers={
                    "Authorization": f"Bot {self._token}",
                    "User-Agent": (
                        f"DiscordBot (discordium, 0.1.0) "
                        f"Python/{sys.version_info.major}.{sys.version_info.minor}"
                    ),
                },
            )
        return self._session

    async def close(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()
        self._closed = True

    # Core request

    async def request(
        self,
        method: str,
        path: str,
        *,
        json: Any = None,
        params: dict[str, Any] | None = None,
        reason: str | None = None,
        files: list[File] | None = None,
    ) -> Any:
        """Send an authenticated request to the Discord API.

        Returns parsed JSON or ``None`` for 204 responses.
        Supports multipart file uploads via the *files* parameter.
        """
        session = await self._ensure_session()
        url = f"{API_BASE}{path}"

        headers: dict[str, str] = {}
        if reason:
            headers["X-Audit-Log-Reason"] = reason

        # Build request data
        request_data: bytes | aiohttp.FormData | None = None

        if files:
            # Multipart upload
            form = aiohttp.FormData()
            payload_json = orjson.dumps(json or {}).decode()
            form.add_field("payload_json", payload_json, content_type="application/json")
            for i, file in enumerate(files):
                form.add_field(
                    f"files[{i}]",
                    io.BytesIO(file.data),
                    filename=file.filename,
                    content_type=file.content_type,
                )
            request_data = form
        elif json is not None:
            request_data = orjson.dumps(json)
            headers["Content-Type"] = "application/json"

        for attempt in range(self._max_retries + 1):
            bucket = await self._limiter.acquire(method, path)
            try:
                kwargs: dict[str, Any] = {"headers": headers}
                if params:
                    kwargs["params"] = params

                if isinstance(request_data, aiohttp.FormData):
                    kwargs["data"] = request_data
                elif request_data is not None:
                    kwargs["data"] = request_data

                async with session.request(method, url, **kwargs) as resp:
                    remaining = resp.headers.get("X-RateLimit-Remaining")
                    reset_after = resp.headers.get("X-RateLimit-Reset-After")
                    is_global = resp.headers.get("X-RateLimit-Global") == "true"

                    self._limiter.release(
                        bucket,
                        remaining=int(remaining) if remaining else None,
                        reset_after=float(reset_after) if reset_after else None,
                        is_global=is_global,
                    )

                    if resp.status == 204:
                        return None

                    body_bytes = await resp.read()
                    if resp.content_type == "application/json":
                        body = orjson.loads(body_bytes)
                    else:
                        body = body_bytes.decode("utf-8", errors="replace")

                    if 200 <= resp.status < 300:
                        return body

                    if resp.status == 429:
                        retry_after = (
                            float(body.get("retry_after", 1))
                            if isinstance(body, dict)
                            else 1.0
                        )
                        gl = body.get("global", False) if isinstance(body, dict) else False
                        await self._limiter.handle_429(retry_after, is_global=gl)
                        continue

                    if resp.status >= 500 and attempt < self._max_retries:
                        logger.warning(
                            "Server error %d on %s %s, retrying…",
                            resp.status, method, path,
                        )
                        continue

                    if resp.status == 403:
                        raise Forbidden(body)
                    if resp.status == 404:
                        raise NotFound(body)
                    if resp.status >= 500:
                        raise ServerError(resp.status, body)
                    raise HTTPError(resp.status, body)

            except HTTPError:
                raise
            except Exception:
                self._limiter.release(bucket)
                if attempt < self._max_retries:
                    continue
                raise

        raise HTTPError(0, "Max retries exceeded")

    #  MESSAGES

    async def send_message(
        self,
        channel_id: Snowflake,
        content: str | None = None,
        *,
        embed: Embed | None = None,
        embeds: list[Embed] | None = None,
        components: list[Any] | None = None,
        files: list[File] | None = None,
        message_reference: Snowflake | None = None,
        mention_author: bool = True,
        sticker_ids: list[Snowflake] | None = None,
        tts: bool = False,
    ) -> Any:
        """Send a message to a channel."""
        from ..models.message import Message

        payload: dict[str, Any] = {}
        if content is not None:
            payload["content"] = content
        if embed is not None:
            payload["embeds"] = [embed.to_dict()]
        elif embeds:
            payload["embeds"] = [e.to_dict() for e in embeds]
        if components:
            payload["components"] = [c.to_dict() for c in components]
        if message_reference is not None:
            payload["message_reference"] = {"message_id": str(message_reference)}
            if not mention_author:
                payload["allowed_mentions"] = {"replied_user": False}
        if sticker_ids:
            payload["sticker_ids"] = [str(s) for s in sticker_ids]
        if tts:
            payload["tts"] = True
        if files:
            payload["attachments"] = [f.to_attachment_dict(i) for i, f in enumerate(files)]

        data = await self.request(
            "POST", f"/channels/{channel_id}/messages",
            json=payload, files=files,
        )
        return Message.from_payload(data, rest=self)

    async def edit_message(
        self,
        channel_id: Snowflake,
        message_id: Snowflake,
        content: str | None = None,
        *,
        embed: Embed | None = None,
        embeds: list[Embed] | None = None,
        components: list[Any] | None = None,
        files: list[File] | None = None,
    ) -> Any:
        from ..models.message import Message

        payload: dict[str, Any] = {}
        if content is not None:
            payload["content"] = content
        if embed is not None:
            payload["embeds"] = [embed.to_dict()]
        elif embeds:
            payload["embeds"] = [e.to_dict() for e in embeds]
        if components is not None:
            payload["components"] = [c.to_dict() for c in components]
        if files:
            payload["attachments"] = [f.to_attachment_dict(i) for i, f in enumerate(files)]

        data = await self.request(
            "PATCH", f"/channels/{channel_id}/messages/{message_id}",
            json=payload, files=files,
        )
        return Message.from_payload(data, rest=self)

    async def delete_message(
        self, channel_id: Snowflake, message_id: Snowflake
    ) -> None:
        await self.request("DELETE", f"/channels/{channel_id}/messages/{message_id}")

    async def bulk_delete_messages(
        self,
        channel_id: Snowflake,
        message_ids: list[Snowflake],
        *,
        reason: str | None = None,
    ) -> None:
        """Delete 2-100 messages at once (max 14 days old)."""
        await self.request(
            "POST",
            f"/channels/{channel_id}/messages/bulk-delete",
            json={"messages": [str(m) for m in message_ids]},
            reason=reason,
        )

    async def get_message(self, channel_id: Snowflake, message_id: Snowflake) -> Any:
        from ..models.message import Message
        data = await self.request("GET", f"/channels/{channel_id}/messages/{message_id}")
        return Message.from_payload(data, rest=self)

    async def get_messages(
        self,
        channel_id: Snowflake,
        *,
        limit: int = 50,
        before: Snowflake | None = None,
        after: Snowflake | None = None,
        around: Snowflake | None = None,
    ) -> list[Any]:
        from ..models.message import Message
        params: dict[str, Any] = {"limit": min(limit, 100)}
        if before:
            params["before"] = str(before)
        if after:
            params["after"] = str(after)
        if around:
            params["around"] = str(around)
        data = await self.request("GET", f"/channels/{channel_id}/messages", params=params)
        return [Message.from_payload(m, rest=self) for m in data]

    async def pin_message(self, channel_id: Snowflake, message_id: Snowflake) -> None:
        await self.request("PUT", f"/channels/{channel_id}/pins/{message_id}")

    async def unpin_message(self, channel_id: Snowflake, message_id: Snowflake) -> None:
        await self.request("DELETE", f"/channels/{channel_id}/pins/{message_id}")

    async def get_pinned_messages(self, channel_id: Snowflake) -> list[Any]:
        from ..models.message import Message
        data = await self.request("GET", f"/channels/{channel_id}/pins")
        return [Message.from_payload(m, rest=self) for m in data]

    # Reactions

    async def add_reaction(
        self, channel_id: Snowflake, message_id: Snowflake, emoji: str
    ) -> None:
        encoded = urllib.parse.quote(emoji)
        await self.request(
            "PUT",
            f"/channels/{channel_id}/messages/{message_id}/reactions/{encoded}/@me",
        )

    async def remove_reaction(
        self,
        channel_id: Snowflake,
        message_id: Snowflake,
        emoji: str,
        user_id: Snowflake | None = None,
    ) -> None:
        encoded = urllib.parse.quote(emoji)
        target = str(user_id) if user_id else "@me"
        await self.request(
            "DELETE",
            f"/channels/{channel_id}/messages/{message_id}/reactions/{encoded}/{target}",
        )

    async def clear_reactions(
        self, channel_id: Snowflake, message_id: Snowflake, emoji: str | None = None
    ) -> None:
        if emoji:
            encoded = urllib.parse.quote(emoji)
            await self.request(
                "DELETE",
                f"/channels/{channel_id}/messages/{message_id}/reactions/{encoded}",
            )
        else:
            await self.request(
                "DELETE",
                f"/channels/{channel_id}/messages/{message_id}/reactions",
            )

    #  CHANNELS

    async def get_channel(self, channel_id: Snowflake) -> Any:
        from ..models.channel import Channel
        data = await self.request("GET", f"/channels/{channel_id}")
        return Channel.from_payload(data)

    async def edit_channel(
        self,
        channel_id: Snowflake,
        *,
        name: str | None = None,
        topic: str | None = None,
        nsfw: bool | None = None,
        rate_limit_per_user: int | None = None,
        position: int | None = None,
        parent_id: Snowflake | None = None,
        permission_overwrites: list[PermissionOverwrite] | None = None,
        reason: str | None = None,
    ) -> Any:
        from ..models.channel import Channel
        payload: dict[str, Any] = {}
        if name is not None:
            payload["name"] = name
        if topic is not None:
            payload["topic"] = topic
        if nsfw is not None:
            payload["nsfw"] = nsfw
        if rate_limit_per_user is not None:
            payload["rate_limit_per_user"] = rate_limit_per_user
        if position is not None:
            payload["position"] = position
        if parent_id is not None:
            payload["parent_id"] = str(parent_id)
        if permission_overwrites is not None:
            payload["permission_overwrites"] = [o.to_dict() for o in permission_overwrites]
        data = await self.request(
            "PATCH", f"/channels/{channel_id}", json=payload, reason=reason
        )
        return Channel.from_payload(data)

    async def delete_channel(
        self, channel_id: Snowflake, *, reason: str | None = None
    ) -> None:
        await self.request("DELETE", f"/channels/{channel_id}", reason=reason)

    async def create_channel(
        self,
        guild_id: Snowflake,
        name: str,
        *,
        type: int = 0,
        topic: str | None = None,
        position: int | None = None,
        parent_id: Snowflake | None = None,
        permission_overwrites: list[PermissionOverwrite] | None = None,
        nsfw: bool = False,
        reason: str | None = None,
    ) -> Any:
        from ..models.channel import Channel
        payload: dict[str, Any] = {"name": name, "type": type}
        if topic is not None:
            payload["topic"] = topic
        if position is not None:
            payload["position"] = position
        if parent_id is not None:
            payload["parent_id"] = str(parent_id)
        if permission_overwrites is not None:
            payload["permission_overwrites"] = [o.to_dict() for o in permission_overwrites]
        if nsfw:
            payload["nsfw"] = True
        data = await self.request(
            "POST", f"/guilds/{guild_id}/channels", json=payload, reason=reason
        )
        return Channel.from_payload(data)

    #  GUILDS

    async def get_guild(self, guild_id: Snowflake, *, with_counts: bool = True) -> Any:
        from ..models.guild import Guild
        params = {"with_counts": "true"} if with_counts else None
        data = await self.request("GET", f"/guilds/{guild_id}", params=params)
        return Guild.from_payload(data)

    async def edit_guild(
        self,
        guild_id: Snowflake,
        *,
        name: str | None = None,
        description: str | None = None,
        reason: str | None = None,
        **kwargs: Any,
    ) -> Any:
        from ..models.guild import Guild
        payload: dict[str, Any] = {}
        if name is not None:
            payload["name"] = name
        if description is not None:
            payload["description"] = description
        payload.update(kwargs)
        data = await self.request(
            "PATCH", f"/guilds/{guild_id}", json=payload, reason=reason
        )
        return Guild.from_payload(data)

    async def get_guild_channels(self, guild_id: Snowflake) -> list[Any]:
        from ..models.channel import Channel
        data = await self.request("GET", f"/guilds/{guild_id}/channels")
        return [Channel.from_payload(c) for c in data]

    # Members

    async def get_member(self, guild_id: Snowflake, user_id: Snowflake) -> Any:
        from ..models.member import Member
        data = await self.request("GET", f"/guilds/{guild_id}/members/{user_id}")
        return Member.from_payload(data, guild_id=guild_id)

    async def list_members(
        self, guild_id: Snowflake, *, limit: int = 100, after: Snowflake | None = None
    ) -> list[Any]:
        from ..models.member import Member
        params: dict[str, Any] = {"limit": min(limit, 1000)}
        if after:
            params["after"] = str(after)
        data = await self.request("GET", f"/guilds/{guild_id}/members", params=params)
        return [Member.from_payload(m, guild_id=guild_id) for m in data]

    async def search_members(
        self, guild_id: Snowflake, query: str, *, limit: int = 100
    ) -> list[Any]:
        from ..models.member import Member
        params = {"query": query, "limit": min(limit, 1000)}
        data = await self.request(
            "GET", f"/guilds/{guild_id}/members/search", params=params
        )
        return [Member.from_payload(m, guild_id=guild_id) for m in data]

    async def edit_member(
        self,
        guild_id: Snowflake,
        user_id: Snowflake,
        *,
        nick: str | None = None,
        roles: list[Snowflake] | None = None,
        mute: bool | None = None,
        deaf: bool | None = None,
        channel_id: Snowflake | None = None,
        communication_disabled_until: str | None = None,
        reason: str | None = None,
    ) -> Any:
        from ..models.member import Member
        payload: dict[str, Any] = {}
        if nick is not None:
            payload["nick"] = nick
        if roles is not None:
            payload["roles"] = [str(r) for r in roles]
        if mute is not None:
            payload["mute"] = mute
        if deaf is not None:
            payload["deaf"] = deaf
        if channel_id is not None:
            payload["channel_id"] = str(channel_id)
        if communication_disabled_until is not None:
            payload["communication_disabled_until"] = communication_disabled_until
        data = await self.request(
            "PATCH", f"/guilds/{guild_id}/members/{user_id}",
            json=payload, reason=reason,
        )
        return Member.from_payload(data, guild_id=guild_id)

    async def add_member_role(
        self,
        guild_id: Snowflake,
        user_id: Snowflake,
        role_id: Snowflake,
        *,
        reason: str | None = None,
    ) -> None:
        await self.request(
            "PUT", f"/guilds/{guild_id}/members/{user_id}/roles/{role_id}",
            reason=reason,
        )

    async def remove_member_role(
        self,
        guild_id: Snowflake,
        user_id: Snowflake,
        role_id: Snowflake,
        *,
        reason: str | None = None,
    ) -> None:
        await self.request(
            "DELETE", f"/guilds/{guild_id}/members/{user_id}/roles/{role_id}",
            reason=reason,
        )

    async def kick_member(
        self, guild_id: Snowflake, user_id: Snowflake, *, reason: str | None = None
    ) -> None:
        await self.request(
            "DELETE", f"/guilds/{guild_id}/members/{user_id}", reason=reason
        )

    async def ban_member(
        self,
        guild_id: Snowflake,
        user_id: Snowflake,
        *,
        delete_message_seconds: int = 0,
        reason: str | None = None,
    ) -> None:
        payload: dict[str, Any] = {}
        if delete_message_seconds:
            payload["delete_message_seconds"] = delete_message_seconds
        await self.request(
            "PUT", f"/guilds/{guild_id}/bans/{user_id}",
            json=payload, reason=reason,
        )

    async def unban_member(
        self, guild_id: Snowflake, user_id: Snowflake, *, reason: str | None = None
    ) -> None:
        await self.request(
            "DELETE", f"/guilds/{guild_id}/bans/{user_id}", reason=reason
        )

    async def get_bans(self, guild_id: Snowflake, *, limit: int = 1000) -> list[dict[str, Any]]:
        return await self.request(
            "GET", f"/guilds/{guild_id}/bans", params={"limit": limit}
        )

    async def timeout_member(
        self,
        guild_id: Snowflake,
        user_id: Snowflake,
        *,
        until: str | None,
        reason: str | None = None,
    ) -> Any:
        """Timeout (mute) a member. Pass until=None to remove timeout."""
        return await self.edit_member(
            guild_id, user_id,
            communication_disabled_until=until,
            reason=reason,
        )

    # Roles

    async def get_roles(self, guild_id: Snowflake) -> list[Any]:
        from ..models.role import Role
        data = await self.request("GET", f"/guilds/{guild_id}/roles")
        return [Role.from_payload(r) for r in data]

    async def create_role(
        self,
        guild_id: Snowflake,
        *,
        name: str = "new role",
        permissions: int | None = None,
        color: int = 0,
        hoist: bool = False,
        mentionable: bool = False,
        reason: str | None = None,
    ) -> Any:
        from ..models.role import Role
        payload: dict[str, Any] = {
            "name": name, "color": color,
            "hoist": hoist, "mentionable": mentionable,
        }
        if permissions is not None:
            payload["permissions"] = str(permissions)
        data = await self.request(
            "POST", f"/guilds/{guild_id}/roles", json=payload, reason=reason
        )
        return Role.from_payload(data)

    async def edit_role(
        self,
        guild_id: Snowflake,
        role_id: Snowflake,
        *,
        name: str | None = None,
        permissions: int | None = None,
        color: int | None = None,
        hoist: bool | None = None,
        mentionable: bool | None = None,
        reason: str | None = None,
    ) -> Any:
        from ..models.role import Role
        payload: dict[str, Any] = {}
        if name is not None:
            payload["name"] = name
        if permissions is not None:
            payload["permissions"] = str(permissions)
        if color is not None:
            payload["color"] = color
        if hoist is not None:
            payload["hoist"] = hoist
        if mentionable is not None:
            payload["mentionable"] = mentionable
        data = await self.request(
            "PATCH", f"/guilds/{guild_id}/roles/{role_id}",
            json=payload, reason=reason,
        )
        return Role.from_payload(data)

    async def delete_role(
        self, guild_id: Snowflake, role_id: Snowflake, *, reason: str | None = None
    ) -> None:
        await self.request(
            "DELETE", f"/guilds/{guild_id}/roles/{role_id}", reason=reason
        )

    #  THREADS

    async def create_thread_from_message(
        self,
        channel_id: Snowflake,
        message_id: Snowflake,
        name: str,
        *,
        auto_archive_duration: int = 1440,
        reason: str | None = None,
    ) -> Any:
        from ..models.thread import Thread
        payload = {"name": name, "auto_archive_duration": auto_archive_duration}
        data = await self.request(
            "POST", f"/channels/{channel_id}/messages/{message_id}/threads",
            json=payload, reason=reason,
        )
        return Thread.from_payload(data)

    async def create_thread(
        self,
        channel_id: Snowflake,
        name: str,
        *,
        type: int = 11,
        auto_archive_duration: int = 1440,
        invitable: bool | None = None,
        reason: str | None = None,
    ) -> Any:
        from ..models.thread import Thread
        payload: dict[str, Any] = {
            "name": name, "type": type,
            "auto_archive_duration": auto_archive_duration,
        }
        if invitable is not None:
            payload["invitable"] = invitable
        data = await self.request(
            "POST", f"/channels/{channel_id}/threads",
            json=payload, reason=reason,
        )
        return Thread.from_payload(data)

    async def create_forum_thread(
        self,
        channel_id: Snowflake,
        name: str,
        *,
        content: str | None = None,
        embed: Embed | None = None,
        applied_tags: list[Snowflake] | None = None,
        auto_archive_duration: int = 1440,
        files: list[File] | None = None,
        reason: str | None = None,
    ) -> Any:
        from ..models.thread import Thread
        message: dict[str, Any] = {}
        if content:
            message["content"] = content
        if embed:
            message["embeds"] = [embed.to_dict()]
        if files:
            message["attachments"] = [f.to_attachment_dict(i) for i, f in enumerate(files)]
        payload: dict[str, Any] = {
            "name": name, "auto_archive_duration": auto_archive_duration,
            "message": message,
        }
        if applied_tags:
            payload["applied_tags"] = [str(t) for t in applied_tags]
        data = await self.request(
            "POST", f"/channels/{channel_id}/threads",
            json=payload, files=files, reason=reason,
        )
        return Thread.from_payload(data)

    async def join_thread(self, thread_id: Snowflake) -> None:
        await self.request("PUT", f"/channels/{thread_id}/thread-members/@me")

    async def leave_thread(self, thread_id: Snowflake) -> None:
        await self.request("DELETE", f"/channels/{thread_id}/thread-members/@me")

    async def add_thread_member(self, thread_id: Snowflake, user_id: Snowflake) -> None:
        await self.request("PUT", f"/channels/{thread_id}/thread-members/{user_id}")

    async def remove_thread_member(self, thread_id: Snowflake, user_id: Snowflake) -> None:
        await self.request("DELETE", f"/channels/{thread_id}/thread-members/{user_id}")

    async def list_active_threads(self, guild_id: Snowflake) -> dict[str, Any]:
        return await self.request("GET", f"/guilds/{guild_id}/threads/active")

    #  WEBHOOKS

    async def create_webhook(
        self, channel_id: Snowflake, name: str, *, reason: str | None = None,
    ) -> Any:
        from ..models.webhook import Webhook
        data = await self.request(
            "POST", f"/channels/{channel_id}/webhooks",
            json={"name": name}, reason=reason,
        )
        return Webhook.from_payload(data, rest=self)

    async def get_channel_webhooks(self, channel_id: Snowflake) -> list[Any]:
        from ..models.webhook import Webhook
        data = await self.request("GET", f"/channels/{channel_id}/webhooks")
        return [Webhook.from_payload(w, rest=self) for w in data]

    async def get_guild_webhooks(self, guild_id: Snowflake) -> list[Any]:
        from ..models.webhook import Webhook
        data = await self.request("GET", f"/guilds/{guild_id}/webhooks")
        return [Webhook.from_payload(w, rest=self) for w in data]

    #  AUDIT LOG

    async def get_audit_log(
        self,
        guild_id: Snowflake,
        *,
        user_id: Snowflake | None = None,
        action_type: int | None = None,
        before: Snowflake | None = None,
        after: Snowflake | None = None,
        limit: int = 50,
    ) -> Any:
        from ..models.audit_log import AuditLog
        params: dict[str, Any] = {"limit": min(limit, 100)}
        if user_id:
            params["user_id"] = str(user_id)
        if action_type is not None:
            params["action_type"] = action_type
        if before:
            params["before"] = str(before)
        if after:
            params["after"] = str(after)
        data = await self.request(
            "GET", f"/guilds/{guild_id}/audit-logs", params=params
        )
        return AuditLog(data)

    #  AUTOMOD

    async def list_automod_rules(self, guild_id: Snowflake) -> list[Any]:
        from ..models.automod import AutoModRule
        data = await self.request("GET", f"/guilds/{guild_id}/auto-moderation/rules")
        return [AutoModRule.from_payload(r) for r in data]

    async def get_automod_rule(self, guild_id: Snowflake, rule_id: Snowflake) -> Any:
        from ..models.automod import AutoModRule
        data = await self.request(
            "GET", f"/guilds/{guild_id}/auto-moderation/rules/{rule_id}"
        )
        return AutoModRule.from_payload(data)

    async def create_automod_rule(
        self,
        guild_id: Snowflake,
        *,
        name: str,
        event_type: int = 1,
        trigger_type: int,
        trigger_metadata: dict[str, Any] | None = None,
        actions: list[AutoModAction],
        enabled: bool = True,
        exempt_roles: list[Snowflake] | None = None,
        exempt_channels: list[Snowflake] | None = None,
        reason: str | None = None,
    ) -> Any:
        from ..models.automod import AutoModRule
        payload: dict[str, Any] = {
            "name": name, "event_type": event_type,
            "trigger_type": trigger_type,
            "actions": [a.to_dict() for a in actions],
            "enabled": enabled,
        }
        if trigger_metadata:
            payload["trigger_metadata"] = trigger_metadata
        if exempt_roles:
            payload["exempt_roles"] = [str(r) for r in exempt_roles]
        if exempt_channels:
            payload["exempt_channels"] = [str(c) for c in exempt_channels]
        data = await self.request(
            "POST", f"/guilds/{guild_id}/auto-moderation/rules",
            json=payload, reason=reason,
        )
        return AutoModRule.from_payload(data)

    async def delete_automod_rule(
        self, guild_id: Snowflake, rule_id: Snowflake, *, reason: str | None = None
    ) -> None:
        await self.request(
            "DELETE", f"/guilds/{guild_id}/auto-moderation/rules/{rule_id}",
            reason=reason,
        )

    #  INVITES & EMOJIS

    async def create_invite(
        self, channel_id: Snowflake, *, max_age: int = 86400,
        max_uses: int = 0, temporary: bool = False,
        unique: bool = False, reason: str | None = None,
    ) -> dict[str, Any]:
        return await self.request(
            "POST", f"/channels/{channel_id}/invites",
            json={"max_age": max_age, "max_uses": max_uses,
                  "temporary": temporary, "unique": unique},
            reason=reason,
        )

    async def delete_invite(self, code: str, *, reason: str | None = None) -> None:
        await self.request("DELETE", f"/invites/{code}", reason=reason)

    async def get_guild_invites(self, guild_id: Snowflake) -> list[dict[str, Any]]:
        return await self.request("GET", f"/guilds/{guild_id}/invites")

    async def list_emojis(self, guild_id: Snowflake) -> list[dict[str, Any]]:
        return await self.request("GET", f"/guilds/{guild_id}/emojis")

    async def create_emoji(
        self, guild_id: Snowflake, *, name: str, image: str,
        roles: list[Snowflake] | None = None, reason: str | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {"name": name, "image": image}
        if roles:
            payload["roles"] = [str(r) for r in roles]
        return await self.request(
            "POST", f"/guilds/{guild_id}/emojis", json=payload, reason=reason
        )

    async def delete_emoji(
        self, guild_id: Snowflake, emoji_id: Snowflake, *, reason: str | None = None
    ) -> None:
        await self.request(
            "DELETE", f"/guilds/{guild_id}/emojis/{emoji_id}", reason=reason
        )

    #  USER / GATEWAY

    async def get_current_user(self) -> Any:
        from ..models.user import User
        data = await self.request("GET", "/users/@me")
        return User.from_payload(data)

    async def get_user(self, user_id: Snowflake) -> Any:
        from ..models.user import User
        data = await self.request("GET", f"/users/{user_id}")
        return User.from_payload(data)

    async def get_gateway_url(self) -> str:
        data = await self.request("GET", "/gateway/bot")
        return data["url"]

    async def get_gateway_bot(self) -> dict[str, Any]:
        """Get gateway info including recommended shard count and session limits."""
        return await self.request("GET", "/gateway/bot")

    #  REACTIONS – extended

    async def get_reactions(
        self,
        channel_id: Snowflake,
        message_id: Snowflake,
        emoji: str,
        *,
        after: Snowflake | None = None,
        limit: int = 25,
        type: int = 0,
    ) -> list[Any]:
        """Get users who reacted with a specific emoji.

        *type* – 0 = normal reaction, 1 = burst/super reaction.
        """
        from ..models.user import User
        encoded = urllib.parse.quote(emoji)
        params: dict[str, Any] = {"limit": min(limit, 100), "type": type}
        if after:
            params["after"] = str(after)
        data = await self.request(
            "GET",
            f"/channels/{channel_id}/messages/{message_id}/reactions/{encoded}",
            params=params,
        )
        return [User.from_payload(u) for u in data]

    #  MESSAGES – extended

    async def crosspost_message(
        self, channel_id: Snowflake, message_id: Snowflake
    ) -> Any:
        """Crosspost (publish) a message in an Announcement channel."""
        from ..models.message import Message
        data = await self.request(
            "POST", f"/channels/{channel_id}/messages/{message_id}/crosspost"
        )
        return Message.from_payload(data, rest=self)

    async def send_typing(self, channel_id: Snowflake) -> None:
        """Trigger the typing indicator in a channel."""
        await self.request("POST", f"/channels/{channel_id}/typing")

    #  CHANNELS – extended

    async def get_channel_invites(self, channel_id: Snowflake) -> list[dict[str, Any]]:
        """Get all active invites for a channel."""
        return await self.request("GET", f"/channels/{channel_id}/invites")

    async def edit_channel_permissions(
        self,
        channel_id: Snowflake,
        overwrite_id: Snowflake,
        *,
        allow: int | None = None,
        deny: int | None = None,
        type: int = 1,
        reason: str | None = None,
    ) -> None:
        """Edit permission overwrites for a channel (type 0 = role, 1 = member)."""
        payload: dict[str, Any] = {"type": type}
        if allow is not None:
            payload["allow"] = str(allow)
        if deny is not None:
            payload["deny"] = str(deny)
        await self.request(
            "PUT",
            f"/channels/{channel_id}/permissions/{overwrite_id}",
            json=payload,
            reason=reason,
        )

    async def delete_channel_permission(
        self,
        channel_id: Snowflake,
        overwrite_id: Snowflake,
        *,
        reason: str | None = None,
    ) -> None:
        """Delete a permission overwrite for a channel."""
        await self.request(
            "DELETE",
            f"/channels/{channel_id}/permissions/{overwrite_id}",
            reason=reason,
        )

    async def follow_announcement_channel(
        self, channel_id: Snowflake, webhook_channel_id: Snowflake
    ) -> dict[str, Any]:
        """Follow an Announcement channel to send messages to a target channel."""
        return await self.request(
            "POST",
            f"/channels/{channel_id}/followers",
            json={"webhook_channel_id": str(webhook_channel_id)},
        )

    async def modify_guild_channel_positions(
        self,
        guild_id: Snowflake,
        positions: list[dict[str, Any]],
    ) -> None:
        """Batch-update channel positions.

        Each entry: ``{"id": channel_id, "position": int, "parent_id": ...}``.
        """
        await self.request(
            "PATCH",
            f"/guilds/{guild_id}/channels",
            json=positions,
        )

    #  INVITES – extended

    async def get_invite(
        self,
        code: str,
        *,
        with_counts: bool = True,
        with_expiration: bool = True,
    ) -> dict[str, Any]:
        """Fetch metadata about an invite by its code."""
        params: dict[str, Any] = {}
        if with_counts:
            params["with_counts"] = "true"
        if with_expiration:
            params["with_expiration"] = "true"
        return await self.request("GET", f"/invites/{code}", params=params or None)

    async def get_channel_invites_list(self, channel_id: Snowflake) -> list[dict[str, Any]]:
        """Alias – identical to get_channel_invites but more explicit name."""
        return await self.get_channel_invites(channel_id)

    #  GUILD / MEMBER MODERATION – extended

    async def get_ban(self, guild_id: Snowflake, user_id: Snowflake) -> dict[str, Any]:
        """Get the ban record for a single user."""
        return await self.request("GET", f"/guilds/{guild_id}/bans/{user_id}")

    async def get_bans_paginated(
        self,
        guild_id: Snowflake,
        *,
        limit: int = 1000,
        before: Snowflake | None = None,
        after: Snowflake | None = None,
    ) -> list[dict[str, Any]]:
        """Fetch ban list with pagination cursors."""
        params: dict[str, Any] = {"limit": min(limit, 1000)}
        if before:
            params["before"] = str(before)
        if after:
            params["after"] = str(after)
        return await self.request(
            "GET", f"/guilds/{guild_id}/bans", params=params
        )

    async def bulk_ban(
        self,
        guild_id: Snowflake,
        user_ids: list[Snowflake],
        *,
        delete_message_seconds: int = 0,
        reason: str | None = None,
    ) -> dict[str, Any]:
        """Ban up to 200 users at once (Discord API v10 bulk-ban).

        Returns ``{"banned_users": [...], "failed_users": [...]}``.
        """
        payload: dict[str, Any] = {
            "user_ids": [str(u) for u in user_ids],
        }
        if delete_message_seconds:
            payload["delete_message_seconds"] = delete_message_seconds
        return await self.request(
            "POST",
            f"/guilds/{guild_id}/bulk-ban",
            json=payload,
            reason=reason,
        )

    async def prune_members(
        self,
        guild_id: Snowflake,
        *,
        days: int = 7,
        compute_prune_count: bool = True,
        include_roles: list[Snowflake] | None = None,
        reason: str | None = None,
    ) -> dict[str, Any]:
        """Begin a guild prune. Returns ``{"pruned": int}``."""
        payload: dict[str, Any] = {
            "days": days,
            "compute_prune_count": compute_prune_count,
        }
        if include_roles:
            payload["include_roles"] = [str(r) for r in include_roles]
        return await self.request(
            "POST",
            f"/guilds/{guild_id}/prune",
            json=payload,
            reason=reason,
        )

    async def get_prune_count(
        self,
        guild_id: Snowflake,
        *,
        days: int = 7,
        include_roles: list[Snowflake] | None = None,
    ) -> dict[str, Any]:
        """Estimate the number of members that would be pruned."""
        params: dict[str, Any] = {"days": days}
        if include_roles:
            params["include_roles"] = ",".join(str(r) for r in include_roles)
        return await self.request(
            "GET", f"/guilds/{guild_id}/prune", params=params
        )

    async def move_member_voice(
        self,
        guild_id: Snowflake,
        user_id: Snowflake,
        channel_id: Snowflake | None,
        *,
        reason: str | None = None,
    ) -> Any:
        """Move a member to a different voice channel (or disconnect with ``None``)."""
        return await self.edit_member(
            guild_id, user_id, channel_id=channel_id, reason=reason
        )

    async def deafen_member(
        self,
        guild_id: Snowflake,
        user_id: Snowflake,
        deaf: bool,
        *,
        reason: str | None = None,
    ) -> Any:
        """Server-deafen or un-deafen a member."""
        return await self.edit_member(
            guild_id, user_id, deaf=deaf, reason=reason
        )

    async def mute_member(
        self,
        guild_id: Snowflake,
        user_id: Snowflake,
        mute: bool,
        *,
        reason: str | None = None,
    ) -> Any:
        """Server-mute or un-mute a member."""
        return await self.edit_member(
            guild_id, user_id, mute=mute, reason=reason
        )

    async def set_member_nick(
        self,
        guild_id: Snowflake,
        user_id: Snowflake,
        nick: str | None,
        *,
        reason: str | None = None,
    ) -> Any:
        """Set (or clear) a member's server nickname."""
        return await self.edit_member(
            guild_id, user_id, nick=nick or "", reason=reason
        )

    async def set_own_nick(self, guild_id: Snowflake, nick: str) -> None:
        """Change the bot's own nickname in a guild."""
        await self.request(
            "PATCH",
            f"/guilds/{guild_id}/members/@me",
            json={"nick": nick},
        )

    #  ROLES – extended

    async def get_role(self, guild_id: Snowflake, role_id: Snowflake) -> Any:
        """Fetch a single role by ID."""
        from ..models.role import Role
        data = await self.request("GET", f"/guilds/{guild_id}/roles/{role_id}")
        return Role.from_payload(data)

    async def reorder_roles(
        self,
        guild_id: Snowflake,
        positions: list[dict[str, Any]],
        *,
        reason: str | None = None,
    ) -> list[Any]:
        """Batch-update role positions.

        Each entry: ``{"id": role_id, "position": int}``.
        Returns the updated list of roles.
        """
        from ..models.role import Role
        data = await self.request(
            "PATCH",
            f"/guilds/{guild_id}/roles",
            json=positions,
            reason=reason,
        )
        return [Role.from_payload(r) for r in data]

    #  THREADS – extended

    async def edit_thread(
        self,
        thread_id: Snowflake,
        *,
        name: str | None = None,
        archived: bool | None = None,
        locked: bool | None = None,
        invitable: bool | None = None,
        auto_archive_duration: int | None = None,
        rate_limit_per_user: int | None = None,
        applied_tags: list[Snowflake] | None = None,
        reason: str | None = None,
    ) -> Any:
        """Edit a thread channel."""
        from ..models.thread import Thread
        payload: dict[str, Any] = {}
        if name is not None:
            payload["name"] = name
        if archived is not None:
            payload["archived"] = archived
        if locked is not None:
            payload["locked"] = locked
        if invitable is not None:
            payload["invitable"] = invitable
        if auto_archive_duration is not None:
            payload["auto_archive_duration"] = auto_archive_duration
        if rate_limit_per_user is not None:
            payload["rate_limit_per_user"] = rate_limit_per_user
        if applied_tags is not None:
            payload["applied_tags"] = [str(t) for t in applied_tags]
        data = await self.request(
            "PATCH", f"/channels/{thread_id}", json=payload, reason=reason
        )
        return Thread.from_payload(data)

    async def get_thread_members(
        self,
        thread_id: Snowflake,
        *,
        with_member: bool = False,
        after: Snowflake | None = None,
        limit: int = 100,
    ) -> list[Any]:
        """List all members of a thread.

        Set *with_member* to include full guild Member objects.
        """
        from ..models.thread import ThreadMember
        params: dict[str, Any] = {"limit": min(limit, 100)}
        if with_member:
            params["with_member"] = "true"
        if after:
            params["after"] = str(after)
        data = await self.request(
            "GET", f"/channels/{thread_id}/thread-members", params=params
        )
        return [ThreadMember.from_payload(m) for m in data]

    async def get_thread_member(
        self,
        thread_id: Snowflake,
        user_id: Snowflake,
        *,
        with_member: bool = False,
    ) -> Any:
        """Get a specific thread member."""
        from ..models.thread import ThreadMember
        params: dict[str, Any] = {}
        if with_member:
            params["with_member"] = "true"
        data = await self.request(
            "GET",
            f"/channels/{thread_id}/thread-members/{user_id}",
            params=params or None,
        )
        return ThreadMember.from_payload(data)

    async def list_public_archived_threads(
        self,
        channel_id: Snowflake,
        *,
        before: str | None = None,
        limit: int = 50,
    ) -> dict[str, Any]:
        """List public archived threads in a channel."""
        params: dict[str, Any] = {"limit": min(limit, 100)}
        if before:
            params["before"] = before
        return await self.request(
            "GET",
            f"/channels/{channel_id}/threads/archived/public",
            params=params,
        )

    async def list_private_archived_threads(
        self,
        channel_id: Snowflake,
        *,
        before: str | None = None,
        limit: int = 50,
    ) -> dict[str, Any]:
        """List private archived threads in a channel."""
        params: dict[str, Any] = {"limit": min(limit, 100)}
        if before:
            params["before"] = before
        return await self.request(
            "GET",
            f"/channels/{channel_id}/threads/archived/private",
            params=params,
        )

    async def list_joined_private_archived_threads(
        self,
        channel_id: Snowflake,
        *,
        before: str | None = None,
        limit: int = 50,
    ) -> dict[str, Any]:
        """List private archived threads the current user has joined."""
        params: dict[str, Any] = {"limit": min(limit, 100)}
        if before:
            params["before"] = before
        return await self.request(
            "GET",
            f"/channels/{channel_id}/users/@me/threads/archived/private",
            params=params,
        )

    #  WEBHOOKS – extended

    async def get_webhook(self, webhook_id: Snowflake) -> Any:
        """Fetch a webhook by ID (bot auth)."""
        from ..models.webhook import Webhook
        data = await self.request("GET", f"/webhooks/{webhook_id}")
        return Webhook.from_payload(data, rest=self)

    async def get_webhook_with_token(self, webhook_id: Snowflake, token: str) -> Any:
        """Fetch a webhook by ID + token (no bot auth required)."""
        from ..models.webhook import Webhook
        data = await self.request("GET", f"/webhooks/{webhook_id}/{token}")
        return Webhook.from_payload(data, rest=self)

    async def edit_webhook(
        self,
        webhook_id: Snowflake,
        *,
        name: str | None = None,
        channel_id: Snowflake | None = None,
        reason: str | None = None,
    ) -> Any:
        """Edit a webhook (bot auth)."""
        from ..models.webhook import Webhook
        payload: dict[str, Any] = {}
        if name is not None:
            payload["name"] = name
        if channel_id is not None:
            payload["channel_id"] = str(channel_id)
        data = await self.request(
            "PATCH", f"/webhooks/{webhook_id}", json=payload, reason=reason
        )
        return Webhook.from_payload(data, rest=self)

    async def delete_webhook(
        self, webhook_id: Snowflake, *, reason: str | None = None
    ) -> None:
        """Delete a webhook (bot auth)."""
        await self.request("DELETE", f"/webhooks/{webhook_id}", reason=reason)

    async def execute_webhook(
        self,
        webhook_id: Snowflake,
        token: str,
        *,
        content: str | None = None,
        username: str | None = None,
        avatar_url: str | None = None,
        tts: bool = False,
        embeds: list[Any] | None = None,
        components: list[Any] | None = None,
        files: list[Any] | None = None,
        allowed_mentions: dict[str, Any] | None = None,
        thread_id: Snowflake | None = None,
        thread_name: str | None = None,
        wait: bool = False,
        flags: int | None = None,
    ) -> Any | None:
        """Execute (send a message via) a webhook.

        Returns the created Message if *wait* is True, else None.
        """
        from ..models.file import File
        payload: dict[str, Any] = {}
        if content is not None:
            payload["content"] = content
        if username:
            payload["username"] = username
        if avatar_url:
            payload["avatar_url"] = avatar_url
        if tts:
            payload["tts"] = True
        if embeds:
            payload["embeds"] = [e.to_dict() if hasattr(e, "to_dict") else e for e in embeds]
        if components:
            payload["components"] = [c.to_dict() if hasattr(c, "to_dict") else c for c in components]
        if allowed_mentions is not None:
            payload["allowed_mentions"] = allowed_mentions
        if thread_name:
            payload["thread_name"] = thread_name
        if flags is not None:
            payload["flags"] = flags
        if files:
            payload["attachments"] = [
                f.to_attachment_dict(i) if hasattr(f, "to_attachment_dict") else f
                for i, f in enumerate(files)
            ]

        params: dict[str, Any] = {}
        if wait:
            params["wait"] = "true"
        if thread_id:
            params["thread_id"] = str(thread_id)

        return await self.request(
            "POST",
            f"/webhooks/{webhook_id}/{token}",
            json=payload,
            params=params or None,
            files=files,
        )

    async def get_webhook_message(
        self,
        webhook_id: Snowflake,
        token: str,
        message_id: Snowflake,
        *,
        thread_id: Snowflake | None = None,
    ) -> Any:
        """Fetch a message sent by a webhook."""
        from ..models.message import Message
        params = {"thread_id": str(thread_id)} if thread_id else None
        data = await self.request(
            "GET",
            f"/webhooks/{webhook_id}/{token}/messages/{message_id}",
            params=params,
        )
        return Message.from_payload(data, rest=self)

    async def edit_webhook_message(
        self,
        webhook_id: Snowflake,
        token: str,
        message_id: Snowflake,
        *,
        content: str | None = None,
        embeds: list[Any] | None = None,
        components: list[Any] | None = None,
        files: list[Any] | None = None,
        thread_id: Snowflake | None = None,
    ) -> Any:
        """Edit a message previously sent by a webhook."""
        from ..models.message import Message
        payload: dict[str, Any] = {}
        if content is not None:
            payload["content"] = content
        if embeds is not None:
            payload["embeds"] = [e.to_dict() if hasattr(e, "to_dict") else e for e in embeds]
        if components is not None:
            payload["components"] = [c.to_dict() if hasattr(c, "to_dict") else c for c in components]
        if files:
            payload["attachments"] = [
                f.to_attachment_dict(i) if hasattr(f, "to_attachment_dict") else f
                for i, f in enumerate(files)
            ]

        params = {"thread_id": str(thread_id)} if thread_id else None
        data = await self.request(
            "PATCH",
            f"/webhooks/{webhook_id}/{token}/messages/{message_id}",
            json=payload,
            params=params,
            files=files,
        )
        return Message.from_payload(data, rest=self)

    async def delete_webhook_message(
        self,
        webhook_id: Snowflake,
        token: str,
        message_id: Snowflake,
        *,
        thread_id: Snowflake | None = None,
    ) -> None:
        """Delete a message sent by a webhook."""
        params = {"thread_id": str(thread_id)} if thread_id else None
        await self.request(
            "DELETE",
            f"/webhooks/{webhook_id}/{token}/messages/{message_id}",
            params=params,
        )

    #  AUDIT LOG – extended

    async def iter_audit_log(
        self,
        guild_id: Snowflake,
        *,
        user_id: Snowflake | None = None,
        action_type: int | None = None,
        before: Snowflake | None = None,
        limit: int = 100,
    ):
        """Async generator that pages through the full audit log.

        Yields :class:`~discordium.models.audit_log.AuditLogEntry` objects.
        Stops when fewer entries than requested are returned.

        Usage::

            async for entry in rest.iter_audit_log(guild_id, action_type=22):
                print(entry)
        """
        fetched = 0
        cursor = before
        while True:
            batch_size = min(100, limit - fetched) if limit else 100
            log = await self.get_audit_log(
                guild_id,
                user_id=user_id,
                action_type=action_type,
                before=cursor,
                limit=batch_size,
            )
            for entry in log.entries:
                yield entry
                fetched += 1
                if limit and fetched >= limit:
                    return
            if len(log.entries) < batch_size:
                return
            cursor = log.entries[-1].id

    #  APPLICATION COMMANDS

    async def get_global_commands(self, application_id: Snowflake) -> list[dict[str, Any]]:
        """List all global application commands."""
        return await self.request(
            "GET", f"/applications/{application_id}/commands"
        )

    async def create_global_command(
        self,
        application_id: Snowflake,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        """Create a global application command."""
        return await self.request(
            "POST", f"/applications/{application_id}/commands", json=payload
        )

    async def get_global_command(
        self, application_id: Snowflake, command_id: Snowflake
    ) -> dict[str, Any]:
        """Fetch a single global command."""
        return await self.request(
            "GET", f"/applications/{application_id}/commands/{command_id}"
        )

    async def edit_global_command(
        self,
        application_id: Snowflake,
        command_id: Snowflake,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        """Edit a global application command."""
        return await self.request(
            "PATCH",
            f"/applications/{application_id}/commands/{command_id}",
            json=payload,
        )

    async def delete_global_command(
        self, application_id: Snowflake, command_id: Snowflake
    ) -> None:
        """Delete a global application command."""
        await self.request(
            "DELETE", f"/applications/{application_id}/commands/{command_id}"
        )

    async def bulk_overwrite_global_commands(
        self, application_id: Snowflake, commands: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """Overwrite all global commands in one request."""
        return await self.request(
            "PUT", f"/applications/{application_id}/commands", json=commands
        )

    async def get_guild_commands(
        self, application_id: Snowflake, guild_id: Snowflake
    ) -> list[dict[str, Any]]:
        """List all guild-specific application commands."""
        return await self.request(
            "GET", f"/applications/{application_id}/guilds/{guild_id}/commands"
        )

    async def create_guild_command(
        self,
        application_id: Snowflake,
        guild_id: Snowflake,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        """Create a guild-scoped application command."""
        return await self.request(
            "POST",
            f"/applications/{application_id}/guilds/{guild_id}/commands",
            json=payload,
        )

    async def edit_guild_command(
        self,
        application_id: Snowflake,
        guild_id: Snowflake,
        command_id: Snowflake,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        """Edit a guild-scoped application command."""
        return await self.request(
            "PATCH",
            f"/applications/{application_id}/guilds/{guild_id}/commands/{command_id}",
            json=payload,
        )

    async def delete_guild_command(
        self,
        application_id: Snowflake,
        guild_id: Snowflake,
        command_id: Snowflake,
    ) -> None:
        """Delete a guild-scoped application command."""
        await self.request(
            "DELETE",
            f"/applications/{application_id}/guilds/{guild_id}/commands/{command_id}",
        )

    async def bulk_overwrite_guild_commands(
        self,
        application_id: Snowflake,
        guild_id: Snowflake,
        commands: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Overwrite all guild-scoped commands in one request."""
        return await self.request(
            "PUT",
            f"/applications/{application_id}/guilds/{guild_id}/commands",
            json=commands,
        )

    async def get_guild_command_permissions(
        self, application_id: Snowflake, guild_id: Snowflake
    ) -> list[dict[str, Any]]:
        """Get permissions for all guild commands."""
        return await self.request(
            "GET",
            f"/applications/{application_id}/guilds/{guild_id}/commands/permissions",
        )

    async def get_command_permissions(
        self,
        application_id: Snowflake,
        guild_id: Snowflake,
        command_id: Snowflake,
    ) -> dict[str, Any]:
        """Get permissions for a specific guild command."""
        return await self.request(
            "GET",
            f"/applications/{application_id}/guilds/{guild_id}/commands/{command_id}/permissions",
        )

    async def edit_command_permissions(
        self,
        application_id: Snowflake,
        guild_id: Snowflake,
        command_id: Snowflake,
        permissions: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Overwrite permissions for a guild command."""
        return await self.request(
            "PUT",
            f"/applications/{application_id}/guilds/{guild_id}/commands/{command_id}/permissions",
            json={"permissions": permissions},
        )

    #  EMOJI – extended

    async def get_emoji(self, guild_id: Snowflake, emoji_id: Snowflake) -> dict[str, Any]:
        """Fetch a single guild emoji."""
        return await self.request("GET", f"/guilds/{guild_id}/emojis/{emoji_id}")

    async def edit_emoji(
        self,
        guild_id: Snowflake,
        emoji_id: Snowflake,
        *,
        name: str | None = None,
        roles: list[Snowflake] | None = None,
        reason: str | None = None,
    ) -> dict[str, Any]:
        """Edit a guild emoji's name or role restrictions."""
        payload: dict[str, Any] = {}
        if name is not None:
            payload["name"] = name
        if roles is not None:
            payload["roles"] = [str(r) for r in roles]
        return await self.request(
            "PATCH", f"/guilds/{guild_id}/emojis/{emoji_id}",
            json=payload, reason=reason,
        )

    #  STICKERS

    async def get_sticker(self, sticker_id: Snowflake) -> dict[str, Any]:
        """Fetch a sticker by ID."""
        return await self.request("GET", f"/stickers/{sticker_id}")

    async def list_guild_stickers(self, guild_id: Snowflake) -> list[dict[str, Any]]:
        """List all stickers in a guild."""
        return await self.request("GET", f"/guilds/{guild_id}/stickers")

    async def get_guild_sticker(
        self, guild_id: Snowflake, sticker_id: Snowflake
    ) -> dict[str, Any]:
        """Fetch a single guild sticker."""
        return await self.request("GET", f"/guilds/{guild_id}/stickers/{sticker_id}")

    async def edit_guild_sticker(
        self,
        guild_id: Snowflake,
        sticker_id: Snowflake,
        *,
        name: str | None = None,
        description: str | None = None,
        tags: str | None = None,
        reason: str | None = None,
    ) -> dict[str, Any]:
        """Edit a guild sticker."""
        payload: dict[str, Any] = {}
        if name is not None:
            payload["name"] = name
        if description is not None:
            payload["description"] = description
        if tags is not None:
            payload["tags"] = tags
        return await self.request(
            "PATCH", f"/guilds/{guild_id}/stickers/{sticker_id}",
            json=payload, reason=reason,
        )

    async def delete_guild_sticker(
        self,
        guild_id: Snowflake,
        sticker_id: Snowflake,
        *,
        reason: str | None = None,
    ) -> None:
        """Delete a guild sticker."""
        await self.request(
            "DELETE", f"/guilds/{guild_id}/stickers/{sticker_id}", reason=reason
        )

    #  SCHEDULED EVENTS

    async def list_scheduled_events(
        self, guild_id: Snowflake, *, with_user_count: bool = True
    ) -> list[dict[str, Any]]:
        """List all scheduled events in a guild."""
        params = {"with_user_count": "true"} if with_user_count else None
        return await self.request(
            "GET", f"/guilds/{guild_id}/scheduled-events", params=params
        )

    async def create_scheduled_event(
        self,
        guild_id: Snowflake,
        *,
        name: str,
        scheduled_start_time: str,
        privacy_level: int = 2,
        entity_type: int,
        channel_id: Snowflake | None = None,
        entity_metadata: dict[str, Any] | None = None,
        scheduled_end_time: str | None = None,
        description: str | None = None,
        image: str | None = None,
        reason: str | None = None,
    ) -> dict[str, Any]:
        """Create a scheduled event.

        *entity_type*: 1 = Stage, 2 = Voice, 3 = External.
        """
        payload: dict[str, Any] = {
            "name": name,
            "privacy_level": privacy_level,
            "scheduled_start_time": scheduled_start_time,
            "entity_type": entity_type,
        }
        if channel_id is not None:
            payload["channel_id"] = str(channel_id)
        if entity_metadata is not None:
            payload["entity_metadata"] = entity_metadata
        if scheduled_end_time is not None:
            payload["scheduled_end_time"] = scheduled_end_time
        if description is not None:
            payload["description"] = description
        if image is not None:
            payload["image"] = image
        return await self.request(
            "POST", f"/guilds/{guild_id}/scheduled-events",
            json=payload, reason=reason,
        )

    async def get_scheduled_event(
        self,
        guild_id: Snowflake,
        event_id: Snowflake,
        *,
        with_user_count: bool = True,
    ) -> dict[str, Any]:
        """Fetch a single scheduled event."""
        params = {"with_user_count": "true"} if with_user_count else None
        return await self.request(
            "GET",
            f"/guilds/{guild_id}/scheduled-events/{event_id}",
            params=params,
        )

    async def edit_scheduled_event(
        self,
        guild_id: Snowflake,
        event_id: Snowflake,
        *,
        reason: str | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Edit a scheduled event. Pass any writable fields as kwargs."""
        return await self.request(
            "PATCH",
            f"/guilds/{guild_id}/scheduled-events/{event_id}",
            json=kwargs,
            reason=reason,
        )

    async def delete_scheduled_event(
        self, guild_id: Snowflake, event_id: Snowflake
    ) -> None:
        """Delete a scheduled event."""
        await self.request(
            "DELETE", f"/guilds/{guild_id}/scheduled-events/{event_id}"
        )

    async def get_scheduled_event_users(
        self,
        guild_id: Snowflake,
        event_id: Snowflake,
        *,
        limit: int = 100,
        with_member: bool = False,
        before: Snowflake | None = None,
        after: Snowflake | None = None,
    ) -> list[dict[str, Any]]:
        """List users subscribed to a scheduled event."""
        params: dict[str, Any] = {"limit": min(limit, 100)}
        if with_member:
            params["with_member"] = "true"
        if before:
            params["before"] = str(before)
        if after:
            params["after"] = str(after)
        return await self.request(
            "GET",
            f"/guilds/{guild_id}/scheduled-events/{event_id}/users",
            params=params,
        )

    #  SOUNDBOARD

    async def list_default_soundboard_sounds(self) -> list[dict[str, Any]]:
        """List Discord's built-in soundboard sounds."""
        return await self.request("GET", "/soundboard-default-sounds")

    async def list_guild_soundboard_sounds(
        self, guild_id: Snowflake
    ) -> list[dict[str, Any]]:
        """List a guild's custom soundboard sounds."""
        return await self.request(
            "GET", f"/guilds/{guild_id}/soundboard-sounds"
        )

    async def create_guild_soundboard_sound(
        self,
        guild_id: Snowflake,
        *,
        name: str,
        sound: str,
        volume: float = 1.0,
        emoji_id: Snowflake | None = None,
        emoji_name: str | None = None,
        reason: str | None = None,
    ) -> dict[str, Any]:
        """Upload a custom soundboard sound to a guild (base64-encoded MP3/OGG)."""
        payload: dict[str, Any] = {"name": name, "sound": sound, "volume": volume}
        if emoji_id is not None:
            payload["emoji_id"] = str(emoji_id)
        if emoji_name is not None:
            payload["emoji_name"] = emoji_name
        return await self.request(
            "POST", f"/guilds/{guild_id}/soundboard-sounds",
            json=payload, reason=reason,
        )

    async def edit_guild_soundboard_sound(
        self,
        guild_id: Snowflake,
        sound_id: Snowflake,
        *,
        name: str | None = None,
        volume: float | None = None,
        emoji_id: Snowflake | None = None,
        emoji_name: str | None = None,
        reason: str | None = None,
    ) -> dict[str, Any]:
        """Edit a guild soundboard sound."""
        payload: dict[str, Any] = {}
        if name is not None:
            payload["name"] = name
        if volume is not None:
            payload["volume"] = volume
        if emoji_id is not None:
            payload["emoji_id"] = str(emoji_id)
        if emoji_name is not None:
            payload["emoji_name"] = emoji_name
        return await self.request(
            "PATCH", f"/guilds/{guild_id}/soundboard-sounds/{sound_id}",
            json=payload, reason=reason,
        )

    async def delete_guild_soundboard_sound(
        self,
        guild_id: Snowflake,
        sound_id: Snowflake,
        *,
        reason: str | None = None,
    ) -> None:
        """Delete a guild soundboard sound."""
        await self.request(
            "DELETE", f"/guilds/{guild_id}/soundboard-sounds/{sound_id}",
            reason=reason,
        )

    async def send_soundboard_sound(
        self,
        channel_id: Snowflake,
        sound_id: Snowflake,
        *,
        source_guild_id: Snowflake | None = None,
    ) -> None:
        """Play a soundboard sound in a voice channel."""
        payload: dict[str, Any] = {"sound_id": str(sound_id)}
        if source_guild_id is not None:
            payload["source_guild_id"] = str(source_guild_id)
        await self.request(
            "POST", f"/channels/{channel_id}/send-soundboard-sound", json=payload
        )

    #  GUILD EXTRAS

    async def get_guild_preview(self, guild_id: Snowflake) -> dict[str, Any]:
        """Fetch a guild's preview (public info, no membership required)."""
        return await self.request("GET", f"/guilds/{guild_id}/preview")

    async def get_guild_vanity_url(self, guild_id: Snowflake) -> dict[str, Any]:
        """Get the guild's vanity invite URL (if any)."""
        return await self.request("GET", f"/guilds/{guild_id}/vanity-url")

    async def get_guild_widget(self, guild_id: Snowflake) -> dict[str, Any]:
        """Get the guild widget settings."""
        return await self.request("GET", f"/guilds/{guild_id}/widget")

    async def edit_guild_widget(
        self,
        guild_id: Snowflake,
        *,
        enabled: bool | None = None,
        channel_id: Snowflake | None = None,
        reason: str | None = None,
    ) -> dict[str, Any]:
        """Edit the guild widget settings."""
        payload: dict[str, Any] = {}
        if enabled is not None:
            payload["enabled"] = enabled
        if channel_id is not None:
            payload["channel_id"] = str(channel_id)
        return await self.request(
            "PATCH", f"/guilds/{guild_id}/widget", json=payload, reason=reason
        )

    async def get_guild_welcome_screen(self, guild_id: Snowflake) -> dict[str, Any]:
        """Get the welcome screen of a community guild."""
        return await self.request("GET", f"/guilds/{guild_id}/welcome-screen")

    async def edit_guild_welcome_screen(
        self,
        guild_id: Snowflake,
        *,
        enabled: bool | None = None,
        welcome_channels: list[dict[str, Any]] | None = None,
        description: str | None = None,
        reason: str | None = None,
    ) -> dict[str, Any]:
        """Edit the guild welcome screen."""
        payload: dict[str, Any] = {}
        if enabled is not None:
            payload["enabled"] = enabled
        if welcome_channels is not None:
            payload["welcome_channels"] = welcome_channels
        if description is not None:
            payload["description"] = description
        return await self.request(
            "PATCH",
            f"/guilds/{guild_id}/welcome-screen",
            json=payload,
            reason=reason,
        )

    async def get_guild_onboarding(self, guild_id: Snowflake) -> dict[str, Any]:
        """Get the guild onboarding configuration."""
        return await self.request("GET", f"/guilds/{guild_id}/onboarding")

    async def get_guild_integrations(self, guild_id: Snowflake) -> list[dict[str, Any]]:
        """List all integrations in a guild."""
        return await self.request("GET", f"/guilds/{guild_id}/integrations")

    async def delete_guild_integration(
        self,
        guild_id: Snowflake,
        integration_id: Snowflake,
        *,
        reason: str | None = None,
    ) -> None:
        """Delete an integration from a guild."""
        await self.request(
            "DELETE",
            f"/guilds/{guild_id}/integrations/{integration_id}",
            reason=reason,
        )

    async def get_guild_voice_regions(self, guild_id: Snowflake) -> list[dict[str, Any]]:
        """List voice regions available for a guild."""
        return await self.request("GET", f"/guilds/{guild_id}/regions")

    #  STAGE INSTANCES

    async def create_stage_instance(
        self,
        channel_id: Snowflake,
        topic: str,
        *,
        privacy_level: int = 1,
        send_start_notification: bool = False,
        guild_scheduled_event_id: Snowflake | None = None,
        reason: str | None = None,
    ) -> dict[str, Any]:
        """Create a stage instance."""
        payload: dict[str, Any] = {
            "channel_id": str(channel_id),
            "topic": topic,
            "privacy_level": privacy_level,
            "send_start_notification": send_start_notification,
        }
        if guild_scheduled_event_id is not None:
            payload["guild_scheduled_event_id"] = str(guild_scheduled_event_id)
        return await self.request(
            "POST", "/stage-instances", json=payload, reason=reason
        )

    async def get_stage_instance(self, channel_id: Snowflake) -> dict[str, Any]:
        """Fetch an active stage instance for a channel."""
        return await self.request("GET", f"/stage-instances/{channel_id}")

    async def edit_stage_instance(
        self,
        channel_id: Snowflake,
        *,
        topic: str | None = None,
        privacy_level: int | None = None,
        reason: str | None = None,
    ) -> dict[str, Any]:
        """Edit a stage instance."""
        payload: dict[str, Any] = {}
        if topic is not None:
            payload["topic"] = topic
        if privacy_level is not None:
            payload["privacy_level"] = privacy_level
        return await self.request(
            "PATCH", f"/stage-instances/{channel_id}",
            json=payload, reason=reason,
        )

    async def delete_stage_instance(
        self, channel_id: Snowflake, *, reason: str | None = None
    ) -> None:
        """Delete a stage instance."""
        await self.request(
            "DELETE", f"/stage-instances/{channel_id}", reason=reason
        )

    #  VOICE

    async def list_voice_regions(self) -> list[dict[str, Any]]:
        """List all available voice regions."""
        return await self.request("GET", "/voice/regions")

    async def get_current_user_voice_state(
        self, guild_id: Snowflake
    ) -> dict[str, Any]:
        """Get the bot's own voice state in a guild."""
        return await self.request("GET", f"/guilds/{guild_id}/voice-states/@me")

    async def get_user_voice_state(
        self, guild_id: Snowflake, user_id: Snowflake
    ) -> dict[str, Any]:
        """Get a user's voice state in a guild."""
        return await self.request("GET", f"/guilds/{guild_id}/voice-states/{user_id}")

    async def edit_user_voice_state(
        self,
        guild_id: Snowflake,
        user_id: Snowflake,
        *,
        channel_id: Snowflake | None = None,
        suppress: bool | None = None,
    ) -> None:
        """Update a user's voice state (e.g. suppress in Stage)."""
        payload: dict[str, Any] = {}
        if channel_id is not None:
            payload["channel_id"] = str(channel_id)
        if suppress is not None:
            payload["suppress"] = suppress
        await self.request(
            "PATCH", f"/guilds/{guild_id}/voice-states/{user_id}", json=payload
        )

    # CURRENT APPLICATION

    async def get_current_application(self) -> dict[str, Any]:
        """Fetch the current application object (id, name, description, etc.)."""
        return await self.request("GET", "/applications/@me")

    async def edit_current_application(self, **kwargs: Any) -> dict[str, Any]:
        """Edit the current application. Pass any patchable fields as kwargs."""
        return await self.request("PATCH", "/applications/@me", json=kwargs)
