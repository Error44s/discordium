"""Command guards - cooldowns, permission checks, and predicates.

All guards raise exceptions from ``discordium.errors`` the central
error hierarchy. No local exception classes.

Works with both slash commands and prefix commands::

    @slash.command(name="ban", description="Ban a user")
    @has_permissions(Permissions.BAN_MEMBERS)
    @cooldown(rate=1, per=10.0)
    async def ban(inter: Interaction) -> None: ...
"""

from __future__ import annotations

import asyncio
import time
from collections import defaultdict
from collections.abc import Callable, Coroutine
from functools import wraps
from typing import Any

from ..errors import (
    BotMissingPermissions,
    CheckFailure,
    CommandOnCooldown,
    DMOnly,
    GuildOnly,
    MissingPermissions,
    NotOwner,
)
from ..models.permissions import Permissions

# Cooldown

def cooldown(
    rate: int = 1,
    per: float = 5.0,
    *,
    key: Callable[..., str] | None = None,
) -> Callable:
    """Rate-limit a command handler.

    Parameters
    ----------
    rate:
        Number of uses allowed within the window.
    per:
        Window duration in seconds.
    key:
        Custom function to extract a bucket key from the first arg.
        Defaults to user ID.

    Raises
    ------
    CommandOnCooldown:
        When the rate limit is exceeded.
    """
    buckets: dict[str, list[float]] = defaultdict(list)

    def decorator(func: Callable[..., Coroutine]) -> Callable[..., Coroutine]:
        @wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            source = args[0] if args else None
            if key:
                bucket_id = key(source)
            elif source is not None:
                user_id = None
                if hasattr(source, "user") and source.user:
                    user_id = str(source.user.id)
                elif (
                    hasattr(source, "message")
                    and source.message
                    and source.message.author
                ):
                    user_id = str(source.message.author.id)
                bucket_id = user_id or "global"
            else:
                bucket_id = "global"

            now = time.monotonic()
            buckets[bucket_id] = [t for t in buckets[bucket_id] if now - t < per]
            timestamps = buckets[bucket_id]

            if len(timestamps) >= rate:
                retry_after = per - (now - timestamps[0])
                raise CommandOnCooldown(retry_after)

            timestamps.append(now)
            return await func(*args, **kwargs)

        return wrapper

    return decorator

# Permission checks

def has_permissions(*perms: Permissions) -> Callable:
    """Check that the invoking member has all specified permissions.

    Raises ``MissingPermissions`` with the list of missing perm names.
    """

    def decorator(func: Callable[..., Coroutine]) -> Callable[..., Coroutine]:
        @wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            source = args[0] if args else None
            member_perms = Permissions(0)

            if hasattr(source, "member") and source.member:
                member_perms = source.member.permissions

            missing = [p.name for p in perms if not member_perms.has(p)]
            if missing:
                raise MissingPermissions(missing)

            return await func(*args, **kwargs)

        return wrapper

    return decorator


def bot_has_permissions(*perms: Permissions) -> Callable:
    """Check that the bot has all specified permissions in the current context.

    Supports two source types:

    **Slash / Interaction** - reads ``app_permissions`` from the interaction
    payload root (Discord injects this automatically). This is the most
    reliable path and covers channel-level overrides as computed by Discord.

    **Prefix commands (Context)** - not supported yet. The guard passes
    silently and logs a warning. Channel-override resolution for prefix
    commands requires a separate REST lookup that is outside the scope of
    this guard. Contributions welcome.

    Raises ``BotMissingPermissions`` with the list of missing perm names.

    .. note::
        For interactions, Discord computes ``app_permissions`` server-side
        including channel overrides, so this is accurate. For prefix commands,
        consider checking bot permissions manually via ``ctx.rest``.
    """

    def decorator(func: Callable[..., Coroutine]) -> Callable[..., Coroutine]:
        @wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            import logging as _logging
            _log = _logging.getLogger("discordium.guards")

            source = args[0] if args else None
            bot_perms = Permissions(0)

            # Interaction path
            # app_permissions lives in the interaction payload ROOT,
            # not in interaction.data. It's injected by Discord and
            # already accounts for channel-level overrides.
            if hasattr(source, "_rest") and hasattr(source, "guild_id"):
                raw_perms = None
                # Check via the raw payload stored on the interaction
                # (both Interaction objects and raw dicts are handled)
                if hasattr(source, "app_permissions"):
                    raw_perms = source.app_permissions
                elif hasattr(source, "data") and isinstance(source.data, dict):
                    # Fallback: some wrappers store the full payload in .data
                    raw_perms = source.data.get("app_permissions")

                if raw_perms is not None:
                    bot_perms = Permissions.from_value(raw_perms)
                    missing = [p.name for p in perms if not bot_perms.has(p)]
                    if missing:
                        raise BotMissingPermissions(missing)
                    return await func(*args, **kwargs)

            # Prefix command path (Context)
            # We don't have app_permissions here. Silently pass and warn
            # so existing bots don't break, but make the gap visible.
            if hasattr(source, "message") and hasattr(source, "prefix"):
                _log.warning(
                    "bot_has_permissions() called in a prefix-command context "
                    "— channel-level permission resolution is not implemented. "
                    "Check bot permissions manually via ctx.rest if needed."
                )
                return await func(*args, **kwargs)

            # Unknown context
            _log.debug(
                "bot_has_permissions(): unrecognised source type %r, skipping check",
                type(source).__name__,
            )
            return await func(*args, **kwargs)

        return wrapper

    return decorator


