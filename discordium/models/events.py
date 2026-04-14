"""Typed gateway event models.

Every gateway dispatch becomes a proper typed object — no more ``data: dict``.
The client's event dispatcher automatically converts raw payloads into these
event classes before handing them to user handlers::

    @bot.on_event("message_create")
    async def on_message(event: MessageCreateEvent) -> None:
        # event.message is a fully typed Message object
        if event.message.content == "!ping":
            await event.message.reply("Pong!")

    @bot.on_event("ready")
    async def on_ready(event: ReadyEvent) -> None:
        print(f"Logged in as {event.user.display_name}")
        print(f"Connected to {len(event.guilds)} guilds")
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from .channel import Channel
from .enums import ChannelType
from .guild import Guild
from .member import Member
from .message import Message
from .role import Role
from .snowflake import Snowflake
from .thread import Thread
from .user import User

if TYPE_CHECKING:
    from ..http.rest import RESTClient

#  Base Event

@dataclass(slots=True)
class GatewayEvent:
    """Base class for all gateway events.

    Every event carries a reference to the REST client so handlers
    can perform API calls without importing anything extra.
    """

    raw: dict[str, Any] = field(repr=False)

    @classmethod
    def from_payload(cls, data: dict[str, Any], *, rest: RESTClient) -> GatewayEvent:
        """Subclasses override this to parse event-specific data."""
        return cls(raw=data)

#  Connection lifecycle

@dataclass(slots=True)
class UnavailableGuild:
    """A guild that is not yet available (still loading)."""

    id: Snowflake
    unavailable: bool = True

    @classmethod
    def from_payload(cls, data: dict[str, Any]) -> UnavailableGuild:
        return cls(id=Snowflake(data["id"]), unavailable=data.get("unavailable", True))


@dataclass(slots=True)
class ReadyEvent(GatewayEvent):
    """Fired once after initial gateway connection.

    Attributes
    ----------
    user:
        The bot's own user object.
    guilds:
        List of unavailable guilds the bot is in (they arrive later via GUILD_CREATE).
    session_id:
        Current session ID for resuming.
    resume_gateway_url:
        URL to use when resuming.
    application_id:
        The bot's application ID.
    shard:
        ``(shard_id, num_shards)`` if sharding, else None.
    """

    user: User = field(default=None)  # type: ignore[assignment]
    guilds: list[UnavailableGuild] = field(default_factory=list)
    session_id: str = ""
    resume_gateway_url: str = ""
    application_id: Snowflake | None = None
    shard: tuple[int, int] | None = None

    @classmethod
    def from_payload(cls, data: dict[str, Any], *, rest: RESTClient) -> ReadyEvent:
        guilds = [UnavailableGuild.from_payload(g) for g in data.get("guilds", [])]
        shard_data = data.get("shard")
        shard = tuple(shard_data) if shard_data and len(shard_data) == 2 else None

        return cls(
            raw=data,
            user=User.from_payload(data["user"]),
            guilds=guilds,
            session_id=data.get("session_id", ""),
            resume_gateway_url=data.get("resume_gateway_url", ""),
            application_id=Snowflake(data["application"]["id"]) if "application" in data else None,
            shard=shard,  # type: ignore[arg-type]
        )


@dataclass(slots=True)
class ResumedEvent(GatewayEvent):
    """Fired after a successful session resume."""

    @classmethod
    def from_payload(cls, data: dict[str, Any], *, rest: RESTClient) -> ResumedEvent:
        return cls(raw=data)

#  Messages

@dataclass(slots=True)
class MessageCreateEvent(GatewayEvent):
    """Fired when a message is sent in a channel the bot can see."""

    message: Message = field(default=None)  # type: ignore[assignment]

    @classmethod
    def from_payload(cls, data: dict[str, Any], *, rest: RESTClient) -> MessageCreateEvent:
        return cls(
            raw=data,
            message=Message.from_payload(data, rest=rest),
        )


@dataclass(slots=True)
class MessageUpdateEvent(GatewayEvent):
    """Fired when a message is edited."""

    message: Message = field(default=None)  # type: ignore[assignment]

    @classmethod
    def from_payload(cls, data: dict[str, Any], *, rest: RESTClient) -> MessageUpdateEvent:
        return cls(
            raw=data,
            message=Message.from_payload(data, rest=rest),
        )


@dataclass(slots=True)
class MessageDeleteEvent(GatewayEvent):
    """Fired when a message is deleted."""

    message_id: Snowflake = field(default=None)  # type: ignore[assignment]
    channel_id: Snowflake = field(default=None)  # type: ignore[assignment]
    guild_id: Snowflake | None = None

    @classmethod
    def from_payload(cls, data: dict[str, Any], *, rest: RESTClient) -> MessageDeleteEvent:
        return cls(
            raw=data,
            message_id=Snowflake(data["id"]),
            channel_id=Snowflake(data["channel_id"]),
            guild_id=Snowflake(data["guild_id"]) if data.get("guild_id") else None,
        )


@dataclass(slots=True)
class MessageDeleteBulkEvent(GatewayEvent):
    """Fired when messages are bulk-deleted."""

    message_ids: list[Snowflake] = field(default_factory=list)
    channel_id: Snowflake = field(default=None)  # type: ignore[assignment]
    guild_id: Snowflake | None = None

    @classmethod
    def from_payload(cls, data: dict[str, Any], *, rest: RESTClient) -> MessageDeleteBulkEvent:
        return cls(
            raw=data,
            message_ids=[Snowflake(mid) for mid in data.get("ids", [])],
            channel_id=Snowflake(data["channel_id"]),
            guild_id=Snowflake(data["guild_id"]) if data.get("guild_id") else None,
        )


@dataclass(slots=True)
class MessageReactionAddEvent(GatewayEvent):
    """Fired when a reaction is added to a message."""

    user_id: Snowflake = field(default=None)  # type: ignore[assignment]
    channel_id: Snowflake = field(default=None)  # type: ignore[assignment]
    message_id: Snowflake = field(default=None)  # type: ignore[assignment]
    guild_id: Snowflake | None = None
    emoji: dict[str, Any] = field(default_factory=dict)
    member: Member | None = None

    @classmethod
    def from_payload(cls, data: dict[str, Any], *, rest: RESTClient) -> MessageReactionAddEvent:
        guild_id = Snowflake(data["guild_id"]) if data.get("guild_id") else None
        member = Member.from_payload(data["member"], guild_id=guild_id) if "member" in data else None
        return cls(
            raw=data,
            user_id=Snowflake(data["user_id"]),
            channel_id=Snowflake(data["channel_id"]),
            message_id=Snowflake(data["message_id"]),
            guild_id=guild_id,
            emoji=data.get("emoji", {}),
            member=member,
        )


@dataclass(slots=True)
class MessageReactionRemoveEvent(GatewayEvent):
    """Fired when a reaction is removed from a message."""

    user_id: Snowflake = field(default=None)  # type: ignore[assignment]
    channel_id: Snowflake = field(default=None)  # type: ignore[assignment]
    message_id: Snowflake = field(default=None)  # type: ignore[assignment]
    guild_id: Snowflake | None = None
    emoji: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_payload(cls, data: dict[str, Any], *, rest: RESTClient) -> MessageReactionRemoveEvent:
        return cls(
            raw=data,
            user_id=Snowflake(data["user_id"]),
            channel_id=Snowflake(data["channel_id"]),
            message_id=Snowflake(data["message_id"]),
            guild_id=Snowflake(data["guild_id"]) if data.get("guild_id") else None,
            emoji=data.get("emoji", {}),
        )

#  Guilds

@dataclass(slots=True)
class GuildCreateEvent(GatewayEvent):
    """Fired when the bot joins a guild or a guild becomes available."""

    guild: Guild = field(default=None)  # type: ignore[assignment]
    channels: list[Channel] = field(default_factory=list)
    threads: list[Thread] = field(default_factory=list)
    members: list[Member] = field(default_factory=list)
    roles: list[Role] = field(default_factory=list)
    member_count: int = 0
    joined_at: str | None = None

    @classmethod
    def from_payload(cls, data: dict[str, Any], *, rest: RESTClient) -> GuildCreateEvent:
        guild_id = Snowflake(data["id"])
        channels = [Channel.from_payload(c) for c in data.get("channels", [])]
        threads = [Thread.from_payload(t) for t in data.get("threads", [])]
        members = [Member.from_payload(m, guild_id=guild_id) for m in data.get("members", [])]
        roles = [Role.from_payload(r) for r in data.get("roles", [])]

        return cls(
            raw=data,
            guild=Guild.from_payload(data),
            channels=channels,
            threads=threads,
            members=members,
            roles=roles,
            member_count=data.get("member_count", 0),
            joined_at=data.get("joined_at"),
        )


@dataclass(slots=True)
class GuildUpdateEvent(GatewayEvent):
    """Fired when a guild's settings are updated."""

    guild: Guild = field(default=None)  # type: ignore[assignment]

    @classmethod
    def from_payload(cls, data: dict[str, Any], *, rest: RESTClient) -> GuildUpdateEvent:
        return cls(raw=data, guild=Guild.from_payload(data))


