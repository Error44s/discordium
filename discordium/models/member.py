"""Discord Guild Member model — full v10 coverage."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Self

from .base import Model
from .permissions import Permissions
from .snowflake import Snowflake
from .user import User


class Member(Model):
    """Represents a member of a Discord guild.

    Contains the user's guild-specific data (roles, nickname, voice state
    fragments, etc.) as well as a reference to their base :class:`User`.

    Attributes
    ----------
    user:
        Underlying user (absent in some MESSAGE_CREATE payloads).
    nick:
        Guild-specific nickname.
    avatar:
        Guild-specific avatar hash (overrides the user's global avatar).
    banner:
        Guild-specific banner hash.
    roles:
        List of role Snowflakes the member holds.
    joined_at:
        ISO8601 timestamp of when the user joined the guild.
    premium_since:
        ISO8601 timestamp of when the user started boosting (``None`` if not boosting).
    deaf:
        Whether the user is server-deafened in voice.
    mute:
        Whether the user is server-muted in voice.
    pending:
        Whether the user has completed member verification (Community guilds).
    permissions:
        Resolved permissions (only populated in interaction payloads).
    communication_disabled_until:
        ISO8601 expiry of an active timeout, or ``None``.
    flags:
        Member flag bitmask.
    guild_id:
        Injected at construction — not part of the Discord payload.
    """

    user: User | None = None
    nick: str | None = None
    avatar: str | None = None
    banner: str | None = None
    roles: list[Snowflake] | None = None
    joined_at: str | None = None
    premium_since: str | None = None
    deaf: bool = False
    mute: bool = False
    pending: bool = False
    permissions: Permissions = Permissions(0)
    communication_disabled_until: str | None = None
    flags: int = 0
    guild_id: Snowflake | None = None

    # Computed

    @property
    def id(self) -> Snowflake | None:
        return self.user.id if self.user else None

    @property
    def display_name(self) -> str:
        """Priority: server nick > global_name > username."""
        if self.nick:
            return self.nick
        if self.user:
            return self.user.display_name
        return "Unknown"

    @property
    def mention(self) -> str:
        if self.user:
            return self.user.mention
        return "<@0>"

    @property
    def is_boosting(self) -> bool:
        return self.premium_since is not None

    @property
    def is_pending(self) -> bool:
        """True if the member hasn't passed guild membership screening."""
        return self.pending

    @property
    def is_timed_out(self) -> bool:
        """True if this member is currently under a communication timeout."""
        if self.communication_disabled_until is None:
            return False
        try:
            until = datetime.fromisoformat(
                self.communication_disabled_until.replace("Z", "+00:00")
            )
            return until > datetime.now(timezone.utc)
        except (ValueError, AttributeError):
            return False

    @property
    def timeout_expires_at(self) -> datetime | None:
        """Datetime when the timeout expires, or ``None`` if not timed out."""
        if self.communication_disabled_until is None:
            return None
        try:
            return datetime.fromisoformat(
                self.communication_disabled_until.replace("Z", "+00:00")
            )
        except (ValueError, AttributeError):
            return None

    @property
    def joined_at_dt(self) -> datetime | None:
        if self.joined_at is None:
            return None
        try:
            return datetime.fromisoformat(self.joined_at.replace("Z", "+00:00"))
        except (ValueError, AttributeError):
            return None

    @property
    def premium_since_dt(self) -> datetime | None:
        if self.premium_since is None:
            return None
        try:
            return datetime.fromisoformat(self.premium_since.replace("Z", "+00:00"))
        except (ValueError, AttributeError):
            return None

    @property
    def created_at(self):
        return self.id.created_at if self.id else None

    # Role helpers

    def has_role(self, role_id: Snowflake | int) -> bool:
        """Check if the member holds a specific role."""
        if self.roles is None:
            return False
        target = int(role_id)
        return any(int(r) == target for r in self.roles)

    def has_any_role(self, *role_ids: Snowflake | int) -> bool:
        """Check if the member holds any of the given roles."""
        return any(self.has_role(r) for r in role_ids)

    def has_all_roles(self, *role_ids: Snowflake | int) -> bool:
        """Check if the member holds all of the given roles."""
        return all(self.has_role(r) for r in role_ids)

    @property
    def role_count(self) -> int:
        return len(self.roles) if self.roles else 0

    # Permission helpers

    def can(self, *perms: Permissions) -> bool:
        """Return True if the member's resolved permissions include all of *perms*."""
        return self.permissions.has(*perms)

    def can_any(self, *perms: Permissions) -> bool:
        """Return True if the member's resolved permissions include any of *perms*."""
        return self.permissions.has_any(*perms)

    # Avatar helpers

    def avatar_url_as(self, *, size: int = 1024, fmt: str | None = None) -> str | None:
        """Guild-specific avatar URL if set, otherwise falls back to the user avatar."""
        if self.avatar and self.guild_id:
            if fmt is None:
                fmt = "gif" if self.avatar.startswith("a_") else "png"
            return (
                f"https://cdn.discordapp.com/guilds/{self.guild_id}"
                f"/users/{self.id}/avatars/{self.avatar}.{fmt}?size={size}"
            )
        if self.user:
            return self.user.avatar_url_as(size=size, fmt=fmt)
        return None

    @property
    def avatar_url(self) -> str | None:
        return self.avatar_url_as(size=1024)

    # Construction

    @classmethod
    def from_payload(cls, data: dict[str, Any], *, guild_id: Snowflake | None = None) -> Self:
        user = User.from_payload(data["user"]) if "user" in data else None
        roles = [Snowflake(r) for r in data.get("roles", [])]
        perms = (
            Permissions.from_value(data["permissions"])
            if "permissions" in data else Permissions(0)
        )
        return cls(
            user=user,
            nick=data.get("nick"),
            avatar=data.get("avatar"),
            banner=data.get("banner"),
            roles=roles,
            joined_at=data.get("joined_at"),
            premium_since=data.get("premium_since"),
            deaf=data.get("deaf", False),
            mute=data.get("mute", False),
            pending=data.get("pending", False),
            permissions=perms,
            communication_disabled_until=data.get("communication_disabled_until"),
            flags=data.get("flags", 0),
            guild_id=guild_id,
        )

    def __repr__(self) -> str:
        return (
            f"Member(id={self.id}, nick={self.nick!r}, "
            f"roles={self.role_count}, guild={self.guild_id})"
        )
