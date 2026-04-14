"""Discord User model — full v10 coverage."""

from __future__ import annotations

from enum import IntFlag
from typing import Any, Self

from .base import Model
from .snowflake import Snowflake


class UserFlags(IntFlag):
    """Public user flags (shown as badges on profiles)."""
    STAFF                         = 1 << 0
    PARTNER                       = 1 << 1
    HYPESQUAD                     = 1 << 2
    BUG_HUNTER_LEVEL_1            = 1 << 3
    HYPESQUAD_ONLINE_HOUSE_1      = 1 << 6   # Bravery
    HYPESQUAD_ONLINE_HOUSE_2      = 1 << 7   # Brilliance
    HYPESQUAD_ONLINE_HOUSE_3      = 1 << 8   # Balance
    PREMIUM_EARLY_SUPPORTER       = 1 << 9
    TEAM_PSEUDO_USER              = 1 << 10
    BUG_HUNTER_LEVEL_2            = 1 << 14
    VERIFIED_BOT                  = 1 << 16
    VERIFIED_DEVELOPER            = 1 << 17
    CERTIFIED_MODERATOR           = 1 << 18
    BOT_HTTP_INTERACTIONS         = 1 << 19  # bot uses interactions endpoint only
    ACTIVE_DEVELOPER              = 1 << 22


class PremiumType(int):
    """Nitro subscription type constants."""
    NONE = 0
    NITRO_CLASSIC = 1
    NITRO = 2
    NITRO_BASIC = 3


class User(Model):
    """Represents a Discord user (bot or human).

    Attributes
    ----------
    id:
        User Snowflake.
    username:
        Base username (unique, no discriminator since pomelo migration).
    discriminator:
        Legacy 4-digit tag; ``"0"`` for migrated accounts.
    global_name:
        Display name set by the user (distinct from server nicknames).
    avatar:
        Avatar hash (``None`` = default avatar).
    bot:
        Whether this is a bot account.
    system:
        Whether this is an official Discord system user.
    mfa_enabled:
        Whether the user has 2FA enabled (only present for the current user).
    banner:
        Banner hash (Nitro feature).
    accent_color:
        Profile accent colour as an integer RGB value.
    locale:
        User's chosen language (only present for the current user).
    premium_type:
        Nitro subscription tier (only present for the current user).
    public_flags:
        Public badge flags bitfield.
    avatar_decoration_data:
        Avatar decoration asset hash and SKU ID (if any).
    """

    id: Snowflake
    username: str
    discriminator: str = "0"
    global_name: str | None = None
    avatar: str | None = None
    bot: bool = False
    system: bool = False
    mfa_enabled: bool = False
    banner: str | None = None
    accent_color: int | None = None
    locale: str | None = None
    premium_type: int = 0
    public_flags: int = 0
    avatar_decoration_data: dict[str, Any] | None = None

    # Computed

    @property
    def display_name(self) -> str:
        """Global name if set, otherwise username."""
        return self.global_name or self.username

    @property
    def tag(self) -> str:
        """``username#discriminator`` for legacy accounts, ``@username`` for pomelo."""
        if self.discriminator and self.discriminator != "0":
            return f"{self.username}#{self.discriminator}"
        return f"@{self.username}"

    @property
    def mention(self) -> str:
        return f"<@{self.id}>"

    @property
    def is_migrated(self) -> bool:
        """True for pomelo (discriminator-free) accounts."""
        return self.discriminator in ("", "0")

    @property
    def flags(self) -> UserFlags:
        return UserFlags(self.public_flags)

    @property
    def has_nitro(self) -> bool:
        return self.premium_type > 0

    # CDN helpers

    def avatar_url_as(self, *, size: int = 1024, fmt: str | None = None) -> str | None:
        """Return the user's avatar CDN URL, or ``None`` if no custom avatar is set."""
        if self.avatar is None:
            return None
        if fmt is None:
            fmt = "gif" if self.avatar.startswith("a_") else "png"
        return f"https://cdn.discordapp.com/avatars/{self.id}/{self.avatar}.{fmt}?size={size}"

    @property
    def avatar_url(self) -> str | None:
        """Default avatar CDN URL, or ``None`` if no custom avatar is set."""
        if self.avatar is None:
            return None
        fmt = "gif" if self.avatar.startswith("a_") else "png"
        return f"https://cdn.discordapp.com/avatars/{self.id}/{self.avatar}.{fmt}"

    def banner_url_as(self, *, size: int = 1024, fmt: str | None = None) -> str | None:
        """Return the user's banner URL, or ``None`` if they have none."""
        if self.banner is None:
            return None
        if fmt is None:
            fmt = "gif" if self.banner.startswith("a_") else "webp"
        return f"https://cdn.discordapp.com/banners/{self.id}/{self.banner}.{fmt}?size={size}"

    @property
    def banner_url(self, *, size: int = 1024, fmt: str | None = None) -> str | None:
        return self.banner_url_as(size=size, fmt=fmt)

    @property
    def default_avatar_url(self) -> str:
        index = (int(self.id) >> 22) % 6 if self.is_migrated else int(self.discriminator) % 5
        return f"https://cdn.discordapp.com/embed/avatars/{index}.png"

    @property
    def created_at(self):
        return self.id.created_at

    @property
    def accent_color_hex(self) -> str | None:
        if self.accent_color is None:
            return None
        return f"#{self.accent_color:06x}"

    # Construction

    @classmethod
    def from_payload(cls, data: dict[str, Any]) -> Self:
        return cls(
            id=Snowflake(data["id"]),
            username=data["username"],
            discriminator=data.get("discriminator", "0"),
            global_name=data.get("global_name"),
            avatar=data.get("avatar"),
            bot=data.get("bot", False),
            system=data.get("system", False),
            mfa_enabled=data.get("mfa_enabled", False),
            banner=data.get("banner"),
            accent_color=data.get("accent_color"),
            locale=data.get("locale"),
            premium_type=data.get("premium_type", 0),
            public_flags=data.get("public_flags", 0),
            avatar_decoration_data=data.get("avatar_decoration_data"),
        )

    def __repr__(self) -> str:
        return f"User(id={self.id}, tag={self.tag!r})"
