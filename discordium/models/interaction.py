"""Discord Interaction model — the core of slash commands and component callbacks.

Interactions are received via the gateway (or webhook) and must be responded to
within 3 seconds. This module provides the ``Interaction`` model and typed
response helpers.

Response flow::

    @bot.on_interaction("ping")
    async def handle_ping(inter: Interaction) -> None:
        await inter.respond("Pong! 🏓")

    # Deferred response (for long operations):
    await inter.defer()
    # ... do work ...
    await inter.followup("Done!")
"""

from __future__ import annotations

from enum import IntEnum
from typing import TYPE_CHECKING, Any

from .snowflake import Snowflake
from .user import User
from .member import Member

if TYPE_CHECKING:
    from ..http.rest import RESTClient
    from .components import Modal
    from .embed import Embed


class InteractionType(IntEnum):
    PING = 1
    APPLICATION_COMMAND = 2
    MESSAGE_COMPONENT = 3
    APPLICATION_COMMAND_AUTOCOMPLETE = 4
    MODAL_SUBMIT = 5


class InteractionCallbackType(IntEnum):
    PONG = 1
    CHANNEL_MESSAGE_WITH_SOURCE = 4
    DEFERRED_CHANNEL_MESSAGE = 5
    DEFERRED_UPDATE_MESSAGE = 6
    UPDATE_MESSAGE = 7
    APPLICATION_COMMAND_AUTOCOMPLETE_RESULT = 8
    MODAL = 9


class ResolvedData:
    """Resolved entities attached to an interaction.

    Discord resolves all entity IDs referenced by command options and
    embeds them here as partial objects. This class provides typed
    accessors that parse those raw dicts into proper model objects.

    Attributes
    ----------
    users:
        Raw user dicts keyed by snowflake string.
    members:
        Raw member dicts keyed by snowflake string (no ``user`` sub-key —
        merge with ``users`` when constructing a full Member).
    roles:
        Raw role dicts keyed by snowflake string.
    channels:
        Partial channel dicts keyed by snowflake string.
    messages:
        Partial message dicts keyed by snowflake string.
    attachments:
        Attachment dicts keyed by snowflake string.
    """

    __slots__ = ("users", "members", "roles", "channels", "messages", "attachments", "_guild_id")

    def __init__(self, data: dict[str, Any] | None = None, *, guild_id: Snowflake | None = None) -> None:
        data = data or {}
        self.users: dict[str, dict[str, Any]] = data.get("users", {})
        self.members: dict[str, dict[str, Any]] = data.get("members", {})
        self.roles: dict[str, dict[str, Any]] = data.get("roles", {})
        self.channels: dict[str, dict[str, Any]] = data.get("channels", {})
        self.messages: dict[str, dict[str, Any]] = data.get("messages", {})
        self.attachments: dict[str, dict[str, Any]] = data.get("attachments", {})
        self._guild_id = guild_id

    # Typed accessors

    def get_user(self, user_id: str | int) -> User | None:
        """Return a parsed :class:`~discordium.models.user.User` for *user_id*."""
        raw = self.users.get(str(user_id))
        return User.from_payload(raw) if raw else None

    def get_member(self, user_id: str | int) -> Any | None:
        """Return a parsed :class:`~discordium.models.member.Member` for *user_id*.

        The member's ``user`` sub-object is merged in from :attr:`users`.
        """
        from .member import Member
        raw = self.members.get(str(user_id))
        if raw is None:
            return None
        # Discord omits the user sub-key in resolved members — inject it.
        merged = dict(raw)
        user_raw = self.users.get(str(user_id))
        if user_raw and "user" not in merged:
            merged["user"] = user_raw
        return Member.from_payload(merged, guild_id=self._guild_id)

    def get_role(self, role_id: str | int) -> Any | None:
        """Return a parsed :class:`~discordium.models.role.Role` for *role_id*."""
        from .role import Role
        raw = self.roles.get(str(role_id))
        return Role.from_payload(raw) if raw else None

    def get_channel(self, channel_id: str | int) -> Any | None:
        """Return a parsed :class:`~discordium.models.channel.Channel` for *channel_id*."""
        from .channel import Channel
        raw = self.channels.get(str(channel_id))
        return Channel.from_payload(raw) if raw else None

    def get_message(self, message_id: str | int) -> Any | None:
        """Return a parsed :class:`~discordium.models.message.Message` for *message_id*."""
        from .message import Message
        raw = self.messages.get(str(message_id))
        return Message.from_payload(raw) if raw else None

    def get_attachment(self, attachment_id: str | int) -> Any | None:
        """Return a parsed :class:`~discordium.models.message.Attachment` for *attachment_id*."""
        from .message import Attachment
        raw = self.attachments.get(str(attachment_id))
        return Attachment.from_payload(raw) if raw else None

    # Bulk accessors

    def all_users(self) -> list[User]:
        """Return all resolved users as typed objects."""
        return [User.from_payload(v) for v in self.users.values()]

    def all_roles(self) -> list[Any]:
        """Return all resolved roles as typed objects."""
        from .role import Role
        return [Role.from_payload(v) for v in self.roles.values()]

    def all_channels(self) -> list[Any]:
        """Return all resolved channels as typed objects."""
        from .channel import Channel
        return [Channel.from_payload(v) for v in self.channels.values()]

    def all_members(self) -> list[Any]:
        """Return all resolved members as typed objects (with merged user data)."""
        return [self.get_member(uid) for uid in self.members] 