@dataclass(slots=True)
class GuildDeleteEvent(GatewayEvent):
    """Fired when the bot is removed from a guild or the guild is unavailable."""

    guild_id: Snowflake = field(default=None)  # type: ignore[assignment]
    unavailable: bool = False

    @classmethod
    def from_payload(cls, data: dict[str, Any], *, rest: RESTClient) -> GuildDeleteEvent:
        return cls(
            raw=data,
            guild_id=Snowflake(data["id"]),
            unavailable=data.get("unavailable", False),
        )

#  Members

@dataclass(slots=True)
class GuildMemberAddEvent(GatewayEvent):
    """Fired when a user joins a guild."""

    member: Member = field(default=None)  # type: ignore[assignment]
    guild_id: Snowflake = field(default=None)  # type: ignore[assignment]

    @classmethod
    def from_payload(cls, data: dict[str, Any], *, rest: RESTClient) -> GuildMemberAddEvent:
        guild_id = Snowflake(data["guild_id"])
        return cls(
            raw=data,
            member=Member.from_payload(data, guild_id=guild_id),
            guild_id=guild_id,
        )


@dataclass(slots=True)
class GuildMemberRemoveEvent(GatewayEvent):
    """Fired when a user leaves/is kicked/banned from a guild."""

    user: User = field(default=None)  # type: ignore[assignment]
    guild_id: Snowflake = field(default=None)  # type: ignore[assignment]

    @classmethod
    def from_payload(cls, data: dict[str, Any], *, rest: RESTClient) -> GuildMemberRemoveEvent:
        return cls(
            raw=data,
            user=User.from_payload(data["user"]),
            guild_id=Snowflake(data["guild_id"]),
        )


