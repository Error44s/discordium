"""Discord Guild (server) model — full v10 coverage."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import IntEnum
from typing import Any, Self

from .base import Model
from .enums import GuildFeature
from .snowflake import Snowflake


class VerificationLevel(IntEnum):
    NONE = 0
    LOW = 1
    MEDIUM = 2
    HIGH = 3
    VERY_HIGH = 4


class DefaultMessageNotifications(IntEnum):
    ALL_MESSAGES = 0
    ONLY_MENTIONS = 1


class ExplicitContentFilter(IntEnum):
    DISABLED = 0
    MEMBERS_WITHOUT_ROLES = 1
    ALL_MEMBERS = 2


class MFALevel(IntEnum):
    NONE = 0
    ELEVATED = 1


class NSFWLevel(IntEnum):
    DEFAULT = 0
    EXPLICIT = 1
    SAFE = 2
    AGE_RESTRICTED = 3


class PremiumTier(IntEnum):
    NONE = 0
    TIER_1 = 1
    TIER_2 = 2
    TIER_3 = 3


class SystemChannelFlags:
    """Bit constants for system_channel_flags."""
    SUPPRESS_JOIN_NOTIFICATIONS          = 1 << 0
    SUPPRESS_PREMIUM_SUBSCRIPTIONS       = 1 << 1
    SUPPRESS_GUILD_REMINDER_NOTIFICATIONS = 1 << 2
    SUPPRESS_JOIN_NOTIFICATION_REPLIES   = 1 << 3
    SUPPRESS_ROLE_SUBSCRIPTION_PURCHASE_NOTIFICATIONS = 1 << 4
    SUPPRESS_ROLE_SUBSCRIPTION_PURCHASE_NOTIFICATION_REPLIES = 1 << 5


class WelcomeScreenChannel(Model):
    """A single channel listed on a guild's welcome screen."""

    channel_id: Snowflake
    description: str
    emoji_id: Snowflake | None = None
    emoji_name: str | None = None

    @classmethod
    def from_payload(cls, data: dict[str, Any]) -> Self:
        return cls(
            channel_id=Snowflake(data["channel_id"]),
            description=data["description"],
            emoji_id=Snowflake(data["emoji_id"]) if data.get("emoji_id") else None,
            emoji_name=data.get("emoji_name"),
        )


