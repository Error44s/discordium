"""Application Commands (slash commands) framework.

Clean, decorator-driven API for registering and syncing slash commands::

    from discordium.ext.slash import SlashRouter, slash_option
    from discordium.models.interaction import Interaction

    slash = SlashRouter()

    @slash.command(name="greet", description="Say hello")
    @slash_option("user", "Who to greet", type=6, required=True)       # USER type
    @slash_option("message", "Custom message", type=3, required=False)  # STRING type
    async def greet(inter: Interaction) -> None:
        user_id = inter.get_option("user")
        msg = inter.get_option("message") or "Hello!"
        await inter.respond(f"{msg}, <@{user_id}>!")

    # Subcommands via groups:
    settings = slash.group("settings", "Bot settings")

    @settings.command(name="language", description="Set your language")
    @slash_option("lang", "Language code", type=3, required=True)
    async def set_lang(inter: Interaction) -> None:
        await inter.respond(f"Language set to {inter.get_option('lang')}", ephemeral=True)

    # Attach + sync:
    slash.attach(bot)
    # In on_ready:
    await slash.sync(bot)
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Coroutine
from enum import IntEnum
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ..client import GatewayClient
    from ..models.interaction import Interaction

logger = logging.getLogger("discordium.slash")

Handler = Callable[..., Coroutine[Any, Any, Any]]


class OptionType(IntEnum):
    """Application command option types."""
    SUB_COMMAND = 1
    SUB_COMMAND_GROUP = 2
    STRING = 3
    INTEGER = 4
    BOOLEAN = 5
    USER = 6
    CHANNEL = 7
    ROLE = 8
    MENTIONABLE = 9
    NUMBER = 10
    ATTACHMENT = 11


class CommandChoice:
    """A predefined choice for a command option."""

    __slots__ = ("name", "value")

    def __init__(self, name: str, value: str | int | float) -> None:
        self.name = name
        self.value = value

    def to_dict(self) -> dict[str, Any]:
        return {"name": self.name, "value": self.value}


class CommandOption:
    """Metadata for a single slash command option."""

    __slots__ = (
        "name", "description", "type", "required",
        "choices", "min_value", "max_value", "min_length",
        "max_length", "autocomplete", "channel_types", "options",
    )

    def __init__(
        self,
        name: str,
        description: str,
        *,
        type: int = OptionType.STRING,
        required: bool = False,
        choices: list[CommandChoice] | None = None,
        min_value: int | float | None = None,
        max_value: int | float | None = None,
        min_length: int | None = None,
        max_length: int | None = None,
        autocomplete: bool = False,
        channel_types: list[int] | None = None,
        options: list[CommandOption] | None = None,
    ) -> None:
        self.name = name
        self.description = description
        self.type = type
        self.required = required
        self.choices = choices
        self.min_value = min_value
        self.max_value = max_value
        self.min_length = min_length
        self.max_length = max_length
        self.autocomplete = autocomplete
        self.channel_types = channel_types
        self.options = options

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "name": self.name,
            "description": self.description,
            "type": self.type,
        }
        if self.required:
            d["required"] = True
        if self.choices:
            d["choices"] = [c.to_dict() for c in self.choices]
        if self.min_value is not None:
            d["min_value"] = self.min_value
        if self.max_value is not None:
            d["max_value"] = self.max_value
        if self.min_length is not None:
            d["min_length"] = self.min_length
        if self.max_length is not None:
            d["max_length"] = self.max_length
        if self.autocomplete:
            d["autocomplete"] = True
        if self.channel_types is not None:
            d["channel_types"] = self.channel_types
        if self.options:
            d["options"] = [o.to_dict() for o in self.options]
        return d


class SlashCommand:
    """Registered slash command metadata + handler."""

    __slots__ = (
        "name", "description", "callback", "options",
        "guild_ids", "dm_permission", "default_member_permissions",
        "nsfw", "_autocomplete_handlers",
    )

    def __init__(
        self,
        name: str,
        description: str,
        callback: Handler,
        *,
        options: list[CommandOption] | None = None,
        guild_ids: list[int] | None = None,
        dm_permission: bool = True,
        default_member_permissions: int | None = None,
        nsfw: bool = False,
    ) -> None:
        self.name = name
        self.description = description
        self.callback = callback
        self.options = options or []
        self.guild_ids = guild_ids
        self.dm_permission = dm_permission
        self.default_member_permissions = default_member_permissions
        self.nsfw = nsfw
        self._autocomplete_handlers: dict[str, Handler] = {}

    def autocomplete(self, option_name: str) -> Callable[[Handler], Handler]:
        """Register an autocomplete handler for a specific option::

            @greet.autocomplete("message")
            async def message_autocomplete(inter: Interaction) -> None:
                await inter.autocomplete([
                    {"name": "Hello!", "value": "hello"},
                    {"name": "Welcome!", "value": "welcome"},
                ])
        """
        def decorator(func: Handler) -> Handler:
            self._autocomplete_handlers[option_name] = func
            return func
        return decorator

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "name": self.name,
            "description": self.description,
            "type": 1,  # CHAT_INPUT
        }
        if self.options:
            d["options"] = [o.to_dict() for o in self.options]
        if not self.dm_permission:
            d["dm_permission"] = False
        if self.default_member_permissions is not None:
            d["default_member_permissions"] = str(self.default_member_permissions)
        if self.nsfw:
            d["nsfw"] = True
        return d


class SubcommandGroup:
    """A group of related subcommands under one top-level command::

        settings = slash.group("settings", "Bot configuration")

        @settings.command(name="language", description="Set language")
        async def set_lang(inter): ...
    """

    __slots__ = ("name", "description", "subcommands", "guild_ids")

    def __init__(self, name: str, description: str, *, guild_ids: list[int] | None = None) -> None:
        self.name = name
        self.description = description
        self.subcommands: dict[str, SlashCommand] = {}
        self.guild_ids = guild_ids

    def command(
        self,
        name: str,
        description: str,
        **kwargs: Any,
    ) -> Callable[[Handler], SlashCommand]:
        """Register a subcommand in this group."""
        def decorator(func: Handler) -> SlashCommand:
            options = getattr(func, "__slash_options__", [])
            cmd = SlashCommand(name, description, func, options=options, **kwargs)
            self.subcommands[name] = cmd
            return cmd
        return decorator

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "type": 1,
            "options": [
                {
                    "name": sub.name,
                    "description": sub.description,
                    "type": OptionType.SUB_COMMAND,
                    "options": [o.to_dict() for o in sub.options],
                }
                for sub in self.subcommands.values()
            ],
        }

# Decorator for options

def slash_option(
    name: str,
    description: str,
    *,
    type: int = OptionType.STRING,
    required: bool = False,
    choices: list[tuple[str, Any]] | None = None,
    min_value: int | float | None = None,
    max_value: int | float | None = None,
    autocomplete: bool = False,
    **kwargs: Any,
) -> Callable[[Handler], Handler]:
    """Decorator to add an option to a slash command::

        @slash.command(name="ban", description="Ban a user")
        @slash_option("user", "The user to ban", type=6, required=True)
        @slash_option("reason", "Ban reason", type=3)
        async def ban(inter: Interaction) -> None: ...
    """
    parsed_choices = (
        [CommandChoice(n, v) for n, v in choices] if choices else None
    )
    option = CommandOption(
        name, description,
        type=type, required=required, choices=parsed_choices,
        min_value=min_value, max_value=max_value,
        autocomplete=autocomplete, **kwargs,
    )

    def decorator(func: Handler) -> Handler:
        if not hasattr(func, "__slash_options__"):
            func.__slash_options__ = []  # type: ignore[attr-defined]
        # Prepend so options appear in decorator order (top→bottom = first→last)
        func.__slash_options__.insert(0, option)  # type: ignore[attr-defined]
        return func

    return decorator

# Router

class SlashRouter:
    """Manages slash command registration, syncing, and dispatch.

    Usage::

        slash = SlashRouter()

        @slash.command(name="ping", description="Pong!")
        async def ping(inter): ...

        slash.attach(bot)
        # In on_ready: await slash.sync(bot)
    """

    __slots__ = (
        "_commands", "_groups", "_component_handlers",
        "_modal_handlers", "_application_id",
    )

    def __init__(self) -> None:
        self._commands: dict[str, SlashCommand] = {}
        self._groups: dict[str, SubcommandGroup] = {}
        self._component_handlers: dict[str, Handler] = {}
        self._modal_handlers: dict[str, Handler] = {}
        self._application_id: str | None = None

    # Registration

    def command(
        self,
        name: str,
        description: str,
        **kwargs: Any,
    ) -> Callable[[Handler], SlashCommand]:
        """Register a top-level slash command."""
        def decorator(func: Handler) -> SlashCommand:
            options = getattr(func, "__slash_options__", [])
            cmd = SlashCommand(name, description, func, options=options, **kwargs)
            self._commands[name] = cmd
            return cmd
        return decorator

    def group(self, name: str, description: str, **kwargs: Any) -> SubcommandGroup:
        """Create a subcommand group."""
        grp = SubcommandGroup(name, description, **kwargs)
        self._groups[name] = grp
        return grp

    def on_component(self, custom_id: str) -> Callable[[Handler], Handler]:
        """Register a handler for a component interaction (button, select)::

            @slash.on_component("accept_btn")
            async def on_accept(inter: Interaction) -> None: ...
        """
        def decorator(func: Handler) -> Handler:
            self._component_handlers[custom_id] = func
            return func
        return decorator

    def on_modal(self, custom_id: str) -> Callable[[Handler], Handler]:
        """Register a handler for a modal submission::

            @slash.on_modal("feedback_modal")
            async def on_feedback(inter: Interaction) -> None:
                text = inter.get_field("feedback_text")
        """
        def decorator(func: Handler) -> Handler:
            self._modal_handlers[custom_id] = func
            return func
        return decorator

    # Sync

    async def sync(
        self,
        client: GatewayClient,
        *,
        guild_id: int | None = None,
    ) -> list[dict[str, Any]]:
        """Sync all registered commands to Discord.

        Parameters
        ----------
        client:
            The bot client (needs ``rest`` and ``user``).
        guild_id:
            If set, sync to a specific guild (instant). Otherwise global (up to 1hr cache).
        """
        if client.user is None:
            raise RuntimeError("Cannot sync before the bot is ready")

        app_id = str(client.user.id)
        self._application_id = app_id

        # Build command payloads
        payloads = []
        for cmd in self._commands.values():
            payloads.append(cmd.to_dict())
        for grp in self._groups.values():
            payloads.append(grp.to_dict())

        # Bulk overwrite
        if guild_id:
            path = f"/applications/{app_id}/guilds/{guild_id}/commands"
        else:
            path = f"/applications/{app_id}/commands"

        result = await client.rest.request("PUT", path, json=payloads)
        synced = result if isinstance(result, list) else []
        logger.info(
            "Synced %d command(s) %s",
            len(synced),
            f"to guild {guild_id}" if guild_id else "globally",
        )
        return synced

    # Dispatch

    def attach(self, client: GatewayClient) -> None:
        """Hook into the client's event system to dispatch interactions."""
        from ..models.event_names import Events

        @client.on_event(Events.INTERACTION_CREATE)
        async def _dispatch(event: Any) -> None:
            from ..models.events import InteractionCreateEvent
            from ..models.interaction import Interaction, InteractionType

            # Accept both typed events and raw dicts for backwards compat
            if isinstance(event, InteractionCreateEvent):
                raw = event.interaction_data
            elif isinstance(event, dict):
                raw = event
            else:
                return

            inter = Interaction(raw, rest=client.rest)

            match inter.type:
                case InteractionType.APPLICATION_COMMAND:
                    await self._dispatch_command(inter)

                case InteractionType.APPLICATION_COMMAND_AUTOCOMPLETE:
                    await self._dispatch_autocomplete(inter)

                case InteractionType.MESSAGE_COMPONENT:
                    await self._dispatch_component(inter)

                case InteractionType.MODAL_SUBMIT:
                    await self._dispatch_modal(inter)

                case InteractionType.PING:
                    await client.rest.request(
                        "POST",
                        f"/interactions/{inter.id}/{inter.token}/callback",
                        json={"type": 1},
                    )

    async def _dispatch_command(self, inter: Interaction) -> None:
        name = inter.command_name
        if name is None:
            return

        # Direct command
        cmd = self._commands.get(name)
        if cmd:
            try:
                await cmd.callback(inter)
            except Exception:
                logger.exception("Error in slash command %r", name)
            return

        # Subcommand group
        grp = self._groups.get(name)
        if grp:
            subname = inter.get_subcommand()
            if subname and subname in grp.subcommands:
                try:
                    await grp.subcommands[subname].callback(inter)
                except Exception:
                    logger.exception("Error in subcommand %s %s", name, subname)
            return

        logger.warning("Unknown slash command: %s", name)

    async def _dispatch_autocomplete(self, inter: Interaction) -> None:
        name = inter.command_name
        if name is None:
            return

        cmd = self._commands.get(name)
        if not cmd:
            return

        # Find which option is focused
        for opt in inter.options:
            if opt.focused and opt.name in cmd._autocomplete_handlers:
                try:
                    await cmd._autocomplete_handlers[opt.name](inter)
                except Exception:
                    logger.exception("Error in autocomplete for %s.%s", name, opt.name)
                return

    async def _dispatch_component(self, inter: Interaction) -> None:
        cid = inter.custom_id
        if cid is None:
            return

        # Exact match first
        handler = self._component_handlers.get(cid)
        if handler is None:
            # Prefix match for dynamic IDs like "role_select:12345"
            for prefix, h in self._component_handlers.items():
                if cid.startswith(prefix):
                    handler = h
                    break

        if handler:
            try:
                await handler(inter)
            except Exception:
                logger.exception("Error in component handler %r", cid)
        else:
            logger.debug("Unhandled component interaction: %s", cid)

    async def _dispatch_modal(self, inter: Interaction) -> None:
        cid = inter.custom_id
        if cid is None:
            return

        handler = self._modal_handlers.get(cid)
        if handler is None:
            for prefix, h in self._modal_handlers.items():
                if cid.startswith(prefix):
                    handler = h
                    break

        if handler:
            try:
                await handler(inter)
            except Exception:
                logger.exception("Error in modal handler %r", cid)
        else:
            logger.debug("Unhandled modal submission: %s", cid)