@dataclass(slots=True)
class GuildMemberUpdateEvent(GatewayEvent):
    """Fired when a member's roles, nickname, etc. change."""

    guild_id: Snowflake = field(default=None)  # type: ignore[assignment]
    user: User = field(default=None)  # type: ignore[assignment]
    nick: str | None = None
    roles: list[Snowflake] = field(default_factory=list)
    joined_at: str | None = None
    premium_since: str | None = None
    pending: bool = False
    communication_disabled_until: str | None = None

    @classmethod
    def from_payload(cls, data: dict[str, Any], *, rest: RESTClient) -> GuildMemberUpdateEvent:
        return cls(
            raw=data,
            guild_id=Snowflake(data["guild_id"]),
            user=User.from_payload(data["user"]),
            nick=data.get("nick"),
            roles=[Snowflake(r) for r in data.get("roles", [])],
            joined_at=data.get("joined_at"),
            premium_since=data.get("premium_since"),
            pending=data.get("pending", False),
            communication_disabled_until=data.get("communication_disabled_until"),
        )

#  Channels

@dataclass(slots=True)
class ChannelCreateEvent(GatewayEvent):
    """Fired when a channel is created."""

    channel: Channel = field(default=None)  # type: ignore[assignment]

    @classmethod
    def from_payload(cls, data: dict[str, Any], *, rest: RESTClient) -> ChannelCreateEvent:
        return cls(raw=data, channel=Channel.from_payload(data))


