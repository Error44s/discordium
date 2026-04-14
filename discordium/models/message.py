"""Discord Message model — fully fleshed out.

Covers the complete v10 Message object including attachments, reactions,
stickers, polls, role-subscription data, message references, and all
computed helpers.
"""

from __future__ import annotations

from enum import IntEnum, IntFlag
from typing import TYPE_CHECKING, Any, Self

from .base import Model
from .embed import Embed
from .snowflake import Snowflake
from .user import User

if TYPE_CHECKING:
    from ..http.rest import RESTClient

# Enums

class MessageType(IntEnum):
    DEFAULT = 0
    RECIPIENT_ADD = 1
    RECIPIENT_REMOVE = 2
    CALL = 3
    CHANNEL_NAME_CHANGE = 4
    CHANNEL_ICON_CHANGE = 5
    CHANNEL_PINNED_MESSAGE = 6
    USER_JOIN = 7
    GUILD_BOOST = 8
    GUILD_BOOST_TIER_1 = 9
    GUILD_BOOST_TIER_2 = 10
    GUILD_BOOST_TIER_3 = 11
    CHANNEL_FOLLOW_ADD = 12
    GUILD_DISCOVERY_DISQUALIFIED = 14
    GUILD_DISCOVERY_REQUALIFIED = 15
    GUILD_DISCOVERY_GRACE_PERIOD_INITIAL_WARNING = 16
    GUILD_DISCOVERY_GRACE_PERIOD_FINAL_WARNING = 17
    THREAD_CREATED = 18
    REPLY = 19
    CHAT_INPUT_COMMAND = 20
    THREAD_STARTER_MESSAGE = 21
    GUILD_INVITE_REMINDER = 22
    CONTEXT_MENU_COMMAND = 23
    AUTO_MODERATION_ACTION = 24
    ROLE_SUBSCRIPTION_PURCHASE = 25
    INTERACTION_PREMIUM_UPSELL = 26
    STAGE_START = 27
    STAGE_END = 28
    STAGE_SPEAKER = 29
    STAGE_TOPIC = 31
    GUILD_APPLICATION_PREMIUM_SUBSCRIPTION = 32
    GUILD_INCIDENT_ALERT_MODE_ENABLED = 36
    GUILD_INCIDENT_ALERT_MODE_DISABLED = 37
    GUILD_INCIDENT_REPORT_RAID = 38
    GUILD_INCIDENT_REPORT_FALSE_ALARM = 39
    PURCHASE_NOTIFICATION = 44
    POLL_RESULT = 46


class MessageFlags(IntFlag):
    CROSSPOSTED = 1 << 0
    IS_CROSSPOST = 1 << 1
    SUPPRESS_EMBEDS = 1 << 2
    SOURCE_MESSAGE_DELETED = 1 << 3
    URGENT = 1 << 4
    HAS_THREAD = 1 << 5
    EPHEMERAL = 1 << 6
    LOADING = 1 << 7
    FAILED_TO_MENTION_SOME_ROLES_IN_THREAD = 1 << 8
    SUPPRESS_NOTIFICATIONS = 1 << 12
    IS_VOICE_MESSAGE = 1 << 13


class AttachmentFlags(IntFlag):
    """Attachment flags bitfield."""

    IS_REMIX = 1 << 2

# Sub-models

