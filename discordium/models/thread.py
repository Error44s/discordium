"""Discord Thread model — full v10 coverage."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Self

from .base import Model
from .enums import ChannelType
from .snowflake import Snowflake


class ThreadMetadata(Model):
    """Metadata specific to thread channels.

    Attributes
    ----------
    archived:
        Whether the thread is archived.
    auto_archive_duration:
        Minutes of inactivity until auto-archive (60, 1440, 4320, 10080).
    archive_timestamp:
        ISO8601 timestamp when the thread was archived (or last unarchived).
    locked:
        Whether only moderators can unarchive this thread.
    invitable:
        Whether non-moderators can add other members (private threads only).
    create_timestamp:
        ISO8601 timestamp when the thread was created (only present for
        threads created after 2022-01-09).
    """

    archived: bool = False
    auto_archive_duration: int = 1440
    archive_timestamp: str | None = None
    locked: bool = False
    invitable: bool | None = None
    create_timestamp: str | None = None

    @property
    def archive_timestamp_dt(self) -> datetime | None:
        if self.archive_timestamp is None:
            return None
        try:
            return datetime.fromisoformat(self.archive_timestamp.replace("Z", "+00:00"))
        except ValueError:
            return None

    @property
    def create_timestamp_dt(self) -> datetime | None:
        if self.create_timestamp is None:
            return None
        try:
            return datetime.fromisoformat(self.create_timestamp.replace("Z", "+00:00"))
        except ValueError:
            return None

    @classmethod
    def from_payload(cls, data: dict[str, Any]) -> Self:
        return cls(
            archived=data.get("archived", False),
            auto_archive_duration=data.get("auto_archive_duration", 1440),
            archive_timestamp=data.get("archive_timestamp"),
            locked=data.get("locked", False),
            invitable=data.get("invitable"),
            create_timestamp=data.get("create_timestamp"),
        )


class ThreadMember(Model):
    """Represents a single member's presence in a thread.

    Attributes
    ----------
    id:
        Thread channel Snowflake (``None`` in ``LIST_THREAD_MEMBERS`` without
        the ``with_member`` param).
    user_id:
        User Snowflake (``None`` in some bot-created contexts).
    join_timestamp:
        ISO8601 timestamp of when the user joined the thread.
    flags:
        User-thread settings flags.
    member:
        Full guild Member object (only present when ``with_member=True``
        is passed to the list endpoint).
    """

    id: Snowflake | None = None
    user_id: Snowflake | None = None
    join_timestamp: str | None = None
    flags: int = 0
    member: Any | None = None  # Guild Member — imported lazily to avoid circular

    @property
    def join_timestamp_dt(self) -> datetime | None:
        if self.join_timestamp is None:
            return None
        try:
            return datetime.fromisoformat(self.join_timestamp.replace("Z", "+00:00"))
        except ValueError:
            return None

    @classmethod
    def from_payload(cls, data: dict[str, Any]) -> Self:
        member = None
        if "member" in data:
            from .member import Member
            member = Member.from_payload(data["member"])
        return cls(
            id=Snowflake(data["id"]) if "id" in data else None,
            user_id=Snowflake(data["user_id"]) if "user_id" in data else None,
            join_timestamp=data.get("join_timestamp"),
            flags=data.get("flags", 0),
            member=member,
        )

    def __repr__(self) -> str:
        return f"ThreadMember(user_id={self.user_id}, thread_id={self.id})"


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


class Thread(Model):
    """Represents a Discord thread channel.

    Threads are a special kind of channel that lives inside a parent text,
    announcement, or forum channel.

    Attributes
    ----------
    id:
        Thread Snowflake.
    type:
        :class:`~discordium.models.enums.ChannelType`
        (PUBLIC_THREAD, PRIVATE_THREAD, ANNOUNCEMENT_THREAD).
    guild_id:
        Guild this thread belongs to.
    parent_id:
        Parent channel the thread was started in.
    owner_id:
        User who started the thread.
    name:
        Thread name (up to 100 characters).
    rate_limit_per_user:
        Slowmode in seconds.
    message_count:
        Approximate message count (capped at 50 by Discord; use
        ``total_message_sent`` for the real count).
    member_count:
        Approximate member count (capped at 50 by Discord).
    total_message_sent:
        Actual total message count (not capped).
    metadata:
        :class:`ThreadMetadata` with archive/lock state.
    member:
        The current user's :class:`ThreadMember` record (present in
        ``get_member`` / ``join`` responses).
    applied_tags:
        List of tag Snowflakes applied to this forum post.
    flags:
        Channel flag bitmask.
    """

    id: Snowflake
    type: ChannelType
    guild_id: Snowflake | None = None
    parent_id: Snowflake | None = None
    owner_id: Snowflake | None = None
    name: str | None = None
    rate_limit_per_user: int = 0
    message_count: int = 0
    member_count: int = 0
    total_message_sent: int = 0
    metadata: ThreadMetadata | None = None
    member: ThreadMember | None = None
    applied_tags: list[Snowflake] | None = None
    flags: int = 0

    # Computed

    @property
    def is_archived(self) -> bool:
        return self.metadata.archived if self.metadata else False

    @property
    def is_locked(self) -> bool:
        return self.metadata.locked if self.metadata else False

    @property
    def is_private(self) -> bool:
        return self.type == ChannelType.PRIVATE_THREAD

    @property
    def is_public(self) -> bool:
        return self.type == ChannelType.PUBLIC_THREAD

    @property
    def is_announcement_thread(self) -> bool:
        return self.type == ChannelType.ANNOUNCEMENT_THREAD

    @property
    def auto_archive_duration(self) -> int | None:
        return self.metadata.auto_archive_duration if self.metadata else None

    @property
    def created_at(self):
        return self.id.created_at

    @property
    def mention(self) -> str:
        return f"<#{self.id}>"

    @property
    def jump_url(self) -> str:
        guild_part = str(self.guild_id) if self.guild_id else "@me"
        return f"https://discord.com/channels/{guild_part}/{self.id}"

    def has_tag(self, tag_id: int | Snowflake) -> bool:
        """Check if this forum post has a specific tag applied."""
        if not self.applied_tags:
            return False
        tid = int(tag_id)
        return any(int(t) == tid for t in self.applied_tags)

    # Construction

    @classmethod
    def from_payload(cls, data: dict[str, Any]) -> Self:
        metadata = (
            ThreadMetadata.from_payload(data["thread_metadata"])
            if "thread_metadata" in data else None
        )
        member = (
            ThreadMember.from_payload(data["member"])
            if "member" in data else None
        )
        applied_tags = (
            [Snowflake(t) for t in data["applied_tags"]]
            if "applied_tags" in data else None
        )
        return cls(
            id=Snowflake(data["id"]),
            type=ChannelType(data["type"]),
            guild_id=Snowflake(data["guild_id"]) if data.get("guild_id") else None,
            parent_id=Snowflake(data["parent_id"]) if data.get("parent_id") else None,
            owner_id=Snowflake(data["owner_id"]) if data.get("owner_id") else None,
            name=data.get("name"),
            rate_limit_per_user=data.get("rate_limit_per_user", 0),
            message_count=data.get("message_count", 0),
            member_count=data.get("member_count", 0),
            total_message_sent=data.get("total_message_sent", 0),
            metadata=metadata,
            member=member,
            applied_tags=applied_tags,
            flags=data.get("flags", 0),
        )

    def __repr__(self) -> str:
        return (
            f"Thread(id={self.id}, name={self.name!r}, "
            f"archived={self.is_archived}, type={self.type.name})"
        )