@dataclass(slots=True)
class ChannelUpdateEvent(GatewayEvent):
    """Fired when a channel is updated."""

    channel: Channel = field(default=None)  # type: ignore[assignment]

    @classmethod
    def from_payload(cls, data: dict[str, Any], *, rest: RESTClient) -> ChannelUpdateEvent:
        return cls(raw=data, channel=Channel.from_payload(data))


@dataclass(slots=True)
class ChannelDeleteEvent(GatewayEvent):
    """Fired when a channel is deleted."""

    channel: Channel = field(default=None)  # type: ignore[assignment]

    @classmethod
    def from_payload(cls, data: dict[str, Any], *, rest: RESTClient) -> ChannelDeleteEvent:
        return cls(raw=data, channel=Channel.from_payload(data))

#  Roles

@dataclass(slots=True)
class GuildRoleCreateEvent(GatewayEvent):
    """Fired when a role is created."""

    guild_id: Snowflake = field(default=None)  # type: ignore[assignment]
    role: Role = field(default=None)  # type: ignore[assignment]

    @classmethod
    def from_payload(cls, data: dict[str, Any], *, rest: RESTClient) -> GuildRoleCreateEvent:
        return cls(
            raw=data,
            guild_id=Snowflake(data["guild_id"]),
            role=Role.from_payload(data["role"]),
        )


@dataclass(slots=True)
class GuildRoleUpdateEvent(GatewayEvent):
    """Fired when a role is updated."""

    guild_id: Snowflake = field(default=None)  # type: ignore[assignment]
    role: Role = field(default=None)  # type: ignore[assignment]

    @classmethod
    def from_payload(cls, data: dict[str, Any], *, rest: RESTClient) -> GuildRoleUpdateEvent:
        return cls(
            raw=data,
            guild_id=Snowflake(data["guild_id"]),
            role=Role.from_payload(data["role"]),
        )


@dataclass(slots=True)
class GuildRoleDeleteEvent(GatewayEvent):
    """Fired when a role is deleted."""

    guild_id: Snowflake = field(default=None)  # type: ignore[assignment]
    role_id: Snowflake = field(default=None)  # type: ignore[assignment]

    @classmethod
    def from_payload(cls, data: dict[str, Any], *, rest: RESTClient) -> GuildRoleDeleteEvent:
        return cls(
            raw=data,
            guild_id=Snowflake(data["guild_id"]),
            role_id=Snowflake(data["role_id"]),
        )

#  Threads

@dataclass(slots=True)
class ThreadCreateEvent(GatewayEvent):
    """Fired when a thread is created."""

    thread: Thread = field(default=None)  # type: ignore[assignment]

    @classmethod
    def from_payload(cls, data: dict[str, Any], *, rest: RESTClient) -> ThreadCreateEvent:
        return cls(raw=data, thread=Thread.from_payload(data))


@dataclass(slots=True)
class ThreadUpdateEvent(GatewayEvent):
    """Fired when a thread is updated."""

    thread: Thread = field(default=None)  # type: ignore[assignment]

    @classmethod
    def from_payload(cls, data: dict[str, Any], *, rest: RESTClient) -> ThreadUpdateEvent:
        return cls(raw=data, thread=Thread.from_payload(data))


@dataclass(slots=True)
class ThreadDeleteEvent(GatewayEvent):
    """Fired when a thread is deleted."""

    thread_id: Snowflake = field(default=None)  # type: ignore[assignment]
    guild_id: Snowflake = field(default=None)  # type: ignore[assignment]
    parent_id: Snowflake | None = None

    @classmethod
    def from_payload(cls, data: dict[str, Any], *, rest: RESTClient) -> ThreadDeleteEvent:
        return cls(
            raw=data,
            thread_id=Snowflake(data["id"]),
            guild_id=Snowflake(data["guild_id"]),
            parent_id=Snowflake(data["parent_id"]) if data.get("parent_id") else None,
        )

#  Interactions (pre-parsed by the interaction system, but also an event)

@dataclass(slots=True)
class InteractionCreateEvent(GatewayEvent):
    """Fired when an interaction is received.

    Usually handled by the SlashRouter — but available for custom dispatch.
    The ``interaction`` field is the raw dict; the SlashRouter creates the
    full Interaction object internally.
    """

    interaction_data: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_payload(cls, data: dict[str, Any], *, rest: RESTClient) -> InteractionCreateEvent:
        return cls(raw=data, interaction_data=data)

