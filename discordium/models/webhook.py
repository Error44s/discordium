"""Discord Webhook model — full v10 coverage."""

from __future__ import annotations

import re
from enum import IntEnum
from typing import TYPE_CHECKING, Any, Self

from .snowflake import Snowflake
from .user import User

if TYPE_CHECKING:
    from ..http.rest import RESTClient
    from .channel import Channel
    from .embed import Embed
    from .file import File
    from .guild import Guild

_WEBHOOK_URL_RE = re.compile(
    r"https?://(?:ptb\.|canary\.)?discord(?:app)?\.com/api/webhooks/"
    r"(?P<id>\d+)/(?P<token>[A-Za-z0-9_-]+)"
)


class WebhookType(IntEnum):
    """Discord webhook type constants."""
    INCOMING = 1          # regular bot/user-created webhook
    CHANNEL_FOLLOWER = 2  # announcement channel follower
    APPLICATION = 3       # interaction response webhook


class Webhook:
    """Represents a Discord webhook.

    Webhooks come in three flavours: *Incoming* (created by users/bots and
    used to post messages), *Channel Follower* (created by following an
    Announcement channel), and *Application* (used for interaction responses).

    Attributes
    ----------
    id:
        Webhook Snowflake.
    type:
        :class:`WebhookType`.
    token:
        Secret token (absent for Channel Follower and Application webhooks).
    guild_id:
        Guild this webhook belongs to.
    channel_id:
        Channel this webhook posts to.
    name:
        Webhook display name.
    avatar:
        Avatar hash.
    user:
        The user who created this webhook (absent for Application type).
    application_id:
        The bot application ID for Application type webhooks.
    source_guild:
        Partial guild object for Channel Follower webhooks.
    source_channel:
        Partial channel object for Channel Follower webhooks.
    url:
        Computed webhook URL (requires *token*).
    """

    __slots__ = (
        "id", "type", "token", "guild_id", "channel_id",
        "name", "avatar", "user", "application_id",
        "source_guild", "source_channel", "_rest",
    )

    def __init__(
        self,
        *,
        id: Snowflake,
        type: int = WebhookType.INCOMING,
        token: str | None = None,
        guild_id: Snowflake | None = None,
        channel_id: Snowflake | None = None,
        name: str | None = None,
        avatar: str | None = None,
        user: User | None = None,
        application_id: Snowflake | None = None,
        source_guild: dict[str, Any] | None = None,
        source_channel: dict[str, Any] | None = None,
        rest: RESTClient | None = None,
    ) -> None:
        self.id = id
        self.type = type
        self.token = token
        self.guild_id = guild_id
        self.channel_id = channel_id
        self.name = name
        self.avatar = avatar
        self.user = user
        self.application_id = application_id
        self.source_guild = source_guild
        self.source_channel = source_channel
        self._rest = rest

    # Computed

    @property
    def url(self) -> str | None:
        if self.token:
            return f"https://discord.com/api/webhooks/{self.id}/{self.token}"
        return None

    @property
    def created_at(self):
        return self.id.created_at

    @property
    def is_incoming(self) -> bool:
        return self.type == WebhookType.INCOMING

    @property
    def is_follower(self) -> bool:
        return self.type == WebhookType.CHANNEL_FOLLOWER

    @property
    def is_application(self) -> bool:
        return self.type == WebhookType.APPLICATION

    def avatar_url(self, *, size: int = 1024, fmt: str | None = None) -> str | None:
        if self.avatar is None:
            return None
        if fmt is None:
            fmt = "gif" if self.avatar.startswith("a_") else "webp"
        return f"https://cdn.discordapp.com/webhooks/{self.id}/{self.avatar}.{fmt}?size={size}"

    # onstructors

    @classmethod
    def from_payload(cls, data: dict[str, Any], *, rest: RESTClient | None = None) -> Self:
        user = User.from_payload(data["user"]) if "user" in data else None
        return cls(
            id=Snowflake(data["id"]),
            type=data.get("type", WebhookType.INCOMING),
            token=data.get("token"),
            guild_id=Snowflake(data["guild_id"]) if data.get("guild_id") else None,
            channel_id=Snowflake(data["channel_id"]) if data.get("channel_id") else None,
            name=data.get("name"),
            avatar=data.get("avatar"),
            user=user,
            application_id=Snowflake(data["application_id"]) if data.get("application_id") else None,
            source_guild=data.get("source_guild"),
            source_channel=data.get("source_channel"),
            rest=rest,
        )

    @classmethod
    def from_url(cls, url: str, *, rest: RESTClient) -> Webhook:
        """Parse a webhook from its URL (``https://discord.com/api/webhooks/…``)."""
        match = _WEBHOOK_URL_RE.match(url)
        if not match:
            raise ValueError(f"Invalid webhook URL: {url!r}")
        return cls(
            id=Snowflake(match.group("id")),
            token=match.group("token"),
            rest=rest,
        )

    # Actions

    def _require_token(self) -> str:
        if not self.token:
            raise RuntimeError("Webhook token is required for this action")
        return self.token

    def _require_rest(self) -> RESTClient:
        if self._rest is None:
            raise RuntimeError("Webhook is not bound to a REST client")
        return self._rest

    async def send(
        self,
        content: str | None = None,
        *,
        username: str | None = None,
        avatar_url: str | None = None,
        embed: Embed | None = None,
        embeds: list[Embed] | None = None,
        components: list[Any] | None = None,
        files: list[File] | None = None,
        tts: bool = False,
        wait: bool = False,
        thread_id: Snowflake | None = None,
        thread_name: str | None = None,
        flags: int | None = None,
        allowed_mentions: dict[str, Any] | None = None,
    ) -> Any | None:
        """Execute the webhook (post a message).

        Returns the created Message if *wait* is True, else ``None``.
        """
        rest = self._require_rest()
        token = self._require_token()
        return await rest.execute_webhook(
            self.id, token,
            content=content,
            username=username,
            avatar_url=avatar_url,
            tts=tts,
            embeds=[embed] if embed else embeds,
            components=components,
            files=files,
            allowed_mentions=allowed_mentions,
            thread_id=thread_id,
            thread_name=thread_name,
            wait=wait,
            flags=flags,
        )

    async def fetch_message(self, message_id: Snowflake, *, thread_id: Snowflake | None = None) -> Any:
        """Fetch a message that was sent by this webhook."""
        rest = self._require_rest()
        token = self._require_token()
        return await rest.get_webhook_message(self.id, token, message_id, thread_id=thread_id)

    async def edit_message(
        self,
        message_id: Snowflake,
        content: str | None = None,
        *,
        embed: Embed | None = None,
        embeds: list[Embed] | None = None,
        components: list[Any] | None = None,
        files: list[File] | None = None,
        thread_id: Snowflake | None = None,
    ) -> Any:
        """Edit a message sent by this webhook."""
        rest = self._require_rest()
        token = self._require_token()
        return await rest.edit_webhook_message(
            self.id, token, message_id,
            content=content,
            embeds=[embed] if embed else embeds,
            components=components,
            files=files,
            thread_id=thread_id,
        )

    async def delete_message(
        self, message_id: Snowflake, *, thread_id: Snowflake | None = None
    ) -> None:
        """Delete a message sent by this webhook."""
        rest = self._require_rest()
        token = self._require_token()
        await rest.delete_webhook_message(self.id, token, message_id, thread_id=thread_id)

    async def delete(self, *, reason: str | None = None) -> None:
        """Delete this webhook."""
        rest = self._require_rest()
        if self.token:
            await rest.request("DELETE", f"/webhooks/{self.id}/{self.token}")
        else:
            await rest.request("DELETE", f"/webhooks/{self.id}", reason=reason)

    async def edit(
        self,
        *,
        name: str | None = None,
        channel_id: Snowflake | None = None,
        reason: str | None = None,
    ) -> Webhook:
        """Edit this webhook's name or channel."""
        rest = self._require_rest()
        return await rest.edit_webhook(self.id, name=name, channel_id=channel_id, reason=reason)

    def __repr__(self) -> str:
        return f"Webhook(id={self.id}, type={self.type!r}, name={self.name!r})"