class Attachment(Model):
    """A file attached to a Discord message."""

    id: Snowflake
    filename: str
    title: str | None = None
    description: str | None = None
    content_type: str | None = None
    size: int = 0
    url: str = ""
    proxy_url: str = ""
    height: int | None = None
    width: int | None = None
    ephemeral: bool = False
    duration_secs: float | None = None
    waveform: str | None = None
    flags: AttachmentFlags = AttachmentFlags(0)

    @property
    def is_image(self) -> bool:
        return (self.content_type or "").startswith("image/")

    @property
    def is_video(self) -> bool:
        return (self.content_type or "").startswith("video/")

    @property
    def is_audio(self) -> bool:
        return (self.content_type or "").startswith("audio/")

    @property
    def is_voice_message(self) -> bool:
        return self.duration_secs is not None

    @property
    def size_kb(self) -> float:
        return self.size / 1024

    @property
    def size_mb(self) -> float:
        return self.size / (1024 * 1024)

    @property
    def extension(self) -> str:
        return "." + self.filename.rsplit(".", 1)[-1].lower() if "." in self.filename else ""

    @property
    def spoiler(self) -> bool:
        return self.filename.startswith("SPOILER_")

    @classmethod
    def from_payload(cls, data: dict[str, Any]) -> Self:
        return cls(
            id=Snowflake(data["id"]),
            filename=data["filename"],
            title=data.get("title"),
            description=data.get("description"),
            content_type=data.get("content_type"),
            size=data.get("size", 0),
            url=data.get("url", ""),
            proxy_url=data.get("proxy_url", ""),
            height=data.get("height"),
            width=data.get("width"),
            ephemeral=data.get("ephemeral", False),
            duration_secs=data.get("duration_secs"),
            waveform=data.get("waveform"),
            flags=AttachmentFlags(data.get("flags", 0)),
        )


class Reaction(Model):
    """A reaction on a message."""

    count: int = 0
    count_normal: int = 0
    count_burst: int = 0
    me: bool = False
    me_burst: bool = False
    emoji_id: Snowflake | None = None
    emoji_name: str | None = None
    emoji_animated: bool = False
    burst_colors: list[str] | None = None

    @property
    def is_custom(self) -> bool:
        return self.emoji_id is not None

    @property
    def emoji_str(self) -> str:
        """Reaction string usable in API calls."""
        if self.emoji_id:
            return f"{self.emoji_name}:{self.emoji_id}"
        return self.emoji_name or ""

    @property
    def emoji_mention(self) -> str:
        """Formatted emoji for use in message content."""
        if self.emoji_id:
            prefix = "a" if self.emoji_animated else ""
            return f"<{prefix}:{self.emoji_name}:{self.emoji_id}>"
        return self.emoji_name or ""

    @classmethod
    def from_payload(cls, data: dict[str, Any]) -> Self:
        emoji = data.get("emoji", {})
        count_details = data.get("count_details", {})
        return cls(
            count=data.get("count", 0),
            count_normal=count_details.get("normal", data.get("count", 0)),
            count_burst=count_details.get("burst", 0),
            me=data.get("me", False),
            me_burst=data.get("me_burst", False),
            emoji_id=Snowflake(emoji["id"]) if emoji.get("id") else None,
            emoji_name=emoji.get("name"),
            emoji_animated=emoji.get("animated", False),
            burst_colors=data.get("burst_colors"),
        )


class MessageReference(Model):
    """A reference to another message (reply / crosspost / forward)."""

    type: int = 0
    message_id: Snowflake | None = None
    channel_id: Snowflake | None = None
    guild_id: Snowflake | None = None
    fail_if_not_exists: bool = True

    @classmethod
    def from_payload(cls, data: dict[str, Any]) -> Self:
        return cls(
            type=data.get("type", 0),
            message_id=Snowflake(data["message_id"]) if data.get("message_id") else None,
            channel_id=Snowflake(data["channel_id"]) if data.get("channel_id") else None,
            guild_id=Snowflake(data["guild_id"]) if data.get("guild_id") else None,
            fail_if_not_exists=data.get("fail_if_not_exists", True),
        )

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {"fail_if_not_exists": self.fail_if_not_exists, "type": self.type}
        if self.message_id:
            d["message_id"] = str(self.message_id)
        if self.channel_id:
            d["channel_id"] = str(self.channel_id)
        if self.guild_id:
            d["guild_id"] = str(self.guild_id)
        return d


class StickerItem(Model):
    """Partial sticker attached to a message (1=PNG,2=APNG,3=Lottie,4=GIF)."""

    id: Snowflake
    name: str
    format_type: int = 1

    @property
    def url(self) -> str:
        ext = {1: "png", 2: "apng", 3: "json", 4: "gif"}.get(self.format_type, "png")
        return f"https://media.discordapp.net/stickers/{self.id}.{ext}"

    @property
    def is_animated(self) -> bool:
        return self.format_type in (2, 4)

    @classmethod
    def from_payload(cls, data: dict[str, Any]) -> Self:
        return cls(
            id=Snowflake(data["id"]),
            name=data["name"],
            format_type=data.get("format_type", 1),
        )