class InteractionOption:
    """A single option/argument from a slash command invocation."""

    __slots__ = ("name", "type", "value", "options", "focused")

    def __init__(self, data: dict[str, Any]) -> None:
        self.name: str = data["name"]
        self.type: int = data["type"]
        self.value: Any = data.get("value")
        self.focused: bool = data.get("focused", False)
        self.options: list[InteractionOption] = [
            InteractionOption(o) for o in data.get("options", [])
        ]

    def get(self, name: str) -> InteractionOption | None:
        """Find a sub-option by name."""
        for opt in self.options:
            if opt.name == name:
                return opt
        return None


class Interaction:
    """Represents a Discord interaction.

    This is the central object for slash commands, button clicks,
    select menu choices, and modal submissions.
    """

    __slots__ = (
        "id", "application_id", "type", "guild_id", "channel_id",
        "member", "user", "token", "data", "message_data",
        "locale", "guild_locale", "command_name", "custom_id",
        "options", "values", "resolved", "component_type",
        "app_permissions",
        "_rest", "_responded", "_deferred",
    )

    def __init__(self, payload: dict[str, Any], *, rest: RESTClient) -> None:
        self.id = Snowflake(payload["id"])
        self.application_id = Snowflake(payload["application_id"])
        self.type = InteractionType(payload["type"])
        self.token: str = payload["token"]
        self._rest = rest
        self._responded = False
        self._deferred = False

        self.guild_id = Snowflake(payload["guild_id"]) if payload.get("guild_id") else None
        self.channel_id = Snowflake(payload["channel_id"]) if payload.get("channel_id") else None
        self.locale: str = payload.get("locale", "en-US")
        self.guild_locale: str = payload.get("guild_locale", "en-US")

        # app_permissions: bot's effective permissions in the invoking channel.
        # Discord computes this server-side including channel overrides.
        # Only present for guild interactions (None in DMs).
        raw_ap = payload.get("app_permissions")
        self.app_permissions: int | None = int(raw_ap) if raw_ap is not None else None

        # Parse member/user
        if "member" in payload:
            self.member = Member.from_payload(payload["member"], guild_id=self.guild_id)
            self.user = self.member.user
        elif "user" in payload:
            self.user = User.from_payload(payload["user"])
            self.member = None
        else:
            self.user = None
            self.member = None

        # Parse interaction data
        idata = payload.get("data", {})
        self.data = idata
        self.message_data = payload.get("message")
        self.command_name: str | None = idata.get("name")
        self.custom_id: str | None = idata.get("custom_id")
        self.values: list[str] = idata.get("values", [])
        self.component_type: int | None = idata.get("component_type")
        self.resolved = ResolvedData(idata.get("resolved"))

        # Parse options
        self.options: list[InteractionOption] = [
            InteractionOption(o) for o in idata.get("options", [])
        ]

    # Low-level option access

    def get_option(self, name: str) -> Any:
        """Get a command option's raw value by name. Returns None if not found."""
        for opt in self.options:
            if opt.name == name:
                return opt.value
            for sub in opt.options:
                if sub.name == name:
                    return sub.value
        return None

    def get_subcommand(self) -> str | None:
        """Get the subcommand name, if this is a subcommand invocation."""
        for opt in self.options:
            if opt.type in (1, 2):
                return opt.name
        return None

    def get_subcommand_options(self) -> list[InteractionOption]:
        """Get options of the invoked subcommand."""
        for opt in self.options:
            if opt.type in (1, 2):
                return opt.options
        return []

    # High-level typed option resolvers
    #
    # These return properly typed values and auto-resolve snowflakes
    # into full model objects where possible.

    def option_string(self, name: str, *, default: str | None = None) -> str | None:
        """Get a string option value::

            greeting = inter.option_string("message", default="Hello!")
        """
        val = self.get_option(name)
        return str(val) if val is not None else default

    def option_int(self, name: str, *, default: int | None = None) -> int | None:
        """Get an integer option value::

            duration = inter.option_int("minutes", default=5)
        """
        val = self.get_option(name)
        return int(val) if val is not None else default

    def option_float(self, name: str, *, default: float | None = None) -> float | None:
        """Get a number (float) option value."""
        val = self.get_option(name)
        return float(val) if val is not None else default

    def option_bool(self, name: str, *, default: bool | None = None) -> bool | None:
        """Get a boolean option value."""
        val = self.get_option(name)
        return bool(val) if val is not None else default

    def option_user(self, name: str) -> User | None:
        """Get a user option, resolved to a full User object::

            target = inter.option_user("user")
            if target:
                await inter.respond(f"Selected: {target.display_name}")
        """
        val = self.get_option(name)
        if val is None:
            return None
        return self.resolved.get_user(str(val))

    def option_member(self, name: str) -> Member | None:
        """Get a user option, resolved to a full Member object (guild context)."""
        val = self.get_option(name)
        if val is None:
            return None
        raw = self.resolved.members.get(str(val))
        if raw is None:
            return None
        # Members from resolved data don't include user — merge it
        user_raw = self.resolved.users.get(str(val))
        if user_raw:
            raw = {**raw, "user": user_raw}
        return Member.from_payload(raw, guild_id=self.guild_id)

    def option_role(self, name: str) -> dict[str, Any] | None:
        """Get a role option, resolved to role data."""
        val = self.get_option(name)
        if val is None:
            return None
        return self.resolved.roles.get(str(val))

    def option_channel(self, name: str) -> dict[str, Any] | None:
        """Get a channel option, resolved to channel data."""
        val = self.get_option(name)
        if val is None:
            return None
        return self.resolved.channels.get(str(val))

    def option_snowflake(self, name: str) -> Snowflake | None:
        """Get any option value as a Snowflake (for user/role/channel/mentionable)."""
        val = self.get_option(name)
        if val is None:
            return None
        return Snowflake(val)

    # Modal field access

    def get_field(self, custom_id: str) -> str | None:
        """Get a modal text input value by custom_id::

            feedback = inter.get_field("feedback_text")
        """
        for component_row in self.data.get("components", []):
            for component in component_row.get("components", []):
                if component.get("custom_id") == custom_id:
                    return component.get("value")
        return None

    def get_all_fields(self) -> dict[str, str]:
        """Get all modal field values as a dict of ``{custom_id: value}``::

            fields = inter.get_all_fields()
            title = fields.get("title", "")
            body = fields.get("body", "")
        """
        result: dict[str, str] = {}
        for component_row in self.data.get("components", []):
            for component in component_row.get("components", []):
                cid = component.get("custom_id")
                if cid:
                    result[cid] = component.get("value", "")
        return result

    # State helpers

    @property
    def has_responded(self) -> bool:
        """Whether this interaction has already been responded to."""
        return self._responded

    @property
    def is_deferred(self) -> bool:
        """Whether this interaction was deferred."""
        return self._deferred

    @property
    def is_command(self) -> bool:
        """Whether this is a slash command interaction."""
        return self.type == InteractionType.APPLICATION_COMMAND

    @property
    def is_component(self) -> bool:
        """Whether this is a component interaction (button, select, etc.)."""
        return self.type == InteractionType.MESSAGE_COMPONENT

    @property
    def is_modal(self) -> bool:
        """Whether this is a modal submit interaction."""
        return self.type == InteractionType.MODAL_SUBMIT

    @property
    def is_autocomplete(self) -> bool:
        """Whether this is an autocomplete interaction."""
        return self.type == InteractionType.APPLICATION_COMMAND_AUTOCOMPLETE

    @property
    def author(self) -> User | None:
        """Alias for ``self.user`` — consistent with Message.author."""
        return self.user

    # Response methods

    async def respond(
        self,
        content: str | None = None,
        *,
        embed: Embed | None = None,
        embeds: list[Embed] | None = None,
        components: list[Any] | None = None,
        ephemeral: bool = False,
        tts: bool = False,
    ) -> None:
        """Send an immediate response to the interaction.

        Raises
        ------
        InteractionAlreadyResponded:
            If this interaction has already received an initial response.
        """
        from ..errors import InteractionAlreadyResponded

        if self._responded:
            raise InteractionAlreadyResponded(
                "This interaction has already been responded to. "
                "Use followup() for additional messages, or edit_response() to modify."
            )

        data: dict[str, Any] = {}
        if content is not None:
            data["content"] = content
        if embed is not None:
            data["embeds"] = [embed.to_dict()]
        elif embeds:
            data["embeds"] = [e.to_dict() for e in embeds]
        if components:
            data["components"] = [c.to_dict() for c in components]
        if ephemeral:
            data["flags"] = 64  # EPHEMERAL
        if tts:
            data["tts"] = True

        await self._rest.request(
            "POST",
            f"/interactions/{self.id}/{self.token}/callback",
            json={
                "type": InteractionCallbackType.CHANNEL_MESSAGE_WITH_SOURCE,
                "data": data,
            },
        )
        self._responded = True

    async def defer(self, *, ephemeral: bool = False, update: bool = False) -> None:
        """Acknowledge the interaction — you have 15 minutes to follow up.

        Parameters
        ----------
        ephemeral:
            Whether the eventual response is ephemeral.
        update:
            If True, defers as an update to an existing message (for components).

        Raises
        ------
        InteractionAlreadyResponded:
            If this interaction has already been responded to.
        """
        from ..errors import InteractionAlreadyResponded

        if self._responded:
            raise InteractionAlreadyResponded(
                "This interaction has already been responded to. Cannot defer again."
            )

        cb_type = (
            InteractionCallbackType.DEFERRED_UPDATE_MESSAGE
            if update
            else InteractionCallbackType.DEFERRED_CHANNEL_MESSAGE
        )
        data: dict[str, Any] = {}
        if ephemeral:
            data["flags"] = 64

        await self._rest.request(
            "POST",
            f"/interactions/{self.id}/{self.token}/callback",
            json={"type": cb_type, "data": data} if data else {"type": cb_type},
        )
        self._responded = True
        self._deferred = True

    async def followup(
        self,
        content: str | None = None,
        *,
        embed: Embed | None = None,
        embeds: list[Embed] | None = None,
        components: list[Any] | None = None,
        ephemeral: bool = False,
    ) -> dict[str, Any]:
        """Send a follow-up message after responding or deferring.

        Raises
        ------
        InteractionNotResponded:
            If the interaction has not been responded to or deferred yet.
        """
        from ..errors import InteractionNotResponded

        if not self._responded:
            raise InteractionNotResponded(
                "Cannot send followup before responding or deferring. "
                "Call respond() or defer() first."
            )

        payload: dict[str, Any] = {}
        if content is not None:
            payload["content"] = content
        if embed is not None:
            payload["embeds"] = [embed.to_dict()]
        elif embeds:
            payload["embeds"] = [e.to_dict() for e in embeds]
        if components:
            payload["components"] = [c.to_dict() for c in components]
        if ephemeral:
            payload["flags"] = 64

        return await self._rest.request(
            "POST",
            f"/webhooks/{self.application_id}/{self.token}",
            json=payload,
        )

    async def edit_response(
        self,
        content: str | None = None,
        *,
        embed: Embed | None = None,
        embeds: list[Embed] | None = None,
        components: list[Any] | None = None,
    ) -> None:
        """Edit the original interaction response.

        Raises
        ------
        InteractionNotResponded:
            If the interaction has not been responded to yet.
        """
        from ..errors import InteractionNotResponded

        if not self._responded:
            raise InteractionNotResponded(
                "Cannot edit response before responding or deferring."
            )

        payload: dict[str, Any] = {}
        if content is not None:
            payload["content"] = content
        if embed is not None:
            payload["embeds"] = [embed.to_dict()]
        elif embeds:
            payload["embeds"] = [e.to_dict() for e in embeds]
        if components:
            payload["components"] = [c.to_dict() for c in components]

        await self._rest.request(
            "PATCH",
            f"/webhooks/{self.application_id}/{self.token}/messages/@original",
            json=payload,
        )

    async def delete_response(self) -> None:
        """Delete the original interaction response.

        Raises
        ------
        InteractionNotResponded:
            If the interaction has not been responded to yet.
        """
        from ..errors import InteractionNotResponded

        if not self._responded:
            raise InteractionNotResponded(
                "Cannot delete response before responding or deferring."
            )

        await self._rest.request(
            "DELETE",
            f"/webhooks/{self.application_id}/{self.token}/messages/@original",
        )

    async def send_modal(self, modal: Modal) -> None:
        """Respond to the interaction with a modal popup.

        Raises
        ------
        InteractionAlreadyResponded:
            If this interaction has already been responded to.
        """
        from ..errors import InteractionAlreadyResponded

        if self._responded:
            raise InteractionAlreadyResponded(
                "Cannot send modal — interaction already responded to."
            )

        await self._rest.request(
            "POST",
            f"/interactions/{self.id}/{self.token}/callback",
            json={
                "type": InteractionCallbackType.MODAL,
                "data": modal.to_dict(),
            },
        )
        self._responded = True

    async def update_message(
        self,
        content: str | None = None,
        *,
        embed: Embed | None = None,
        components: list[Any] | None = None,
    ) -> None:
        """Update the message that a component is attached to.

        Raises
        ------
        InteractionAlreadyResponded:
            If this interaction has already been responded to.
        """
        from ..errors import InteractionAlreadyResponded

        if self._responded:
            raise InteractionAlreadyResponded(
                "Cannot update message — interaction already responded to."
            )

        data: dict[str, Any] = {}
        if content is not None:
            data["content"] = content
        if embed is not None:
            data["embeds"] = [embed.to_dict()]
        if components is not None:
            data["components"] = [c.to_dict() for c in components]

        await self._rest.request(
            "POST",
            f"/interactions/{self.id}/{self.token}/callback",
            json={
                "type": InteractionCallbackType.UPDATE_MESSAGE,
                "data": data,
            },
        )
        self._responded = True

    async def autocomplete(self, choices: list[dict[str, Any]]) -> None:
        """Respond with autocomplete suggestions.

        Each choice is ``{"name": "display", "value": "actual_value"}``.

        Raises
        ------
        InteractionAlreadyResponded:
            If this interaction has already been responded to.
        """
        from ..errors import InteractionAlreadyResponded

        if self._responded:
            raise InteractionAlreadyResponded(
                "Cannot send autocomplete — interaction already responded to."
            )

        await self._rest.request(
            "POST",
            f"/interactions/{self.id}/{self.token}/callback",
            json={
                "type": InteractionCallbackType.APPLICATION_COMMAND_AUTOCOMPLETE_RESULT,
                "data": {"choices": choices[:25]},
            },
        )
        self._responded = True
