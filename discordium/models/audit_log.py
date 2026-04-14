"""Discord Audit Log models — full v10 coverage."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import IntEnum
from typing import Any, Iterator, Self

from .base import Model
from .snowflake import Snowflake


class AuditLogEvent(IntEnum):
    """All audit log action types as of Discord API v10."""

    GUILD_UPDATE = 1
    CHANNEL_CREATE = 10
    CHANNEL_UPDATE = 11
    CHANNEL_DELETE = 12
    CHANNEL_OVERWRITE_CREATE = 13
    CHANNEL_OVERWRITE_UPDATE = 14
    CHANNEL_OVERWRITE_DELETE = 15
    MEMBER_KICK = 20
    MEMBER_PRUNE = 21
    MEMBER_BAN_ADD = 22
    MEMBER_BAN_REMOVE = 23
    MEMBER_UPDATE = 24
    MEMBER_ROLE_UPDATE = 25
    MEMBER_MOVE = 26
    MEMBER_DISCONNECT = 27
    BOT_ADD = 28
    ROLE_CREATE = 30
    ROLE_UPDATE = 31
    ROLE_DELETE = 32
    INVITE_CREATE = 40
    INVITE_UPDATE = 41
    INVITE_DELETE = 42
    WEBHOOK_CREATE = 50
    WEBHOOK_UPDATE = 51
    WEBHOOK_DELETE = 52
    EMOJI_CREATE = 60
    EMOJI_UPDATE = 61
    EMOJI_DELETE = 62
    MESSAGE_DELETE = 72
    MESSAGE_BULK_DELETE = 73
    MESSAGE_PIN = 74
    MESSAGE_UNPIN = 75
    INTEGRATION_CREATE = 80
    INTEGRATION_UPDATE = 81
    INTEGRATION_DELETE = 82
    STAGE_INSTANCE_CREATE = 83
    STAGE_INSTANCE_UPDATE = 84
    STAGE_INSTANCE_DELETE = 85
    STICKER_CREATE = 90
    STICKER_UPDATE = 91
    STICKER_DELETE = 92
    GUILD_SCHEDULED_EVENT_CREATE = 100
    GUILD_SCHEDULED_EVENT_UPDATE = 101
    GUILD_SCHEDULED_EVENT_DELETE = 102
    THREAD_CREATE = 110
    THREAD_UPDATE = 111
    THREAD_DELETE = 112
    APPLICATION_COMMAND_PERMISSION_UPDATE = 121
    SOUNDBOARD_SOUND_CREATE = 130
    SOUNDBOARD_SOUND_UPDATE = 131
    SOUNDBOARD_SOUND_DELETE = 132
    AUTO_MODERATION_RULE_CREATE = 140
    AUTO_MODERATION_RULE_UPDATE = 141
    AUTO_MODERATION_RULE_DELETE = 142
    AUTO_MODERATION_BLOCK_MESSAGE = 143
    AUTO_MODERATION_FLAG_TO_CHANNEL = 144
    AUTO_MODERATION_USER_COMMUNICATION_DISABLED = 145
    CREATOR_MONETIZATION_REQUEST_CREATED = 150
    CREATOR_MONETIZATION_TERMS_ACCEPTED = 151
    ROLE_SUBSCRIPTION_LISTING_CREATE = 162
    ROLE_SUBSCRIPTION_LISTING_UPDATE = 163
    ROLE_SUBSCRIPTION_LISTING_DELETE = 164
    ROLE_SUBSCRIPTION_GIFT_AUTO_REDEEMED = 169
    ROLE_SUBSCRIPTION_BULK_GRACE_PERIOD_INITIATED = 170


class AuditLogChange:
    """A single field change within an audit log entry.

    Attributes
    ----------
    key:
        The name of the changed field (e.g. ``"name"``, ``"permissions"``).
    old_value:
        Value before the change (may be absent if the field was created).
    new_value:
        Value after the change (may be absent if the field was deleted).
    """

    __slots__ = ("key", "old_value", "new_value")

    def __init__(self, data: dict[str, Any]) -> None:
        self.key: str = data["key"]
        self.old_value: Any = data.get("old_value")
        self.new_value: Any = data.get("new_value")

    def __repr__(self) -> str:
        return f"AuditLogChange({self.key!r}: {self.old_value!r} → {self.new_value!r})"


class AuditLogOptions:
    """Optional extra data attached to certain audit log entry types.

    Not every field is present for every action type.

    Attributes
    ----------
    application_id:
        For APPLICATION_COMMAND_PERMISSION_UPDATE.
    auto_moderation_rule_name:
        For AUTO_MODERATION_* actions.
    auto_moderation_rule_trigger_type:
        For AUTO_MODERATION_* actions.
    channel_id:
        Channel targeted by the action (pins, moves, etc.).
    count:
        Number of affected entities (bulk deletes, prunes, etc.).
    delete_member_days:
        How many days' inactivity was used for the prune.
    id:
        ID of the overwrite target role/user.
    members_removed:
        Number of members removed by prune.
    message_id:
        Specific message targeted (pins, etc.).
    role_name:
        Name of the role target for overwrite actions.
    type:
        Type of overwrite (``"0"`` = role, ``"1"`` = member).
    integration_type:
        For MEMBER_ROLE_UPDATE via integration.
    """

    __slots__ = (
        "application_id", "auto_moderation_rule_name",
        "auto_moderation_rule_trigger_type",
        "channel_id", "count", "delete_member_days", "id",
        "members_removed", "message_id", "role_name", "type",
        "integration_type",
    )

    def __init__(self, data: dict[str, Any]) -> None:
        self.application_id: Snowflake | None = (
            Snowflake(data["application_id"]) if "application_id" in data else None
        )
        self.auto_moderation_rule_name: str | None = data.get("auto_moderation_rule_name")
        self.auto_moderation_rule_trigger_type: str | None = data.get(
            "auto_moderation_rule_trigger_type"
        )
        self.channel_id: Snowflake | None = (
            Snowflake(data["channel_id"]) if "channel_id" in data else None
        )
        self.count: int | None = int(data["count"]) if "count" in data else None
        self.delete_member_days: int | None = (
            int(data["delete_member_days"]) if "delete_member_days" in data else None
        )
        self.id: Snowflake | None = Snowflake(data["id"]) if "id" in data else None
        self.members_removed: int | None = (
            int(data["members_removed"]) if "members_removed" in data else None
        )
        self.message_id: Snowflake | None = (
            Snowflake(data["message_id"]) if "message_id" in data else None
        )
        self.role_name: str | None = data.get("role_name")
        self.type: str | None = data.get("type")
        self.integration_type: str | None = data.get("integration_type")

    def __repr__(self) -> str:
        parts = []
        for slot in self.__slots__:
            val = getattr(self, slot)
            if val is not None:
                parts.append(f"{slot}={val!r}")
        return f"AuditLogOptions({', '.join(parts)})"


class AuditLogEntry(Model):
    """A single audit log entry.

    Attributes
    ----------
    id:
        Entry Snowflake.
    user_id:
        User who performed the action.
    target_id:
        The affected entity's ID (channel, user, role, etc.).
    action_type:
        Raw action type integer.
    reason:
        Reason provided with the action (if any).
    changes:
        List of field changes.
    options:
        Extra context data (type-dependent).
    """

    id: Snowflake
    user_id: Snowflake | None = None
    target_id: Snowflake | None = None
    action_type: int = 0
    reason: str | None = None
    changes: list[AuditLogChange] | None = None
    options: AuditLogOptions | None = None

    # Computed

    @property
    def event(self) -> AuditLogEvent | int:
        """Typed :class:`AuditLogEvent` enum value, or raw int if unrecognised."""
        try:
            return AuditLogEvent(self.action_type)
        except ValueError:
            return self.action_type

    @property
    def created_at(self) -> datetime:
        return self.id.created_at

    def get_change(self, key: str) -> AuditLogChange | None:
        """Look up a specific change by field name."""
        if not self.changes:
            return None
        for c in self.changes:
            if c.key == key:
                return c
        return None

    def changed_value(self, key: str) -> Any:
        """Shortcut: return the *new_value* of a change by key, or ``None``."""
        change = self.get_change(key)
        return change.new_value if change else None

    # Construction

    @classmethod
    def from_payload(cls, data: dict[str, Any]) -> Self:
        changes = (
            [AuditLogChange(c) for c in data["changes"]]
            if "changes" in data else None
        )
        options = (
            AuditLogOptions(data["options"])
            if "options" in data else None
        )
        return cls(
            id=Snowflake(data["id"]),
            user_id=Snowflake(data["user_id"]) if data.get("user_id") else None,
            target_id=Snowflake(data["target_id"]) if data.get("target_id") else None,
            action_type=data.get("action_type", 0),
            reason=data.get("reason"),
            changes=changes,
            options=options,
        )

    def __repr__(self) -> str:
        return (
            f"AuditLogEntry(id={self.id}, event={self.event!r}, "
            f"user={self.user_id}, target={self.target_id})"
        )


class AuditLog:
    """Container for an audit log query result.

    Attributes
    ----------
    entries:
        Parsed :class:`AuditLogEntry` objects (newest first).
    users:
        Raw user objects referenced by entries.
    webhooks:
        Raw webhook objects referenced by entries.
    integrations:
        Raw integration objects referenced by entries.
    threads:
        Raw thread channel objects referenced by entries.
    application_commands:
        Raw application command objects referenced by entries.
    auto_moderation_rules:
        Raw auto-moderation rule objects referenced by entries.
    """

    __slots__ = (
        "entries", "users", "webhooks", "integrations",
        "threads", "application_commands", "auto_moderation_rules",
    )

    def __init__(self, data: dict[str, Any]) -> None:
        self.entries: list[AuditLogEntry] = [
            AuditLogEntry.from_payload(e) for e in data.get("audit_log_entries", [])
        ]
        self.users: list[dict[str, Any]] = data.get("users", [])
        self.webhooks: list[dict[str, Any]] = data.get("webhooks", [])
        self.integrations: list[dict[str, Any]] = data.get("integrations", [])
        self.threads: list[dict[str, Any]] = data.get("threads", [])
        self.application_commands: list[dict[str, Any]] = data.get("application_commands", [])
        self.auto_moderation_rules: list[dict[str, Any]] = data.get("auto_moderation_rules", [])

    # Filtering helpers

    def filter_by(self, event: AuditLogEvent | int) -> list[AuditLogEntry]:
        """Filter entries by a specific action type."""
        return [e for e in self.entries if e.action_type == int(event)]

    def by_user(self, user_id: int | Snowflake) -> list[AuditLogEntry]:
        """Filter entries by the user who performed the action."""
        uid = int(user_id)
        return [e for e in self.entries if e.user_id and int(e.user_id) == uid]

    def by_target(self, target_id: int | Snowflake) -> list[AuditLogEntry]:
        """Filter entries by the affected entity."""
        tid = int(target_id)
        return [e for e in self.entries if e.target_id and int(e.target_id) == tid]

    def since(self, dt: datetime) -> list[AuditLogEntry]:
        """Filter to entries created after a given datetime."""
        return [e for e in self.entries if e.created_at >= dt]

    def with_reason(self) -> list[AuditLogEntry]:
        """Filter to entries that have an audit-log reason attached."""
        return [e for e in self.entries if e.reason]

    # Dunder

    def __len__(self) -> int:
        return len(self.entries)

    def __iter__(self) -> Iterator[AuditLogEntry]:
        return iter(self.entries)

    def __getitem__(self, index: int) -> AuditLogEntry:
        return self.entries[index]

    def __repr__(self) -> str:
        return f"AuditLog({len(self.entries)} entries)"
