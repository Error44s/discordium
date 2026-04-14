"""Gateway Intents as a composable bitfield."""

from __future__ import annotations

from enum import IntFlag


class Intents(IntFlag):
    """Discord Gateway Intents.

    Compose with ``|``::

        intents = Intents.GUILDS | Intents.GUILD_MESSAGES | Intents.MESSAGE_CONTENT
    """

    GUILDS                    = 1 << 0
    GUILD_MEMBERS             = 1 << 1   # privileged
    GUILD_MODERATION          = 1 << 2
    GUILD_EXPRESSIONS         = 1 << 3
    GUILD_INTEGRATIONS        = 1 << 4
    GUILD_WEBHOOKS            = 1 << 5
    GUILD_INVITES             = 1 << 6
    GUILD_VOICE_STATES        = 1 << 7
    GUILD_PRESENCES           = 1 << 8   # privileged
    GUILD_MESSAGES            = 1 << 9
    GUILD_MESSAGE_REACTIONS   = 1 << 10
    GUILD_MESSAGE_TYPING      = 1 << 11
    DIRECT_MESSAGES           = 1 << 12
    DIRECT_MESSAGE_REACTIONS  = 1 << 13
    DIRECT_MESSAGE_TYPING     = 1 << 14
    MESSAGE_CONTENT           = 1 << 15  # privileged
    GUILD_SCHEDULED_EVENTS    = 1 << 16
    AUTO_MODERATION_CONFIG    = 1 << 20
    AUTO_MODERATION_EXECUTION = 1 << 21

    # Presets

    @classmethod
    def default(cls) -> Intents:
        """All non-privileged intents."""
        return cls(
            cls.GUILDS
            | cls.GUILD_MODERATION
            | cls.GUILD_EXPRESSIONS
            | cls.GUILD_INTEGRATIONS
            | cls.GUILD_WEBHOOKS
            | cls.GUILD_INVITES
            | cls.GUILD_VOICE_STATES
            | cls.GUILD_MESSAGES
            | cls.GUILD_MESSAGE_REACTIONS
            | cls.GUILD_MESSAGE_TYPING
            | cls.DIRECT_MESSAGES
            | cls.DIRECT_MESSAGE_REACTIONS
            | cls.DIRECT_MESSAGE_TYPING
            | cls.GUILD_SCHEDULED_EVENTS
            | cls.AUTO_MODERATION_CONFIG
            | cls.AUTO_MODERATION_EXECUTION
        )

    @classmethod
    def all(cls) -> Intents:
        """Every intent including privileged ones."""
        result = cls(0)
        for member in cls:
            result |= member
        return result

    @classmethod
    def privileged(cls) -> Intents:
        """Only privileged intents."""
        return cls(cls.GUILD_MEMBERS | cls.GUILD_PRESENCES | cls.MESSAGE_CONTENT)

    @classmethod
    def none(cls) -> Intents:
        """No intents."""
        return cls(0)
