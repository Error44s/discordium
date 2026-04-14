"""
discordium - next-generation async Discord API wrapper for Python 3.11+

Zero bloat. Fully typed. Built for speed.
"""

from __future__ import annotations

__version__ = "0.1.0b1"

# Core client
from .client import GatewayClient

# Models data structures
from .models.intents import Intents
from .models.snowflake import Snowflake
from .models.message import Message
from .models.guild import Guild
from .models.user import User
from .models.channel import Channel
from .models.embed import Embed, EmbedField
from .models.enums import ChannelType, GuildFeature, Status, ActivityType
from .models.permissions import Permissions, PermissionOverwrite
from .models.role import Role
from .models.member import Member
from .models.interaction import Interaction, InteractionType
from .models.components import (
    ActionRow, Button, ButtonStyle, SelectMenu, SelectOption,
    TextInput, TextInputStyle, Modal, ComponentType,
)
from .models.file import File
from .models.webhook import Webhook
from .models.thread import Thread, ThreadMetadata, ForumTag
from .models.audit_log import AuditLog, AuditLogEntry, AuditLogEvent
from .models.automod import (
    AutoModRule, AutoModAction, AutoModActionType,
    AutoModTriggerType, AutoModEventType, AutoModKeywordPreset,
)

# Typed events
from .models.events import (
    GatewayEvent,
    ReadyEvent,
    ResumedEvent,
    MessageCreateEvent,
    MessageUpdateEvent,
    MessageDeleteEvent,
    MessageDeleteBulkEvent,
    MessageReactionAddEvent,
    MessageReactionRemoveEvent,
    GuildCreateEvent,
    GuildUpdateEvent,
    GuildDeleteEvent,
    GuildMemberAddEvent,
    GuildMemberRemoveEvent,
    GuildMemberUpdateEvent,
    ChannelCreateEvent,
    ChannelUpdateEvent,
    ChannelDeleteEvent,
    GuildRoleCreateEvent,
    GuildRoleUpdateEvent,
    GuildRoleDeleteEvent,
    ThreadCreateEvent,
    ThreadUpdateEvent,
    ThreadDeleteEvent,
    InteractionCreateEvent,
    TypingStartEvent,
    PresenceUpdateEvent,
    VoiceStateUpdateEvent,
    GuildBanAddEvent,
    GuildBanRemoveEvent,
    InviteCreateEvent,
    InviteDeleteEvent,
)

# Cache
from .cache.base import CachePolicy, NoCache, TTLCache

# Events
from .utils.event import EventEmitter, listener, once

# Event name constants use instead of raw strings
from .models.event_names import Events, EventName

# Errors structured exception hierarchy
from .errors import (
    DiscordiumError,
    HTTPError,
    Forbidden,
    NotFound,
    RateLimited,
    ServerError,
    GatewayError,
    GatewayReconnect,
    InvalidSession,
    HeartbeatTimeout,
    ConnectionClosed,
    InteractionError,
    InteractionAlreadyResponded,
    InteractionNotResponded,
    InteractionTimedOut,
    CommandError,
    CommandNotFound,
    CommandOnCooldown,
    CheckFailure,
    MissingPermissions,
    BotMissingPermissions,
    NotOwner,
    GuildOnly,
    DMOnly,
    MaxConcurrencyReached,
    ClientError,
    NotReady,
    AlreadyConnected,
    LoginFailure,
)

__all__ = [
    # Core
    "GatewayClient",
    # Models
    "Intents", "Snowflake", "Message", "Guild", "User", "Channel",
    "Embed", "EmbedField",
    "ChannelType", "GuildFeature", "Status", "ActivityType",
    "Permissions", "PermissionOverwrite",
    "Role", "Member",
    "Interaction", "InteractionType",
    "ActionRow", "Button", "ButtonStyle", "SelectMenu", "SelectOption",
    "TextInput", "TextInputStyle", "Modal", "ComponentType",
    "File", "Webhook",
    "Thread", "ThreadMetadata", "ForumTag",
    "AuditLog", "AuditLogEntry", "AuditLogEvent",
    "AutoModRule", "AutoModAction", "AutoModActionType",
    "AutoModTriggerType", "AutoModEventType", "AutoModKeywordPreset",
    # Typed Events
    "GatewayEvent", "ReadyEvent", "ResumedEvent",
    "MessageCreateEvent", "MessageUpdateEvent", "MessageDeleteEvent",
    "MessageDeleteBulkEvent", "MessageReactionAddEvent", "MessageReactionRemoveEvent",
    "GuildCreateEvent", "GuildUpdateEvent", "GuildDeleteEvent",
    "GuildMemberAddEvent", "GuildMemberRemoveEvent", "GuildMemberUpdateEvent",
    "ChannelCreateEvent", "ChannelUpdateEvent", "ChannelDeleteEvent",
    "GuildRoleCreateEvent", "GuildRoleUpdateEvent", "GuildRoleDeleteEvent",
    "ThreadCreateEvent", "ThreadUpdateEvent", "ThreadDeleteEvent",
    "InteractionCreateEvent",
    "TypingStartEvent", "PresenceUpdateEvent", "VoiceStateUpdateEvent",
    "GuildBanAddEvent", "GuildBanRemoveEvent",
    "InviteCreateEvent", "InviteDeleteEvent",
    # Cache
    "CachePolicy", "NoCache", "TTLCache",
    # Events
    "EventEmitter", "listener", "once",
    # Errors
    "DiscordiumError", "HTTPError", "Forbidden", "NotFound", "RateLimited",
    "ServerError", "GatewayError", "GatewayReconnect", "InvalidSession",
    "HeartbeatTimeout", "ConnectionClosed",
    "InteractionError", "InteractionAlreadyResponded",
    "InteractionNotResponded", "InteractionTimedOut",
    "CommandError", "CommandNotFound", "CommandOnCooldown",
    "CheckFailure", "MissingPermissions", "BotMissingPermissions",
    "NotOwner", "GuildOnly", "DMOnly", "MaxConcurrencyReached",
    "ClientError", "NotReady", "AlreadyConnected", "LoginFailure",
]