#  Typing & Presence

@dataclass(slots=True)
class TypingStartEvent(GatewayEvent):
    """Fired when a user starts typing."""

    channel_id: Snowflake = field(default=None)  # type: ignore[assignment]
    user_id: Snowflake = field(default=None)  # type: ignore[assignment]
    guild_id: Snowflake | None = None
    timestamp: int = 0
    member: Member | None = None

    @classmethod
    def from_payload(cls, data: dict[str, Any], *, rest: RESTClient) -> TypingStartEvent:
        guild_id = Snowflake(data["guild_id"]) if data.get("guild_id") else None
        member = Member.from_payload(data["member"], guild_id=guild_id) if "member" in data else None
        return cls(
            raw=data,
            channel_id=Snowflake(data["channel_id"]),
            user_id=Snowflake(data["user_id"]),
            guild_id=guild_id,
            timestamp=data.get("timestamp", 0),
            member=member,
        )


@dataclass(slots=True)
class PresenceUpdateEvent(GatewayEvent):
    """Fired when a user's presence changes."""

    user_id: Snowflake = field(default=None)  # type: ignore[assignment]
    guild_id: Snowflake = field(default=None)  # type: ignore[assignment]
    status: str = "offline"
    activities: list[dict[str, Any]] = field(default_factory=list)

    @classmethod
    def from_payload(cls, data: dict[str, Any], *, rest: RESTClient) -> PresenceUpdateEvent:
        return cls(
            raw=data,
            user_id=Snowflake(data.get("user", {}).get("id", 0)),
            guild_id=Snowflake(data["guild_id"]) if data.get("guild_id") else Snowflake(0),
            status=data.get("status", "offline"),
            activities=data.get("activities", []),
        )

#  Voice

@dataclass(slots=True)
class VoiceStateUpdateEvent(GatewayEvent):
    """Fired when a user's voice state changes (join, leave, mute, etc.)."""

    guild_id: Snowflake | None = None
    channel_id: Snowflake | None = None
    user_id: Snowflake = field(default=None)  # type: ignore[assignment]
    session_id: str = ""
    deaf: bool = False
    mute: bool = False
    self_deaf: bool = False
    self_mute: bool = False
    self_stream: bool = False
    self_video: bool = False
    suppress: bool = False
    member: Member | None = None

    @classmethod
    def from_payload(cls, data: dict[str, Any], *, rest: RESTClient) -> VoiceStateUpdateEvent:
        guild_id = Snowflake(data["guild_id"]) if data.get("guild_id") else None
        member = Member.from_payload(data["member"], guild_id=guild_id) if "member" in data else None
        return cls(
            raw=data,
            guild_id=guild_id,
            channel_id=Snowflake(data["channel_id"]) if data.get("channel_id") else None,
            user_id=Snowflake(data["user_id"]),
            session_id=data.get("session_id", ""),
            deaf=data.get("deaf", False),
            mute=data.get("mute", False),
            self_deaf=data.get("self_deaf", False),
            self_mute=data.get("self_mute", False),
            self_stream=data.get("self_stream", False),
            self_video=data.get("self_video", False),
            suppress=data.get("suppress", False),
            member=member,
        )

#  Ban events

@dataclass(slots=True)
class GuildBanAddEvent(GatewayEvent):
    """Fired when a user is banned."""

    guild_id: Snowflake = field(default=None)  # type: ignore[assignment]
    user: User = field(default=None)  # type: ignore[assignment]

    @classmethod
    def from_payload(cls, data: dict[str, Any], *, rest: RESTClient) -> GuildBanAddEvent:
        return cls(
            raw=data,
            guild_id=Snowflake(data["guild_id"]),
            user=User.from_payload(data["user"]),
        )


@dataclass(slots=True)
class GuildBanRemoveEvent(GatewayEvent):
    """Fired when a user is unbanned."""

    guild_id: Snowflake = field(default=None)  # type: ignore[assignment]
    user: User = field(default=None)  # type: ignore[assignment]

    @classmethod
    def from_payload(cls, data: dict[str, Any], *, rest: RESTClient) -> GuildBanRemoveEvent:
        return cls(
            raw=data,
            guild_id=Snowflake(data["guild_id"]),
            user=User.from_payload(data["user"]),
        )