class Guild(Model):
    """Represents a Discord guild (server) — full v10 field coverage.

    Attributes
    ----------
    id:
        Guild Snowflake.
    name:
        Guild name.
    icon / icon_hash:
        Icon hash (``icon_hash`` is the template variant).
    splash:
        Invite splash screen hash.
    discovery_splash:
        Discovery splash hash.
    owner_id:
        Snowflake of the guild owner.
    afk_channel_id:
        AFK voice channel.
    afk_timeout:
        AFK timeout in seconds.
    widget_enabled / widget_channel_id:
        Widget settings.
    verification_level:
        :class:`VerificationLevel`.
    default_message_notifications:
        :class:`DefaultMessageNotifications`.
    explicit_content_filter:
        :class:`ExplicitContentFilter`.
    features:
        List of enabled :class:`~discordium.models.enums.GuildFeature` strings.
    mfa_level:
        :class:`MFALevel`.
    system_channel_id:
        Channel that receives system messages.
    system_channel_flags:
        Bitmask controlling which system messages appear.
    rules_channel_id:
        Rules/guidelines channel for Community guilds.
    max_members:
        Maximum member count.
    vanity_url_code:
        Vanity invite code (if any).
    description:
        Community guild description.
    banner:
        Banner hash.
    premium_tier:
        :class:`PremiumTier` (Nitro boost level).
    premium_subscription_count:
        Number of boosts.
    preferred_locale:
        Primary locale tag (e.g. ``"en-US"``).
    public_updates_channel_id:
        Channel for Discord's official updates in Community guilds.
    max_video_channel_users:
        Max users in a video-enabled voice channel.
    approximate_member_count / approximate_presence_count:
        Estimates included when ``with_counts=True`` is requested.
    nsfw_level:
        :class:`NSFWLevel`.
    premium_progress_bar_enabled:
        Whether the boost progress bar is shown.
    member_count:
        Exact member count from gateway GUILD_CREATE (absent on REST).
    """

    id: Snowflake
    name: str
    icon: str | None = None
    icon_hash: str | None = None
    splash: str | None = None
    discovery_splash: str | None = None
    owner_id: Snowflake | None = None
    afk_channel_id: Snowflake | None = None
    afk_timeout: int = 300
    widget_enabled: bool = False
    widget_channel_id: Snowflake | None = None
    verification_level: int = 0
    default_message_notifications: int = 0
    explicit_content_filter: int = 0
    features: list[str] | None = None
    mfa_level: int = 0
    system_channel_id: Snowflake | None = None
    system_channel_flags: int = 0
    rules_channel_id: Snowflake | None = None
    max_members: int | None = None
    vanity_url_code: str | None = None
    description: str | None = None
    banner: str | None = None
    premium_tier: int = 0
    premium_subscription_count: int = 0
    preferred_locale: str = "en-US"
    public_updates_channel_id: Snowflake | None = None
    max_video_channel_users: int | None = None
    approximate_member_count: int | None = None
    approximate_presence_count: int | None = None
    nsfw_level: int = 0
    premium_progress_bar_enabled: bool = False
    member_count: int | None = None
    safety_alerts_channel_id: Snowflake | None = None

    # CDN helpers

    def icon_url_as(self, *, size: int = 1024, fmt: str | None = None) -> str | None:
        if self.icon is None:
            return None
        if fmt is None:
            fmt = "gif" if self.icon.startswith("a_") else "png"
        return f"https://cdn.discordapp.com/icons/{self.id}/{self.icon}.{fmt}?size={size}"

    @property
    def icon_url(self) -> str | None:
        return self.icon_url_as(size=1024)

    def banner_url(self, *, size: int = 1024, fmt: str = "webp") -> str | None:
        if self.banner is None:
            return None
        return f"https://cdn.discordapp.com/banners/{self.id}/{self.banner}.{fmt}?size={size}"

    def splash_url(self, *, size: int = 1024) -> str | None:
        if self.splash is None:
            return None
        return f"https://cdn.discordapp.com/splashes/{self.id}/{self.splash}.webp?size={size}"

    def discovery_splash_url(self, *, size: int = 1024) -> str | None:
        if self.discovery_splash is None:
            return None
        return f"https://cdn.discordapp.com/discovery-splashes/{self.id}/{self.discovery_splash}.webp?size={size}"

    # Computed

    @property
    def created_at(self):
        return self.id.created_at

    @property
    def boost_level(self) -> PremiumTier:
        try:
            return PremiumTier(self.premium_tier)
        except ValueError:
            return PremiumTier.NONE

    @property
    def is_community(self) -> bool:
        return "COMMUNITY" in (self.features or [])

    @property
    def is_partnered(self) -> bool:
        return "PARTNERED" in (self.features or [])

    @property
    def is_verified(self) -> bool:
        return "VERIFIED" in (self.features or [])

    @property
    def has_vanity_url(self) -> bool:
        return self.vanity_url_code is not None

    @property
    def vanity_url(self) -> str | None:
        if self.vanity_url_code:
            return f"https://discord.gg/{self.vanity_url_code}"
        return None

    def has_feature(self, feature: str | GuildFeature) -> bool:
        """Check whether a specific feature flag is enabled."""
        return str(feature) in (self.features or [])

    # Construction

    @classmethod
    def from_payload(cls, data: dict[str, Any]) -> Self:
        return cls(
            id=Snowflake(data["id"]),
            name=data["name"],
            icon=data.get("icon"),
            icon_hash=data.get("icon_hash"),
            splash=data.get("splash"),
            discovery_splash=data.get("discovery_splash"),
            owner_id=Snowflake(data["owner_id"]) if data.get("owner_id") else None,
            afk_channel_id=Snowflake(data["afk_channel_id"]) if data.get("afk_channel_id") else None,
            afk_timeout=data.get("afk_timeout", 300),
            widget_enabled=data.get("widget_enabled", False),
            widget_channel_id=Snowflake(data["widget_channel_id"]) if data.get("widget_channel_id") else None,
            verification_level=data.get("verification_level", 0),
            default_message_notifications=data.get("default_message_notifications", 0),
            explicit_content_filter=data.get("explicit_content_filter", 0),
            features=data.get("features"),
            mfa_level=data.get("mfa_level", 0),
            system_channel_id=Snowflake(data["system_channel_id"]) if data.get("system_channel_id") else None,
            system_channel_flags=data.get("system_channel_flags", 0),
            rules_channel_id=Snowflake(data["rules_channel_id"]) if data.get("rules_channel_id") else None,
            max_members=data.get("max_members"),
            vanity_url_code=data.get("vanity_url_code"),
            description=data.get("description"),
            banner=data.get("banner"),
            premium_tier=data.get("premium_tier", 0),
            premium_subscription_count=data.get("premium_subscription_count", 0),
            preferred_locale=data.get("preferred_locale", "en-US"),
            public_updates_channel_id=Snowflake(data["public_updates_channel_id"]) if data.get("public_updates_channel_id") else None,
            max_video_channel_users=data.get("max_video_channel_users"),
            approximate_member_count=data.get("approximate_member_count"),
            approximate_presence_count=data.get("approximate_presence_count"),
            nsfw_level=data.get("nsfw_level", 0),
            premium_progress_bar_enabled=data.get("premium_progress_bar_enabled", False),
            member_count=data.get("member_count"),
            safety_alerts_channel_id=Snowflake(data["safety_alerts_channel_id"]) if data.get("safety_alerts_channel_id") else None,
        )

    def __repr__(self) -> str:
        return f"Guild(id={self.id}, name={self.name!r}, members={self.member_count})"
