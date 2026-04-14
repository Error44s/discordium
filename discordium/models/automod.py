"""Discord AutoModeration models.

Create and manage auto-moderation rules::

    rule = await rest.create_automod_rule(
        guild_id,
        name="No Spam Links",
        event_type=AutoModEventType.MESSAGE_SEND,
        trigger_type=AutoModTriggerType.KEYWORD,
        trigger_metadata={"keyword_filter": ["discord.gg", "free nitro"]},
        actions=[AutoModAction.block_message("Spam link detected")],
    )
"""

from __future__ import annotations

from enum import IntEnum
from typing import Any, Self

from .base import Model
from .snowflake import Snowflake


class AutoModEventType(IntEnum):
    MESSAGE_SEND = 1
    MEMBER_UPDATE = 2


class AutoModTriggerType(IntEnum):
    KEYWORD = 1
    SPAM = 3
    KEYWORD_PRESET = 4
    MENTION_SPAM = 5
    MEMBER_PROFILE = 6


class AutoModActionType(IntEnum):
    BLOCK_MESSAGE = 1
    SEND_ALERT_MESSAGE = 2
    TIMEOUT = 3
    BLOCK_MEMBER_INTERACTION = 4


class AutoModKeywordPreset(IntEnum):
    PROFANITY = 1
    SEXUAL_CONTENT = 2
    SLURS = 3


class AutoModAction:
    """A single action taken when an AutoMod rule triggers."""

    __slots__ = ("type", "metadata")

    def __init__(self, type: AutoModActionType, metadata: dict[str, Any] | None = None) -> None:
        self.type = type
        self.metadata = metadata or {}

    @classmethod
    def block_message(cls, custom_message: str | None = None) -> AutoModAction:
        meta = {}
        if custom_message:
            meta["custom_message"] = custom_message
        return cls(AutoModActionType.BLOCK_MESSAGE, meta)

    @classmethod
    def send_alert(cls, channel_id: int | Snowflake) -> AutoModAction:
        return cls(AutoModActionType.SEND_ALERT_MESSAGE, {"channel_id": str(channel_id)})

    @classmethod
    def timeout(cls, duration_seconds: int) -> AutoModAction:
        return cls(AutoModActionType.TIMEOUT, {"duration_seconds": duration_seconds})

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {"type": self.type}
        if self.metadata:
            d["metadata"] = self.metadata
        return d

    @classmethod
    def from_payload(cls, data: dict[str, Any]) -> AutoModAction:
        return cls(
            type=AutoModActionType(data["type"]),
            metadata=data.get("metadata"),
        )


class AutoModRule(Model):
    """Represents an AutoModeration rule."""

    id: Snowflake
    guild_id: Snowflake
    name: str
    creator_id: Snowflake | None = None
    event_type: int = AutoModEventType.MESSAGE_SEND
    trigger_type: int = AutoModTriggerType.KEYWORD
    trigger_metadata: dict[str, Any] | None = None
    actions: list[AutoModAction] | None = None
    enabled: bool = True
    exempt_roles: list[Snowflake] | None = None
    exempt_channels: list[Snowflake] | None = None

    @classmethod
    def from_payload(cls, data: dict[str, Any]) -> Self:
        actions = (
            [AutoModAction.from_payload(a) for a in data["actions"]]
            if "actions" in data
            else None
        )
        exempt_roles = [Snowflake(r) for r in data.get("exempt_roles", [])] or None
        exempt_channels = [Snowflake(c) for c in data.get("exempt_channels", [])] or None

        return cls(
            id=Snowflake(data["id"]),
            guild_id=Snowflake(data["guild_id"]),
            name=data["name"],
            creator_id=Snowflake(data["creator_id"]) if data.get("creator_id") else None,
            event_type=data.get("event_type", AutoModEventType.MESSAGE_SEND),
            trigger_type=data.get("trigger_type", AutoModTriggerType.KEYWORD),
            trigger_metadata=data.get("trigger_metadata"),
            actions=actions,
            enabled=data.get("enabled", True),
            exempt_roles=exempt_roles,
            exempt_channels=exempt_channels,
        )

    def to_create_dict(self) -> dict[str, Any]:
        """Serialise for the create/update endpoints."""
        d: dict[str, Any] = {
            "name": self.name,
            "event_type": self.event_type,
            "trigger_type": self.trigger_type,
            "enabled": self.enabled,
        }
        if self.trigger_metadata:
            d["trigger_metadata"] = self.trigger_metadata
        if self.actions:
            d["actions"] = [a.to_dict() for a in self.actions]
        if self.exempt_roles:
            d["exempt_roles"] = [str(r) for r in self.exempt_roles]
        if self.exempt_channels:
            d["exempt_channels"] = [str(c) for c in self.exempt_channels]
        return d
