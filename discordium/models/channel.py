"""Discord Channel model - full v10 coverage."""

from __future__ import annotations

from typing import Any, Self

from .base import Model
from .enums import ChannelType
from .permissions import PermissionOverwrite
from .snowflake import Snowflake


class ChannelFlags:
    """Channel flag constants (used as a plain int bitmask)."""
    PINNED = 1 << 1                  # thread pinned in forum
    REQUIRE_TAG = 1 << 4             # forum: posts must have a tag
    HIDE_MEDIA_DOWNLOAD_OPTIONS = 1 << 15


class DefaultReactionEmoji(Model):
    """Default reaction for forum posts."""

    emoji_id: Snowflake | None = None
    emoji_name: str | None = None

    @classmethod
    def from_payload(cls, data: dict[str, Any]) -> Self:
        return cls(
            emoji_id=Snowflake(data["emoji_id"]) if data.get("emoji_id") else None,
            emoji_name=data.get("emoji_name"),
        )

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {}
        if self.emoji_id:
            d["emoji_id"] = str(self.emoji_id)
        if self.emoji_name:
            d["emoji_name"] = self.emoji_name
        return d


class ForumTag(Model):
    """A tag available in a forum or media channel."""

    id: Snowflake
    name: str
    moderated: bool = False
    emoji_id: Snowflake | None = None
    emoji_name: str | None = None

    @property
    def emoji_str(self) -> str:
        if self.emoji_id:
            return f"{self.emoji_name}:{self.emoji_id}"
        return self.emoji_name or ""

    @classmethod
    def from_payload(cls, data: dict[str, Any]) -> Self:
        return cls(
            id=Snowflake(data["id"]),
            name=data["name"],
            moderated=data.get("moderated", False),
            emoji_id=Snowflake(data["emoji_id"]) if data.get("emoji_id") else None,
            emoji_name=data.get("emoji_name"),
        )

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {"id": str(self.id), "name": self.name, "moderated": self.moderated}
        if self.emoji_id:
            d["emoji_id"] = str(self.emoji_id)
        if self.emoji_name:
            d["emoji_name"] = self.emoji_name
        return d


