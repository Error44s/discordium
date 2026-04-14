"""Typed event name constants for the discordium event system.

Instead of raw strings, use these literals for full IDE support and
zero risk of typos::

    from discordium.models.event_names import EventName

    @bot.on_event(EventName.MESSAGE_CREATE)
    async def on_msg(event: MessageCreateEvent) -> None: ...

All values match the Discord gateway dispatch event names (lowercase).
"""

from __future__ import annotations

from typing import Final, Literal

# Literal type for exhaustive type-checking

EventName = Literal[
    "ready",
    "resumed",
    "message_create",
    "message_update",
    "message_delete",
    "message_delete_bulk",
    "message_reaction_add",
    "message_reaction_remove",
    "guild_create",
    "guild_update",
    "guild_delete",
    "guild_ban_add",
    "guild_ban_remove",
    "guild_member_add",
    "guild_member_remove",
    "guild_member_update",
    "channel_create",
    "channel_update",
    "channel_delete",
    "guild_role_create",
    "guild_role_update",
    "guild_role_delete",
    "thread_create",
    "thread_update",
    "thread_delete",
    "interaction_create",
    "typing_start",
    "presence_update",
    "voice_state_update",
    "invite_create",
    "invite_delete",
]
"""Union of all valid Discord gateway event name strings.

Use as a type annotation wherever an event name string is accepted::

    def on_event(self, event: EventName) -> ...: ...
"""


class Events:
    """Namespace of event name constants.

    Avoids magic strings in your own code::

        bot.on_event(Events.MESSAGE_CREATE)   # "message_create"
        bot.on_event(Events.INTERACTION_CREATE)  # "interaction_create"
    """

    READY: Final = "ready"
    RESUMED: Final = "resumed"

    # Messages
    MESSAGE_CREATE: Final = "message_create"
    MESSAGE_UPDATE: Final = "message_update"
    MESSAGE_DELETE: Final = "message_delete"
    MESSAGE_DELETE_BULK: Final = "message_delete_bulk"
    MESSAGE_REACTION_ADD: Final = "message_reaction_add"
    MESSAGE_REACTION_REMOVE: Final = "message_reaction_remove"

    # Guilds
    GUILD_CREATE: Final = "guild_create"
    GUILD_UPDATE: Final = "guild_update"
    GUILD_DELETE: Final = "guild_delete"
    GUILD_BAN_ADD: Final = "guild_ban_add"
    GUILD_BAN_REMOVE: Final = "guild_ban_remove"

    # Members
    GUILD_MEMBER_ADD: Final = "guild_member_add"
    GUILD_MEMBER_REMOVE: Final = "guild_member_remove"
    GUILD_MEMBER_UPDATE: Final = "guild_member_update"

    # Channels
    CHANNEL_CREATE: Final = "channel_create"
    CHANNEL_UPDATE: Final = "channel_update"
    CHANNEL_DELETE: Final = "channel_delete"

    # Roles
    GUILD_ROLE_CREATE: Final = "guild_role_create"
    GUILD_ROLE_UPDATE: Final = "guild_role_update"
    GUILD_ROLE_DELETE: Final = "guild_role_delete"

    # Threads
    THREAD_CREATE: Final = "thread_create"
    THREAD_UPDATE: Final = "thread_update"
    THREAD_DELETE: Final = "thread_delete"

    # Interactions
    INTERACTION_CREATE: Final = "interaction_create"

    # Presence & Voice
    TYPING_START: Final = "typing_start"
    PRESENCE_UPDATE: Final = "presence_update"
    VOICE_STATE_UPDATE: Final = "voice_state_update"

    # Invites
    INVITE_CREATE: Final = "invite_create"
    INVITE_DELETE: Final = "invite_delete"