#  Invite events

@dataclass(slots=True)
class InviteCreateEvent(GatewayEvent):
    """Fired when a guild invite is created."""

    channel_id: Snowflake = field(default=None)  # type: ignore[assignment]
    guild_id: Snowflake | None = None
    code: str = ""
    inviter: User | None = None
    max_age: int = 0
    max_uses: int = 0
    temporary: bool = False

    @classmethod
    def from_payload(cls, data: dict[str, Any], *, rest: RESTClient) -> InviteCreateEvent:
        inviter = User.from_payload(data["inviter"]) if "inviter" in data else None
        return cls(
            raw=data,
            channel_id=Snowflake(data["channel_id"]),
            guild_id=Snowflake(data["guild_id"]) if data.get("guild_id") else None,
            code=data.get("code", ""),
            inviter=inviter,
            max_age=data.get("max_age", 0),
            max_uses=data.get("max_uses", 0),
            temporary=data.get("temporary", False),
        )


@dataclass(slots=True)
class InviteDeleteEvent(GatewayEvent):
    """Fired when a guild invite is deleted."""

    channel_id: Snowflake = field(default=None)  # type: ignore[assignment]
    guild_id: Snowflake | None = None
    code: str = ""

    @classmethod
    def from_payload(cls, data: dict[str, Any], *, rest: RESTClient) -> InviteDeleteEvent:
        return cls(
            raw=data,
            channel_id=Snowflake(data["channel_id"]),
            guild_id=Snowflake(data["guild_id"]) if data.get("guild_id") else None,
            code=data.get("code", ""),
        )

#  Event Registry — maps Discord event names to their typed classes

EVENT_REGISTRY: dict[str, type[GatewayEvent]] = {
    "ready": ReadyEvent,
    "resumed": ResumedEvent,
    # Messages
    "message_create": MessageCreateEvent,
    "message_update": MessageUpdateEvent,
    "message_delete": MessageDeleteEvent,
    "message_delete_bulk": MessageDeleteBulkEvent,
    "message_reaction_add": MessageReactionAddEvent,
    "message_reaction_remove": MessageReactionRemoveEvent,
    # Guilds
    "guild_create": GuildCreateEvent,
    "guild_update": GuildUpdateEvent,
    "guild_delete": GuildDeleteEvent,
    "guild_ban_add": GuildBanAddEvent,
    "guild_ban_remove": GuildBanRemoveEvent,
    # Members
    "guild_member_add": GuildMemberAddEvent,
    "guild_member_remove": GuildMemberRemoveEvent,
    "guild_member_update": GuildMemberUpdateEvent,
    # Channels
    "channel_create": ChannelCreateEvent,
    "channel_update": ChannelUpdateEvent,
    "channel_delete": ChannelDeleteEvent,
    # Roles
    "guild_role_create": GuildRoleCreateEvent,
    "guild_role_update": GuildRoleUpdateEvent,
    "guild_role_delete": GuildRoleDeleteEvent,
    # Threads
    "thread_create": ThreadCreateEvent,
    "thread_update": ThreadUpdateEvent,
    "thread_delete": ThreadDeleteEvent,
    # Interactions
    "interaction_create": InteractionCreateEvent,
    # Typing & Presence
    "typing_start": TypingStartEvent,
    "presence_update": PresenceUpdateEvent,
    # Voice
    "voice_state_update": VoiceStateUpdateEvent,
    # Invites
    "invite_create": InviteCreateEvent,
    "invite_delete": InviteDeleteEvent,
}


def parse_event(event_name: str, data: dict[str, Any], *, rest: RESTClient) -> GatewayEvent:
    """Parse a raw gateway event into its typed event class.

    Falls back to a generic ``GatewayEvent`` for unrecognised event names.
    """
    event_cls = EVENT_REGISTRY.get(event_name)
    if event_cls is not None:
        try:
            return event_cls.from_payload(data, rest=rest)
        except (KeyError, TypeError, ValueError):
            # Malformed payload — return generic event so the bot doesn't crash
            return GatewayEvent(raw=data)
    return GatewayEvent(raw=data)