class MessageActivity(Model):
    """Rich Presence activity embedded in a message (1=JOIN,2=SPECTATE,3=LISTEN,5=JOIN_REQUEST)."""

    type: int
    party_id: str | None = None

    @classmethod
    def from_payload(cls, data: dict[str, Any]) -> Self:
        return cls(type=data["type"], party_id=data.get("party_id"))


class RoleSubscriptionData(Model):
    """Data about a role-subscription purchase message."""

    role_subscription_listing_id: Snowflake
    tier_name: str
    total_months_subscribed: int = 0
    is_renewal: bool = False

    @classmethod
    def from_payload(cls, data: dict[str, Any]) -> Self:
        return cls(
            role_subscription_listing_id=Snowflake(data["role_subscription_listing_id"]),
            tier_name=data["tier_name"],
            total_months_subscribed=data.get("total_months_subscribed", 0),
            is_renewal=data.get("is_renewal", False),
        )


class PollAnswer(Model):
    """A single answer option in a Discord poll."""

    answer_id: int
    text: str | None = None
    emoji_id: Snowflake | None = None
    emoji_name: str | None = None
    emoji_animated: bool = False

    @classmethod
    def from_payload(cls, data: dict[str, Any]) -> Self:
        media = data.get("poll_media", {})
        emoji = media.get("emoji") or {}
        return cls(
            answer_id=data["answer_id"],
            text=media.get("text"),
            emoji_id=Snowflake(emoji["id"]) if emoji.get("id") else None,
            emoji_name=emoji.get("name"),
            emoji_animated=emoji.get("animated", False),
        )


class PollResult(Model):
    """Vote count for a single poll answer."""

    answer_id: int
    count: int = 0
    me_voted: bool = False

    @classmethod
    def from_payload(cls, data: dict[str, Any]) -> Self:
        return cls(
            answer_id=data["answer_id"],
            count=data.get("count", 0),
            me_voted=data.get("me_voted", False),
        )


class Poll(Model):
    """A Discord poll attached to a message."""

    question: str
    answers: list[PollAnswer]
    expiry: str | None = None
    allow_multiselect: bool = False
    layout_type: int = 1
    results: list[PollResult] | None = None

    @property
    def is_finalised(self) -> bool:
        return self.results is not None

    @property
    def total_votes(self) -> int:
        if not self.results:
            return 0
        return sum(r.count for r in self.results)

    def winner(self) -> PollResult | None:
        if not self.results:
            return None
        return max(self.results, key=lambda r: r.count)

    @classmethod
    def from_payload(cls, data: dict[str, Any]) -> Self:
        question_media = data.get("question", {})
        answers = [PollAnswer.from_payload(a) for a in data.get("answers", [])]
        results_data = data.get("results", {})
        results: list[PollResult] | None = None
        if results_data:
            results = [PollResult.from_payload(r) for r in results_data.get("answer_counts", [])]
        return cls(
            question=question_media.get("text", ""),
            answers=answers,
            expiry=data.get("expiry"),
            allow_multiselect=data.get("allow_multiselect", False),
            layout_type=data.get("layout_type", 1),
            results=results,
        )


class PartialMessage(Model):
    """Minimal message — only guaranteed fields for cross-channel references."""

    id: Snowflake
    channel_id: Snowflake
    guild_id: Snowflake | None = None

    @classmethod
    def from_payload(cls, data: dict[str, Any]) -> Self:
        return cls(
            id=Snowflake(data["id"]),
            channel_id=Snowflake(data["channel_id"]),
            guild_id=Snowflake(data["guild_id"]) if data.get("guild_id") else None,
        )

# Full Message