class Channel(Model):
    """Represents a Discord channel (text, voice, category, forum, DM, thread…).

    All channel types are normalised into this single model. Fields that only
    apply to certain types default to ``None`` or a safe fallback so code can
    always access them without a ``hasattr`` check.

    Attributes
    ----------
    id:
        Channel Snowflake.
    type:
        :class:`~discordium.models.enums.ChannelType`.
    guild_id:
        Guild this channel belongs to (``None`` for DMs).
    name:
        Channel name (``None`` for DMs).
    topic:
        Channel topic / description.
    nsfw:
        Whether the channel is age-restricted.
    position:
        Position in the guild's channel list.
    parent_id:
        Parent category ID (or parent channel ID for threads).
    rate_limit_per_user:
        Slowmode delay in seconds.
    bitrate:
        Voice bitrate in bits per second.
    user_limit:
        Max users in a voice channel (0 = unlimited).
    rtc_region:
        Voice region override (``None`` = automatic).
    video_quality_mode:
        1 = auto, 2 = full (720p).
    default_auto_archive_duration:
        Default thread auto-archive in minutes for threads created here.
    last_message_id:
        ID of the most recent message (may be stale).
    last_pin_timestamp:
        ISO8601 timestamp of the most recent pin.
    icon:
        Icon hash for group DMs.
    owner_id:
        Owner of a group DM or thread.
    permissions:
        Computed permission string for the invoking user (interaction only).
    flags:
        Channel flag bitmask (see :class:`ChannelFlags`).
    permission_overwrites:
        List of explicit permission overwrites.
    available_tags:
        Forum/media channel tag list.
    default_reaction_emoji:
        Default reaction for forum posts.
    default_thread_rate_limit_per_user:
        Default slowmode for threads created in this channel.
    default_sort_order:
        Forum sort order (0 = latest activity, 1 = creation date).
    default_forum_layout:
        Forum display type (0 = not set, 1 = list, 2 = gallery).
    """

    id: Snowflake
    type: ChannelType
    guild_id: Snowflake | None = None
    name: str | None = None
    topic: str | None = None
    nsfw: bool = False
    position: int | None = None
    parent_id: Snowflake | None = None
    rate_limit_per_user: int = 0
    bitrate: int | None = None
    user_limit: int | None = None
    rtc_region: str | None = None
    video_quality_mode: int | None = None
    default_auto_archive_duration: int | None = None
    last_message_id: Snowflake | None = None
    last_pin_timestamp: str | None = None
    icon: str | None = None
    owner_id: Snowflake | None = None
    permissions: str | None = None
    flags: int = 0
    permission_overwrites: list[PermissionOverwrite] | None = None
    available_tags: list[ForumTag] | None = None
    default_reaction_emoji: DefaultReactionEmoji | None = None
    default_thread_rate_limit_per_user: int = 0
    default_sort_order: int | None = None
    default_forum_layout: int | None = None

    # Type checks

    @property
    def is_text(self) -> bool:
        return self.type in (
            ChannelType.GUILD_TEXT,
            ChannelType.GUILD_ANNOUNCEMENT,
            ChannelType.PUBLIC_THREAD,
            ChannelType.PRIVATE_THREAD,
            ChannelType.ANNOUNCEMENT_THREAD,
        )

    @property
    def is_voice(self) -> bool:
        return self.type in (ChannelType.GUILD_VOICE, ChannelType.GUILD_STAGE_VOICE)

    @property
    def is_category(self) -> bool:
        return self.type == ChannelType.GUILD_CATEGORY

    @property
    def is_dm(self) -> bool:
        return self.type in (ChannelType.DM, ChannelType.GROUP_DM)

    @property
    def is_thread(self) -> bool:
        return self.type in (
            ChannelType.PUBLIC_THREAD,
            ChannelType.PRIVATE_THREAD,
            ChannelType.ANNOUNCEMENT_THREAD,
        )

    @property
    def is_forum(self) -> bool:
        return self.type in (ChannelType.GUILD_FORUM, ChannelType.GUILD_MEDIA)

    @property
    def is_announcement(self) -> bool:
        return self.type == ChannelType.GUILD_ANNOUNCEMENT

    @property
    def is_stage(self) -> bool:
        return self.type == ChannelType.GUILD_STAGE_VOICE

    # Computed

    @property
    def mention(self) -> str:
        return f"<#{self.id}>"

    @property
    def created_at(self):
        return self.id.created_at

    @property
    def jump_url(self) -> str:
        guild_part = str(self.guild_id) if self.guild_id else "@me"
        return f"https://discord.com/channels/{guild_part}/{self.id}"

    @property
    def is_nsfw(self) -> bool:
        """Alias for :attr:`nsfw` for readability."""
        return self.nsfw

    @property
    def slowmode_delay(self) -> int:
        """Alias for :attr:`rate_limit_per_user`."""
        return self.rate_limit_per_user

    def get_overwrite_for(self, target_id: int | Snowflake) -> PermissionOverwrite | None:
        """Return the permission overwrite for a specific role or user ID."""
        if not self.permission_overwrites:
            return None
        tid = int(target_id)
        for ow in self.permission_overwrites:
            if ow.id == tid:
                return ow
        return None

    def get_tag(self, name: str) -> ForumTag | None:
        """Find an available forum tag by name (case-insensitive)."""
        if not self.available_tags:
            return None
        name_lower = name.lower()
        for tag in self.available_tags:
            if tag.name.lower() == name_lower:
                return tag
        return None

    @classmethod
    def from_payload(cls, data: dict[str, Any]) -> Self:
        overwrites = (
            [PermissionOverwrite.from_payload(o) for o in data["permission_overwrites"]]
            if "permission_overwrites" in data else None
        )
        available_tags = (
            [ForumTag.from_payload(t) for t in data["available_tags"]]
            if "available_tags" in data else None
        )
        default_reaction = (
            DefaultReactionEmoji.from_payload(data["default_reaction_emoji"])
            if data.get("default_reaction_emoji") else None
        )
        return cls(
            id=Snowflake(data["id"]),
            type=ChannelType(data["type"]),
            guild_id=Snowflake(data["guild_id"]) if data.get("guild_id") else None,
            name=data.get("name"),
            topic=data.get("topic"),
            nsfw=data.get("nsfw", False),
            position=data.get("position"),
            parent_id=Snowflake(data["parent_id"]) if data.get("parent_id") else None,
            rate_limit_per_user=data.get("rate_limit_per_user", 0),
            bitrate=data.get("bitrate"),
            user_limit=data.get("user_limit"),
            rtc_region=data.get("rtc_region"),
            video_quality_mode=data.get("video_quality_mode"),
            default_auto_archive_duration=data.get("default_auto_archive_duration"),
            last_message_id=Snowflake(data["last_message_id"]) if data.get("last_message_id") else None,
            last_pin_timestamp=data.get("last_pin_timestamp"),
            icon=data.get("icon"),
            owner_id=Snowflake(data["owner_id"]) if data.get("owner_id") else None,
            permissions=data.get("permissions"),
            flags=data.get("flags", 0),
            permission_overwrites=overwrites,
            available_tags=available_tags,
            default_reaction_emoji=default_reaction,
            default_thread_rate_limit_per_user=data.get("default_thread_rate_limit_per_user", 0),
            default_sort_order=data.get("default_sort_order"),
            default_forum_layout=data.get("default_forum_layout"),
        )

    def __repr__(self) -> str:
        return f"Channel(id={self.id}, type={self.type.name}, name={self.name!r})"
