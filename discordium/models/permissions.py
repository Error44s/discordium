"""Discord permission bitfield system.

Composable with ``|`` and ``&``, checkable with ``in``::

    perms = Permissions.SEND_MESSAGES | Permissions.EMBED_LINKS
    if Permissions.SEND_MESSAGES in perms:
        ...

    # Check against a member's resolved permissions
    if member.permissions.has(Permissions.MANAGE_CHANNELS):
        ...
"""

from __future__ import annotations

from enum import IntFlag


class Permissions(IntFlag):
    """Complete Discord permission bitfield (API v10)."""

    CREATE_INSTANT_INVITE       = 1 << 0
    KICK_MEMBERS                = 1 << 1
    BAN_MEMBERS                 = 1 << 2
    ADMINISTRATOR               = 1 << 3
    MANAGE_CHANNELS             = 1 << 4
    MANAGE_GUILD                = 1 << 5
    ADD_REACTIONS               = 1 << 6
    VIEW_AUDIT_LOG              = 1 << 7
    PRIORITY_SPEAKER            = 1 << 8
    STREAM                      = 1 << 9
    VIEW_CHANNEL                = 1 << 10
    SEND_MESSAGES               = 1 << 11
    SEND_TTS_MESSAGES           = 1 << 12
    MANAGE_MESSAGES             = 1 << 13
    EMBED_LINKS                 = 1 << 14
    ATTACH_FILES                = 1 << 15
    READ_MESSAGE_HISTORY        = 1 << 16
    MENTION_EVERYONE            = 1 << 17
    USE_EXTERNAL_EMOJIS         = 1 << 18
    VIEW_GUILD_INSIGHTS         = 1 << 19
    CONNECT                     = 1 << 20
    SPEAK                       = 1 << 21
    MUTE_MEMBERS                = 1 << 22
    DEAFEN_MEMBERS              = 1 << 23
    MOVE_MEMBERS                = 1 << 24
    USE_VAD                     = 1 << 25
    CHANGE_NICKNAME             = 1 << 26
    MANAGE_NICKNAMES            = 1 << 27
    MANAGE_ROLES                = 1 << 28
    MANAGE_WEBHOOKS             = 1 << 29
    MANAGE_GUILD_EXPRESSIONS    = 1 << 30
    USE_APPLICATION_COMMANDS    = 1 << 31
    REQUEST_TO_SPEAK            = 1 << 32
    MANAGE_EVENTS               = 1 << 33
    MANAGE_THREADS              = 1 << 34
    CREATE_PUBLIC_THREADS       = 1 << 35
    CREATE_PRIVATE_THREADS      = 1 << 36
    USE_EXTERNAL_STICKERS       = 1 << 37
    SEND_MESSAGES_IN_THREADS    = 1 << 38
    USE_EMBEDDED_ACTIVITIES     = 1 << 39
    MODERATE_MEMBERS            = 1 << 40
    VIEW_CREATOR_MONETIZATION   = 1 << 41
    USE_SOUNDBOARD              = 1 << 42
    CREATE_GUILD_EXPRESSIONS    = 1 << 43
    CREATE_EVENTS               = 1 << 44
    USE_EXTERNAL_SOUNDS         = 1 << 45
    SEND_VOICE_MESSAGES         = 1 << 46
    SEND_POLLS                  = 1 << 49
    USE_EXTERNAL_APPS           = 1 << 50

    # Presets

    @classmethod
    def all_channel(cls) -> Permissions:
        """All channel-level permissions."""
        return cls(
            cls.VIEW_CHANNEL | cls.MANAGE_CHANNELS | cls.MANAGE_ROLES
            | cls.CREATE_INSTANT_INVITE | cls.SEND_MESSAGES
            | cls.SEND_MESSAGES_IN_THREADS | cls.CREATE_PUBLIC_THREADS
            | cls.CREATE_PRIVATE_THREADS | cls.EMBED_LINKS | cls.ATTACH_FILES
            | cls.ADD_REACTIONS | cls.USE_EXTERNAL_EMOJIS
            | cls.MENTION_EVERYONE | cls.MANAGE_MESSAGES
            | cls.READ_MESSAGE_HISTORY | cls.SEND_TTS_MESSAGES
            | cls.MANAGE_THREADS
        )

    @classmethod
    def text(cls) -> Permissions:
        """Common text-channel permissions."""
        return cls(
            cls.VIEW_CHANNEL | cls.SEND_MESSAGES | cls.EMBED_LINKS
            | cls.ATTACH_FILES | cls.ADD_REACTIONS | cls.READ_MESSAGE_HISTORY
            | cls.USE_EXTERNAL_EMOJIS
        )

    @classmethod
    def voice(cls) -> Permissions:
        """Common voice-channel permissions."""
        return cls(
            cls.VIEW_CHANNEL | cls.CONNECT | cls.SPEAK | cls.STREAM
            | cls.USE_VAD
        )

    @classmethod
    def moderator(cls) -> Permissions:
        """Typical moderator permissions."""
        return cls(
            cls.KICK_MEMBERS | cls.BAN_MEMBERS | cls.MANAGE_MESSAGES
            | cls.MODERATE_MEMBERS | cls.MANAGE_THREADS | cls.VIEW_AUDIT_LOG
            | cls.MANAGE_NICKNAMES
        )

    # Helpers

    def has(self, *perms: Permissions) -> bool:
        """Check if this bitfield has ALL specified permissions.

        Administrator always returns True.
        """
        if self & Permissions.ADMINISTRATOR:
            return True
        for perm in perms:
            if not (self & perm):
                return False
        return True

    def has_any(self, *perms: Permissions) -> bool:
        """Check if this bitfield has ANY of the specified permissions."""
        if self & Permissions.ADMINISTRATOR:
            return True
        return any(self & perm for perm in perms)

    @classmethod
    def from_value(cls, value: int | str) -> Permissions:
        """Parse from an int or string (Discord sends permissions as strings)."""
        return cls(int(value))


class PermissionOverwrite:
    """A channel-level permission overwrite for a role or member.

    Attributes
    ----------
    id:
        The role or user ID this overwrite targets.
    type:
        0 for role, 1 for member.
    allow:
        Explicitly allowed permissions.
    deny:
        Explicitly denied permissions.
    """

    __slots__ = ("id", "type", "allow", "deny")

    def __init__(
        self,
        id: int | str,
        type: int,
        allow: int | str = 0,
        deny: int | str = 0,
    ) -> None:
        self.id = int(id)
        self.type = type
        self.allow = Permissions.from_value(allow)
        self.deny = Permissions.from_value(deny)

    def to_dict(self) -> dict[str, str | int]:
        return {
            "id": str(self.id),
            "type": self.type,
            "allow": str(int(self.allow)),
            "deny": str(int(self.deny)),
        }

    @classmethod
    def from_payload(cls, data: dict) -> PermissionOverwrite:
        return cls(
            id=data["id"],
            type=data["type"],
            allow=data.get("allow", 0),
            deny=data.get("deny", 0),
        )

    def __repr__(self) -> str:
        kind = "role" if self.type == 0 else "member"
        return f"PermissionOverwrite({kind}:{self.id} allow={int(self.allow)} deny={int(self.deny)})"
