"""Discord Role model — full v10 coverage."""

from __future__ import annotations

from enum import IntFlag
from typing import Any, Self

from .base import Model
from .permissions import Permissions
from .snowflake import Snowflake


class RoleFlags(IntFlag):
    IN_PROMPT = 1 << 0   # role is selectable in an onboarding prompt


class RoleTags(Model):
    """Special metadata tags attached to managed/integration roles.

    All fields are optional and absent when not applicable.

    Attributes
    ----------
    bot_id:
        If present, this role is the bot's managed role.
    integration_id:
        If present, this role belongs to an integration.
    subscription_listing_id:
        If present, this is a purchasable role-subscription role.
    premium_subscriber:
        ``True`` if this is the guild's Nitro booster role.
    available_for_purchase:
        ``True`` if this role can be purchased (requires ``subscription_listing_id``).
    guild_connections:
        ``True`` if this role is a guild's linked-role role.
    """

    bot_id: Snowflake | None = None
    integration_id: Snowflake | None = None
    subscription_listing_id: Snowflake | None = None
    premium_subscriber: bool = False
    available_for_purchase: bool = False
    guild_connections: bool = False

    @classmethod
    def from_payload(cls, data: dict[str, Any]) -> Self:
        # Note: Discord sends these tag keys with null values when true (not
        # a boolean) — the key's presence alone encodes the boolean.
        return cls(
            bot_id=Snowflake(data["bot_id"]) if data.get("bot_id") else None,
            integration_id=Snowflake(data["integration_id"]) if data.get("integration_id") else None,
            subscription_listing_id=Snowflake(data["subscription_listing_id"]) if data.get("subscription_listing_id") else None,
            premium_subscriber="premium_subscriber" in data,
            available_for_purchase="available_for_purchase" in data,
            guild_connections="guild_connections" in data,
        )


class Role(Model):
    """Represents a Discord guild role.

    Attributes
    ----------
    id:
        Role Snowflake.
    name:
        Role name.
    color:
        Integer RGB colour (0 = no colour).
    hoist:
        Whether the role is displayed separately in the member list.
    icon:
        Role icon hash (requires ROLE_ICONS feature).
    unicode_emoji:
        Unicode emoji used as the role icon.
    position:
        Role position (0 = @everyone, higher = higher in the hierarchy).
    permissions:
        Permission bitfield.
    managed:
        Whether this role is managed by an integration/bot.
    mentionable:
        Whether members can mention this role.
    tags:
        Special metadata for managed roles.
    flags:
        :class:`RoleFlags` bitmask.
    """

    id: Snowflake
    name: str
    color: int = 0
    hoist: bool = False
    icon: str | None = None
    unicode_emoji: str | None = None
    position: int = 0
    permissions: Permissions = Permissions(0)
    managed: bool = False
    mentionable: bool = False
    tags: RoleTags | None = None
    flags: int = 0

    # Computed

    @property
    def mention(self) -> str:
        return f"<@&{self.id}>"

    @property
    def is_default(self) -> bool:
        """True if this is the @everyone role (position 0)."""
        return self.position == 0

    @property
    def is_bot_managed(self) -> bool:
        """True if this role was automatically created for a bot."""
        return self.tags is not None and self.tags.bot_id is not None

    @property
    def is_integration(self) -> bool:
        """True if this role belongs to an integration (e.g. Twitch sub)."""
        return self.tags is not None and self.tags.integration_id is not None

    @property
    def is_booster_role(self) -> bool:
        """True if this is the guild's Nitro booster role."""
        return self.tags is not None and self.tags.premium_subscriber

    @property
    def is_purchasable(self) -> bool:
        """True if this role can be bought via role subscriptions."""
        return self.tags is not None and self.tags.available_for_purchase

    @property
    def color_hex(self) -> str:
        """Role colour as a hex string like ``#5865F2``. Returns ``#000000`` for colourless."""
        return f"#{self.color:06x}"

    @property
    def created_at(self):
        return self.id.created_at

    @property
    def role_flags(self) -> RoleFlags:
        return RoleFlags(self.flags)

    # Icon helpers

    def icon_url(self, *, size: int = 64, fmt: str = "webp") -> str | None:
        if self.icon is None:
            return None
        return f"https://cdn.discordapp.com/role-icons/{self.id}/{self.icon}.{fmt}?size={size}"

    @property
    def display_icon(self) -> str | None:
        """Unicode emoji if set, otherwise the role icon URL (or None)."""
        return self.unicode_emoji or self.icon_url()

    # Permission helpers

    def has_permission(self, *perms: Permissions) -> bool:
        """Check if this role has all specified permissions."""
        return self.permissions.has(*perms)

    # Construction

    @classmethod
    def from_payload(cls, data: dict[str, Any]) -> Self:
        tags = RoleTags.from_payload(data["tags"]) if "tags" in data else None
        return cls(
            id=Snowflake(data["id"]),
            name=data["name"],
            color=data.get("color", 0),
            hoist=data.get("hoist", False),
            icon=data.get("icon"),
            unicode_emoji=data.get("unicode_emoji"),
            position=data.get("position", 0),
            permissions=Permissions.from_value(data.get("permissions", 0)),
            managed=data.get("managed", False),
            mentionable=data.get("mentionable", False),
            tags=tags,
            flags=data.get("flags", 0),
        )

    def __repr__(self) -> str:
        return f"Role(id={self.id}, name={self.name!r}, position={self.position})"
