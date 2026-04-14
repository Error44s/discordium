"""Structured exception hierarchy for discordium.

Every error the framework can raise has a specific class so users can
catch exactly what they need::

    try:
        await inter.respond("hello")
    except discordium.InteractionAlreadyResponded:
        await inter.followup("hello (followup)")

    try:
        await rest.ban_member(guild_id, user_id)
    except discordium.Forbidden as e:
        print(f"Missing permissions: {e}")
    except discordium.NotFound:
        print("User not found")
"""

from __future__ import annotations

from typing import Any

#  Base

class DiscordiumError(Exception):
    """Base exception for all discordium errors."""

#  HTTP Errors

class HTTPError(DiscordiumError):
    """Raised when the Discord API returns a non-2xx status code.

    Attributes
    ----------
    status:
        HTTP status code.
    error_code:
        Discord-specific error code (from the JSON response), or None.
    data:
        Full response body.
    """

    def __init__(self, status: int, data: dict[str, Any] | str) -> None:
        self.status = status
        self.data = data
        if isinstance(data, dict):
            self.error_code: int | None = data.get("code")
            msg = data.get("message", str(data))
        else:
            self.error_code = None
            msg = str(data)
        super().__init__(f"HTTP {status}: {msg}")


class Forbidden(HTTPError):
    """403 — missing permissions or access denied."""

    def __init__(self, data: dict[str, Any] | str) -> None:
        super().__init__(403, data)


class NotFound(HTTPError):
    """404 — the requested resource does not exist."""

    def __init__(self, data: dict[str, Any] | str) -> None:
        super().__init__(404, data)


class RateLimited(HTTPError):
    """429 — rate limited by Discord.

    Attributes
    ----------
    retry_after:
        Seconds to wait before retrying.
    is_global:
        Whether this is a global rate limit.
    """

    def __init__(
        self,
        data: dict[str, Any] | str,
        *,
        retry_after: float = 1.0,
        is_global: bool = False,
    ) -> None:
        super().__init__(429, data)
        self.retry_after = retry_after
        self.is_global = is_global


class ServerError(HTTPError):
    """5xx — Discord server error."""

    def __init__(self, status: int, data: dict[str, Any] | str) -> None:
        super().__init__(status, data)

#  Gateway Errors

class GatewayError(DiscordiumError):
    """Base for gateway-related errors."""


class GatewayReconnect(GatewayError):
    """The gateway requested a reconnect."""


class InvalidSession(GatewayError):
    """The gateway session is invalid.

    Attributes
    ----------
    resumable:
        Whether the session can be resumed.
    """

    def __init__(self, resumable: bool = False) -> None:
        self.resumable = resumable
        super().__init__(f"Invalid session (resumable={resumable})")


class HeartbeatTimeout(GatewayError):
    """No heartbeat ACK received — zombie connection detected."""


class ConnectionClosed(GatewayError):
    """The WebSocket connection was closed.

    Attributes
    ----------
    code:
        WebSocket close code.
    reason:
        Close reason string.
    """

    def __init__(self, code: int, reason: str = "") -> None:
        self.code = code
        self.reason = reason
        super().__init__(f"WebSocket closed: {code} {reason}")

#  Interaction Errors

class InteractionError(DiscordiumError):
    """Base for interaction-related errors."""


class InteractionAlreadyResponded(InteractionError):
    """The interaction has already received an initial response."""


class InteractionNotResponded(InteractionError):
    """Cannot send followup before responding or deferring."""


class InteractionTimedOut(InteractionError):
    """The 3-second interaction response window has expired."""

#  Command Errors

class CommandError(DiscordiumError):
    """Base for command framework errors."""


class CommandNotFound(CommandError):
    """The invoked command does not exist."""

    def __init__(self, command_name: str) -> None:
        self.command_name = command_name
        super().__init__(f"Command not found: {command_name!r}")


class CommandOnCooldown(CommandError):
    """The command is on cooldown for this user/guild.

    Attributes
    ----------
    retry_after:
        Seconds until the command can be used again.
    """

    def __init__(self, retry_after: float) -> None:
        self.retry_after = retry_after
        super().__init__(f"Command on cooldown. Retry in {retry_after:.1f}s")


class CheckFailure(CommandError):
    """A command check (permission, predicate, etc.) failed."""

    def __init__(self, message: str = "You don't have permission to use this command.") -> None:
        super().__init__(message)


class MissingPermissions(CheckFailure):
    """The invoking user is missing required permissions.

    Attributes
    ----------
    missing:
        List of permission names that are missing.
    """

    def __init__(self, missing: list[str]) -> None:
        self.missing = missing
        perms = ", ".join(missing)
        super().__init__(f"Missing permissions: {perms}")


class BotMissingPermissions(CheckFailure):
    """The bot is missing required permissions.

    Attributes
    ----------
    missing:
        List of permission names that are missing.
    """

    def __init__(self, missing: list[str]) -> None:
        self.missing = missing
        perms = ", ".join(missing)
        super().__init__(f"Bot is missing permissions: {perms}")


class NotOwner(CheckFailure):
    """The command requires the bot owner."""

    def __init__(self) -> None:
        super().__init__("This command can only be used by the bot owner.")


class GuildOnly(CheckFailure):
    """The command can only be used in a guild."""

    def __init__(self) -> None:
        super().__init__("This command can only be used in a server.")


class DMOnly(CheckFailure):
    """The command can only be used in DMs."""

    def __init__(self) -> None:
        super().__init__("This command can only be used in DMs.")


class MaxConcurrencyReached(CommandError):
    """Too many concurrent invocations of this command."""

    def __init__(self, limit: int) -> None:
        self.limit = limit
        super().__init__(f"Max concurrency reached ({limit})")

#  Client Errors

class ClientError(DiscordiumError):
    """Base for client lifecycle errors."""


class NotReady(ClientError):
    """An operation was attempted before the client is ready."""


class AlreadyConnected(ClientError):
    """The client is already connected to the gateway."""


class LoginFailure(ClientError):
    """Authentication failed — invalid token or similar."""
