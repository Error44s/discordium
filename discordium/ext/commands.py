"""Lightweight prefix-command framework.

Unlike other heavy Cog system, discordium uses a flat, functional
approach — just decorate async functions::

    from discordium.ext.commands import CommandRouter

    router = CommandRouter(prefix="!")

    @router.command()
    async def ping(ctx: Context) -> None:
        await ctx.reply("Pong!")

    # In your bot setup:
    router.attach(bot)
"""

from __future__ import annotations

import inspect
import logging
import shlex
from collections.abc import Callable, Coroutine
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ..client import GatewayClient
    from ..http.rest import RESTClient
    from ..models.message import Message
    from ..models.snowflake import Snowflake

logger = logging.getLogger("discordium.commands")


@dataclass(frozen=True, slots=True)
class Context:
    """Invocation context passed to every command handler."""

    message: Message
    rest: RESTClient
    prefix: str
    command_name: str
    args: list[str]
    raw_args: str

    async def reply(self, content: str, **kwargs: Any) -> Message:
        return await self.message.reply(content, **kwargs)

    async def send(self, content: str, **kwargs: Any) -> Message:
        return await self.rest.send_message(
            self.message.channel_id, content, **kwargs
        )


@dataclass
class Command:
    """Metadata for a registered command."""

    name: str
    callback: Callable[..., Coroutine[Any, Any, Any]]
    aliases: list[str] = field(default_factory=list)
    description: str = ""
    hidden: bool = False

    @property
    def signature(self) -> str:
        """Human-readable parameter signature."""
        sig = inspect.signature(self.callback)
        params = []
        for p_name, param in sig.parameters.items():
            if p_name == "ctx":
                continue
            if param.default is inspect.Parameter.empty:
                params.append(f"<{p_name}>")
            else:
                params.append(f"[{p_name}]")
        return " ".join(params)


class CommandRouter:
    """Prefix-command router.

    Parameters
    ----------
    prefix:
        Command prefix string (e.g. ``"!"``, ``"?"``, ``"bot "``).
    case_sensitive:
        Whether command matching is case-sensitive.
    """

    __slots__ = ("_prefix", "_commands", "_case_sensitive")

    def __init__(self, prefix: str = "!", *, case_sensitive: bool = False) -> None:
        self._prefix = prefix
        self._case_sensitive = case_sensitive
        self._commands: dict[str, Command] = {}

    @property
    def commands(self) -> dict[str, Command]:
        return dict(self._commands)

    def command(
        self,
        name: str | None = None,
        *,
        aliases: list[str] | None = None,
        description: str = "",
        hidden: bool = False,
    ) -> Callable[
        [Callable[..., Coroutine[Any, Any, Any]]],
        Callable[..., Coroutine[Any, Any, Any]],
    ]:
        """Register a command handler."""

        def decorator(
            func: Callable[..., Coroutine[Any, Any, Any]],
        ) -> Callable[..., Coroutine[Any, Any, Any]]:
            cmd_name = name or func.__name__
            cmd = Command(
                name=cmd_name,
                callback=func,
                aliases=aliases or [],
                description=description or func.__doc__ or "",
                hidden=hidden,
            )
            key = cmd_name if self._case_sensitive else cmd_name.lower()
            self._commands[key] = cmd
            for alias in cmd.aliases:
                a_key = alias if self._case_sensitive else alias.lower()
                self._commands[a_key] = cmd
            return func

        return decorator

    def attach(self, client: GatewayClient) -> None:
        """Bind this router to a ``GatewayClient`` so it processes messages."""
        from ..models.event_names import Events

        @client.on_event(Events.MESSAGE_CREATE)
        async def _dispatch(event: Any) -> None:
            from ..models.events import MessageCreateEvent
            from ..models.message import Message

            # Accept both typed events and raw dicts
            if isinstance(event, MessageCreateEvent):
                msg = event.message
            elif isinstance(event, dict):
                msg = Message.from_payload(event, rest=client.rest)
            else:
                return

            # Ignore bots
            if msg.author and msg.author.bot:
                return

            content = msg.content
            if not content.startswith(self._prefix):
                return

            without_prefix = content[len(self._prefix) :]
            if not without_prefix:
                return

            try:
                parts = shlex.split(without_prefix)
            except ValueError:
                parts = without_prefix.split()

            cmd_name = parts[0]
            key = cmd_name if self._case_sensitive else cmd_name.lower()
            cmd = self._commands.get(key)
            if cmd is None:
                return

            args = parts[1:]
            raw_args = without_prefix[len(cmd_name) :].strip()

            ctx = Context(
                message=msg,
                rest=client.rest,
                prefix=self._prefix,
                command_name=cmd_name,
                args=args,
                raw_args=raw_args,
            )

            try:
                await cmd.callback(ctx, *args)
            except TypeError as exc:
                logger.error("Command %r argument error: %s", cmd.name, exc)
            except Exception:
                logger.exception("Error in command %r", cmd.name)