_owner_ids_cache: set[str] | None = None
"""Module-level cache for owner/team member IDs.

Populated on first ``owner_only()`` check, then reused for all subsequent
calls. Reset to ``None`` to force a refresh (e.g. after a team change)::

    import discordium.ext.guards as guards
    guards._owner_ids_cache = None
"""


async def _fetch_owner_ids(rest: Any) -> set[str]:
    """Fetch owner / team-member IDs from ``/oauth2/applications/@me``.

    Results are cached in ``_owner_ids_cache`` for the lifetime of the
    process. The API is only called once, not on every command invocation.
    """
    global _owner_ids_cache
    if _owner_ids_cache is not None:
        return _owner_ids_cache

    app_info = await rest.request("GET", "/oauth2/applications/@me")
    ids: set[str] = set()

    team = app_info.get("team")
    if team:
        for member in team.get("members", []):
            uid = member.get("user", {}).get("id")
            if uid:
                ids.add(str(uid))
    else:
        owner_id = app_info.get("owner", {}).get("id")
        if owner_id:
            ids.add(str(owner_id))

    _owner_ids_cache = ids
    return ids


def owner_only() -> Callable:
    """Only allow the application owner (or team members) to use this command.

    Owner IDs are fetched once on first use via ``/oauth2/applications/@me``
    and cached for all subsequent checks — no repeated API calls.

    To force a refresh (e.g. after a team change), set
    ``discordium.ext.guards._owner_ids_cache = None``.

    Raises ``NotOwner``.
    """

    def decorator(func: Callable[..., Coroutine]) -> Callable[..., Coroutine]:
        @wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            source = args[0] if args else None

            if not (hasattr(source, "_rest") and hasattr(source, "user")):
                raise NotOwner()

            user_id = str(source.user.id) if source.user else None
            if not user_id:
                raise NotOwner()

            try:
                owner_ids = await _fetch_owner_ids(source._rest)
            except Exception:
                raise NotOwner()

            if user_id not in owner_ids:
                raise NotOwner()

            return await func(*args, **kwargs)

        return wrapper

    return decorator


def check(
    predicate: Callable[..., bool | Coroutine[Any, Any, bool]],
) -> Callable:
    """Custom check decorator with any sync or async predicate::

        @check(lambda inter: inter.guild_id is not None)
        async def guild_cmd(inter): ...
    """

    def decorator(func: Callable[..., Coroutine]) -> Callable[..., Coroutine]:
        @wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            source = args[0] if args else None
            result = predicate(source)
            if asyncio.iscoroutine(result):
                result = await result
            if not result:
                raise CheckFailure()
            return await func(*args, **kwargs)

        return wrapper

    return decorator


def guild_only() -> Callable:
    """Only allow in guilds (not DMs). Raises ``GuildOnly``."""

    def decorator(func: Callable[..., Coroutine]) -> Callable[..., Coroutine]:
        @wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            source = args[0] if args else None
            guild_id = getattr(source, "guild_id", None)
            if guild_id is None:
                raise GuildOnly()
            return await func(*args, **kwargs)

        return wrapper

    return decorator


def dm_only() -> Callable:
    """Only allow in DMs. Raises ``DMOnly``."""

    def decorator(func: Callable[..., Coroutine]) -> Callable[..., Coroutine]:
        @wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            source = args[0] if args else None
            guild_id = getattr(source, "guild_id", None)
            if guild_id is not None:
                raise DMOnly()
            return await func(*args, **kwargs)

        return wrapper

    return decorator