class Message(Model):
    """Represents a complete Discord message (API v10)."""

    id: Snowflake
    channel_id: Snowflake
    guild_id: Snowflake | None = None
    author: User | None = None
    webhook_id: Snowflake | None = None
    type: int = 0
    content: str = ""
    timestamp: str | None = None
    edited_timestamp: str | None = None
    tts: bool = False
    mention_everyone: bool = False
    mentions: list[User] | None = None
    mention_roles: list[Snowflake] | None = None
    attachments: list[Attachment] | None = None
    embeds: list[Embed] | None = None
    reactions: list[Reaction] | None = None
    pinned: bool = False
    nonce: str | int | None = None
    application_id: Snowflake | None = None
    flags: int = 0
    referenced_message: Message | None = None
    message_reference: MessageReference | None = None
    sticker_items: list[StickerItem] | None = None
    activity: MessageActivity | None = None
    role_subscription_data: RoleSubscriptionData | None = None
    poll: Poll | None = None
    interaction_metadata: dict[str, Any] | None = None
    position: int | None = None

    _rest: RESTClient | None = None  # type: ignore[assignment]

    # Computed

    @property
    def message_type(self) -> MessageType | int:
        try:
            return MessageType(self.type)
        except ValueError:
            return self.type

    @property
    def message_flags(self) -> MessageFlags:
        return MessageFlags(self.flags)

    @property
    def is_reply(self) -> bool:
        return self.message_reference is not None and self.message_reference.message_id is not None

    @property
    def is_system(self) -> bool:
        return self.type not in (0, 19, 20, 23, 21)

    @property
    def is_webhook(self) -> bool:
        return self.webhook_id is not None

    @property
    def is_ephemeral(self) -> bool:
        return bool(self.flags & MessageFlags.EPHEMERAL)

    @property
    def is_crosspost(self) -> bool:
        return bool(self.flags & MessageFlags.IS_CROSSPOST)

    @property
    def has_thread(self) -> bool:
        return bool(self.flags & MessageFlags.HAS_THREAD)

    @property
    def jump_url(self) -> str:
        guild_part = str(self.guild_id) if self.guild_id else "@me"
        return f"https://discord.com/channels/{guild_part}/{self.channel_id}/{self.id}"

    @property
    def created_at(self):
        return self.id.created_at

    @property
    def edited_at(self):
        if self.edited_timestamp is None:
            return None
        from datetime import datetime
        return datetime.fromisoformat(self.edited_timestamp.replace("Z", "+00:00"))

    @property
    def image_attachments(self) -> list[Attachment]:
        return [a for a in (self.attachments or []) if a.is_image]

    @property
    def video_attachments(self) -> list[Attachment]:
        return [a for a in (self.attachments or []) if a.is_video]

    # Helpers

    def get_reaction(self, emoji: str) -> Reaction | None:
        if not self.reactions:
            return None
        for r in self.reactions:
            if r.emoji_str == emoji or r.emoji_name == emoji:
                return r
        return None

    def mentions_user(self, user_id: int | Snowflake) -> bool:
        if not self.mentions:
            return False
        target = int(user_id)
        return any(int(u.id) == target for u in self.mentions)

    def mentions_role(self, role_id: int | Snowflake) -> bool:
        if not self.mention_roles:
            return False
        target = int(role_id)
        return any(int(r) == target for r in self.mention_roles)

    # REST shortcuts

    async def reply(
        self,
        content: str | None = None,
        *,
        embed: Embed | None = None,
        embeds: list[Embed] | None = None,
        mention_author: bool = True,
        tts: bool = False,
    ) -> Message:
        if self._rest is None:
            raise RuntimeError("Message is not bound to a REST client")
        return await self._rest.send_message(
            channel_id=self.channel_id,
            content=content,
            embed=embed,
            embeds=embeds,
            message_reference=self.id,
            mention_author=mention_author,
            tts=tts,
        )

    async def react(self, emoji: str) -> None:
        if self._rest is None:
            raise RuntimeError("Message is not bound to a REST client")
        await self._rest.add_reaction(self.channel_id, self.id, emoji)

    async def remove_reaction(self, emoji: str, user_id: Snowflake | None = None) -> None:
        if self._rest is None:
            raise RuntimeError("Message is not bound to a REST client")
        await self._rest.remove_reaction(self.channel_id, self.id, emoji, user_id)

    async def clear_reaction(self, emoji: str) -> None:
        if self._rest is None:
            raise RuntimeError("Message is not bound to a REST client")
        await self._rest.clear_reactions(self.channel_id, self.id, emoji)

    async def clear_reactions(self) -> None:
        if self._rest is None:
            raise RuntimeError("Message is not bound to a REST client")
        await self._rest.clear_reactions(self.channel_id, self.id)

    async def edit(
        self,
        content: str | None = None,
        *,
        embed: Embed | None = None,
        embeds: list[Embed] | None = None,
        components: list[Any] | None = None,
    ) -> Message:
        if self._rest is None:
            raise RuntimeError("Message is not bound to a REST client")
        return await self._rest.edit_message(
            self.channel_id, self.id,
            content=content, embed=embed, embeds=embeds, components=components,
        )

    async def delete(self) -> None:
        if self._rest is None:
            raise RuntimeError("Message is not bound to a REST client")
        await self._rest.delete_message(self.channel_id, self.id)

    async def pin(self) -> None:
        if self._rest is None:
            raise RuntimeError("Message is not bound to a REST client")
        await self._rest.pin_message(self.channel_id, self.id)

    async def unpin(self) -> None:
        if self._rest is None:
            raise RuntimeError("Message is not bound to a REST client")
        await self._rest.unpin_message(self.channel_id, self.id)

    async def crosspost(self) -> Message:
        if self._rest is None:
            raise RuntimeError("Message is not bound to a REST client")
        return await self._rest.crosspost_message(self.channel_id, self.id)

    @classmethod
    def from_payload(cls, data: dict[str, Any], *, rest: RESTClient | None = None) -> Self:
        author = User.from_payload(data["author"]) if "author" in data else None
        embeds = [Embed.from_payload(e) for e in data["embeds"]] if data.get("embeds") else None
        mentions = [User.from_payload(u) for u in data["mentions"]] if data.get("mentions") else None
        mention_roles = [Snowflake(r) for r in data["mention_roles"]] if data.get("mention_roles") else None
        attachments = [Attachment.from_payload(a) for a in data["attachments"]] if data.get("attachments") else None
        reactions = [Reaction.from_payload(r) for r in data["reactions"]] if data.get("reactions") else None
        message_reference = MessageReference.from_payload(data["message_reference"]) if "message_reference" in data else None
        referenced_message = Message.from_payload(data["referenced_message"]) if data.get("referenced_message") else None
        sticker_items = [StickerItem.from_payload(s) for s in data["sticker_items"]] if data.get("sticker_items") else None
        activity = MessageActivity.from_payload(data["activity"]) if "activity" in data else None
        role_subscription_data = RoleSubscriptionData.from_payload(data["role_subscription_data"]) if "role_subscription_data" in data else None
        poll = Poll.from_payload(data["poll"]) if "poll" in data else None

        msg = cls(
            id=Snowflake(data["id"]),
            channel_id=Snowflake(data["channel_id"]),
            guild_id=Snowflake(data["guild_id"]) if data.get("guild_id") else None,
            author=author,
            webhook_id=Snowflake(data["webhook_id"]) if data.get("webhook_id") else None,
            type=data.get("type", 0),
            content=data.get("content", ""),
            timestamp=data.get("timestamp"),
            edited_timestamp=data.get("edited_timestamp"),
            tts=data.get("tts", False),
            mention_everyone=data.get("mention_everyone", False),
            mentions=mentions,
            mention_roles=mention_roles,
            attachments=attachments,
            embeds=embeds,
            reactions=reactions,
            pinned=data.get("pinned", False),
            nonce=data.get("nonce"),
            application_id=Snowflake(data["application_id"]) if data.get("application_id") else None,
            flags=data.get("flags", 0),
            referenced_message=referenced_message,
            message_reference=message_reference,
            sticker_items=sticker_items,
            activity=activity,
            role_subscription_data=role_subscription_data,
            poll=poll,
            interaction_metadata=data.get("interaction_metadata"),
            position=data.get("position"),
        )
        if rest is not None:
            object.__setattr__(msg, "_rest", rest)
        return msg

    def __repr__(self) -> str:
        return (
            f"Message(id={self.id}, channel={self.channel_id}, "
            f"author={self.author!r}, content={self.content[:50]!r})"
        )
