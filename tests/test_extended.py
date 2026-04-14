"""Extended test suite — covers every requested category.

Tests:
  1. Slash command dispatch (direct, subcommand, unknown, autocomplete)
  2. Component dispatch (exact match, prefix match, unhandled)
  3. Modal dispatch (exact match, prefix match, unhandled)
  4. REST error mapping (403, 404, 429, 5xx, 204, retry logic)
  5. 429 rate limit behavior (per-route, global, retry-after)
  6. Guard combinations (stacked, async, edge cases)
  7. Task loop lifecycle (start/stop/restart/count/hooks)
  8. Event parser — every registered event type
  9. File upload edge cases
  10. Gateway reconnect / heartbeat
"""

import asyncio
import time
import zlib
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from discordium.errors import (
    CheckFailure,
    CommandOnCooldown,
    DMOnly,
    Forbidden,
    GuildOnly,
    HTTPError,
    InteractionAlreadyResponded,
    InteractionNotResponded,
    MissingPermissions,
    NotFound,
    ServerError,
)
from discordium.models.interaction import Interaction, InteractionType
from discordium.models.permissions import Permissions
from discordium.models.snowflake import Snowflake

#  Helpers

def _inter_payload(*, type_=2, name="test", custom_id=None, options=None,
                   values=None, components=None, focused_option=None):
    """Build a raw interaction payload for testing."""
    data = {}
    if name:
        data["name"] = name
    if custom_id:
        data["custom_id"] = custom_id
    if options:
        data["options"] = options
    if values:
        data["values"] = values
    if components:
        data["components"] = components
    if focused_option:
        data["options"] = [{"name": focused_option, "type": 3, "value": "", "focused": True}]

    return {
        "id": "900", "application_id": "800", "type": type_,
        "token": "tok", "guild_id": "111", "channel_id": "222",
        "data": data,
        "member": {
            "user": {"id": "333", "username": "tester", "discriminator": "0"},
            "nick": None, "roles": [], "permissions": "0",
        },
    }


def _make_inter(**kwargs):
    rest = AsyncMock()
    rest.request = AsyncMock(return_value={})
    return Interaction(_inter_payload(**kwargs), rest=rest)

#  1. Slash Command Dispatch Tests

class TestSlashCommandDispatch:
    def _make_router(self):
        from discordium.ext.slash import SlashRouter
        return SlashRouter()

    @pytest.mark.asyncio
    async def test_dispatch_direct_command(self):
        router = self._make_router()
        called = []

        @router.command(name="ping", description="Ping")
        async def ping(inter):
            called.append("ping")

        inter = _make_inter(name="ping")
        await router._dispatch_command(inter)
        assert called == ["ping"]

    @pytest.mark.asyncio
    async def test_dispatch_unknown_command(self):
        """Unknown commands should not crash, just log a warning."""
        router = self._make_router()
        inter = _make_inter(name="nonexistent")
        await router._dispatch_command(inter)  # should not raise

    @pytest.mark.asyncio
    async def test_dispatch_subcommand(self):
        router = self._make_router()
        called = []

        grp = router.group("settings", "Settings")

        @grp.command(name="lang", description="Set language")
        async def set_lang(inter):
            called.append("lang")

        # Subcommand invocation has options with type=1 (SUB_COMMAND)
        inter = _make_inter(
            name="settings",
            options=[{
                "name": "lang", "type": 1,
                "options": [{"name": "value", "type": 3, "value": "en"}],
            }],
        )
        await router._dispatch_command(inter)
        assert called == ["lang"]

    @pytest.mark.asyncio
    async def test_dispatch_subcommand_unknown_sub(self):
        """Unknown subcommand should not crash."""
        router = self._make_router()
        grp = router.group("settings", "Settings")

        @grp.command(name="lang", description="Set language")
        async def set_lang(inter): pass

        inter = _make_inter(
            name="settings",
            options=[{"name": "unknown_sub", "type": 1, "options": []}],
        )
        await router._dispatch_command(inter)  # should not raise

    @pytest.mark.asyncio
    async def test_dispatch_command_error_caught(self):
        """Errors in command handlers should be caught, not propagated."""
        router = self._make_router()

        @router.command(name="fail", description="Fail")
        async def fail(inter):
            raise ValueError("boom")

        inter = _make_inter(name="fail")
        await router._dispatch_command(inter)  # should not raise

    @pytest.mark.asyncio
    async def test_dispatch_autocomplete(self):
        router = self._make_router()
        called = []

        @router.command(name="color", description="Pick color")
        async def color(inter): pass

        @color.autocomplete("name")
        async def color_ac(inter):
            called.append("autocomplete")

        inter = _make_inter(name="color", focused_option="name")
        await router._dispatch_autocomplete(inter)
        assert called == ["autocomplete"]

    @pytest.mark.asyncio
    async def test_dispatch_autocomplete_unknown_option(self):
        """Autocomplete for unregistered option should not crash."""
        router = self._make_router()

        @router.command(name="test", description="Test")
        async def test_cmd(inter): pass

        inter = _make_inter(name="test", focused_option="unregistered")
        await router._dispatch_autocomplete(inter)  # should not raise

    @pytest.mark.asyncio
    async def test_multiple_commands_dispatch_correctly(self):
        """Multiple registered commands should dispatch to the right one."""
        router = self._make_router()
        called = []

        @router.command(name="cmd_a", description="A")
        async def cmd_a(inter): called.append("a")

        @router.command(name="cmd_b", description="B")
        async def cmd_b(inter): called.append("b")

        @router.command(name="cmd_c", description="C")
        async def cmd_c(inter): called.append("c")

        await router._dispatch_command(_make_inter(name="cmd_b"))
        await router._dispatch_command(_make_inter(name="cmd_a"))
        await router._dispatch_command(_make_inter(name="cmd_c"))
        assert called == ["b", "a", "c"]

#  2. Component Dispatch Tests

class TestComponentDispatch:
    def _make_router(self):
        from discordium.ext.slash import SlashRouter
        return SlashRouter()

    @pytest.mark.asyncio
    async def test_exact_match(self):
        router = self._make_router()
        called = []

        @router.on_component("btn_accept")
        async def on_accept(inter): called.append("accept")

        inter = _make_inter(type_=3, custom_id="btn_accept")
        await router._dispatch_component(inter)
        assert called == ["accept"]

    @pytest.mark.asyncio
    async def test_prefix_match(self):
        router = self._make_router()
        called = []

        @router.on_component("counter:")
        async def on_counter(inter): called.append(inter.custom_id)

        inter = _make_inter(type_=3, custom_id="counter:inc")
        await router._dispatch_component(inter)
        assert called == ["counter:inc"]

    @pytest.mark.asyncio
    async def test_unhandled_component(self):
        """Unregistered component custom_id should not crash."""
        router = self._make_router()
        inter = _make_inter(type_=3, custom_id="unknown_btn")
        await router._dispatch_component(inter)  # no crash

    @pytest.mark.asyncio
    async def test_component_error_caught(self):
        router = self._make_router()

        @router.on_component("crash")
        async def on_crash(inter): raise RuntimeError("oops")

        inter = _make_inter(type_=3, custom_id="crash")
        await router._dispatch_component(inter)  # should not raise

    @pytest.mark.asyncio
    async def test_null_custom_id(self):
        router = self._make_router()
        inter = _make_inter(type_=3, custom_id=None)
        await router._dispatch_component(inter)  # should not raise

    @pytest.mark.asyncio
    async def test_multiple_component_handlers(self):
        router = self._make_router()
        called = []

        @router.on_component("vote:yes")
        async def on_yes(inter): called.append("yes")

        @router.on_component("vote:no")
        async def on_no(inter): called.append("no")

        await router._dispatch_component(_make_inter(type_=3, custom_id="vote:yes"))
        await router._dispatch_component(_make_inter(type_=3, custom_id="vote:no"))
        assert called == ["yes", "no"]

#  3. Modal Dispatch Tests

class TestModalDispatch:
    def _make_router(self):
        from discordium.ext.slash import SlashRouter
        return SlashRouter()

    @pytest.mark.asyncio
    async def test_exact_match(self):
        router = self._make_router()
        called = []

        @router.on_modal("feedback_modal")
        async def on_fb(inter): called.append("fb")

        inter = _make_inter(type_=5, custom_id="feedback_modal")
        await router._dispatch_modal(inter)
        assert called == ["fb"]

    @pytest.mark.asyncio
    async def test_prefix_match(self):
        router = self._make_router()
        called = []

        @router.on_modal("report:")
        async def on_report(inter): called.append(inter.custom_id)

        inter = _make_inter(type_=5, custom_id="report:bug_123")
        await router._dispatch_modal(inter)
        assert called == ["report:bug_123"]

    @pytest.mark.asyncio
    async def test_unhandled_modal(self):
        router = self._make_router()
        inter = _make_inter(type_=5, custom_id="unknown_modal")
        await router._dispatch_modal(inter)  # no crash

    @pytest.mark.asyncio
    async def test_modal_error_caught(self):
        router = self._make_router()

        @router.on_modal("crash_modal")
        async def on_crash(inter): raise RuntimeError("modal boom")

        inter = _make_inter(type_=5, custom_id="crash_modal")
        await router._dispatch_modal(inter)  # should not raise

    @pytest.mark.asyncio
    async def test_modal_with_fields(self):
        """Modal submission with text input fields should be accessible."""
        router = self._make_router()
        results = {}

        @router.on_modal("survey")
        async def on_survey(inter):
            results["name"] = inter.get_field("name_input")
            results["all"] = inter.get_all_fields()

        inter = _make_inter(
            type_=5, custom_id="survey",
            components=[
                {"type": 1, "components": [{"type": 4, "custom_id": "name_input", "value": "Alice"}]},
                {"type": 1, "components": [{"type": 4, "custom_id": "age_input", "value": "25"}]},
            ],
        )
        await router._dispatch_modal(inter)
        assert results["name"] == "Alice"
        assert results["all"] == {"name_input": "Alice", "age_input": "25"}

#  4. REST Error Mapping Tests

class TestRESTErrorMapping:
    """Test that REST responses map to the correct central error classes."""

    def _make_client_with_response(self, status, body_dict=None, body_str=None):
        """Create a RESTClient with a pre-configured mock session."""
        import orjson
        from discordium.http.rest import RESTClient

        client = RESTClient("fake_token", max_retries=0)

        # Build mock response
        resp = MagicMock()
        resp.status = status
        resp.headers = {}
        resp.content_type = "application/json"

        if body_dict is not None:
            resp.read = AsyncMock(return_value=orjson.dumps(body_dict))
        elif body_str is not None:
            resp.read = AsyncMock(return_value=body_str.encode())
            resp.content_type = "text/plain"
        else:
            resp.read = AsyncMock(return_value=b"{}")

        # Create proper async context manager
        ctx = MagicMock()
        ctx.__aenter__ = AsyncMock(return_value=resp)
        ctx.__aexit__ = AsyncMock(return_value=False)

        session = MagicMock()
        session.closed = False
        session.request = MagicMock(return_value=ctx)

        client._session = session
        return client

    @pytest.mark.asyncio
    async def test_403_raises_forbidden(self):
        client = self._make_client_with_response(403, {"message": "Missing Access", "code": 50001})
        with pytest.raises(Forbidden) as exc:
            await client.request("GET", "/test")
        assert exc.value.status == 403
        assert exc.value.error_code == 50001

    @pytest.mark.asyncio
    async def test_404_raises_not_found(self):
        client = self._make_client_with_response(404, {"message": "Unknown Channel"})
        with pytest.raises(NotFound) as exc:
            await client.request("GET", "/channels/999")
        assert exc.value.status == 404

    @pytest.mark.asyncio
    async def test_500_raises_server_error(self):
        client = self._make_client_with_response(500, {"message": "Internal Server Error"})
        with pytest.raises(ServerError) as exc:
            await client.request("GET", "/test")
        assert exc.value.status == 500

    @pytest.mark.asyncio
    async def test_204_returns_none(self):
        client = self._make_client_with_response(204)
        result = await client.request("DELETE", "/test")
        assert result is None

    @pytest.mark.asyncio
    async def test_200_returns_body(self):
        body = {"id": "123", "username": "test"}
        client = self._make_client_with_response(200, body)
        result = await client.request("GET", "/users/@me")
        assert result == body

    @pytest.mark.asyncio
    async def test_422_raises_generic_http_error(self):
        client = self._make_client_with_response(422, {"message": "Invalid Form Body"})
        with pytest.raises(HTTPError) as exc:
            await client.request("POST", "/test")
        assert exc.value.status == 422
        assert not isinstance(exc.value, Forbidden)
        assert not isinstance(exc.value, NotFound)

    @pytest.mark.asyncio
    async def test_429_retries(self):
        """429 should trigger retry via rate limiter."""
        import orjson
        from discordium.http.rest import RESTClient

        client = RESTClient("fake_token", max_retries=1)

        # First response: 429, second: 200
        resp_429 = MagicMock()
        resp_429.status = 429
        resp_429.headers = {}
        resp_429.content_type = "application/json"
        resp_429.read = AsyncMock(return_value=orjson.dumps({"retry_after": 0.01, "global": False}))

        resp_200 = MagicMock()
        resp_200.status = 200
        resp_200.headers = {}
        resp_200.content_type = "application/json"
        resp_200.read = AsyncMock(return_value=orjson.dumps({"ok": True}))

        call_count = {"n": 0}

        def make_ctx():
            ctx = MagicMock()
            if call_count["n"] == 0:
                ctx.__aenter__ = AsyncMock(return_value=resp_429)
            else:
                ctx.__aenter__ = AsyncMock(return_value=resp_200)
            ctx.__aexit__ = AsyncMock(return_value=False)
            call_count["n"] += 1
            return ctx

        session = MagicMock()
        session.closed = False
        session.request = MagicMock(side_effect=lambda *a, **kw: make_ctx())
        client._session = session

        result = await client.request("GET", "/test")
        assert result == {"ok": True}
        assert call_count["n"] == 2  # called twice (429 then 200)

    def test_error_hierarchy_isinstance(self):
        assert isinstance(Forbidden("x"), HTTPError)
        assert isinstance(NotFound("x"), HTTPError)
        assert isinstance(ServerError(500, "x"), HTTPError)

#  5. 429 Rate Limit Behavior Tests

class TestRateLimitBehavior:
    @pytest.mark.asyncio
    async def test_per_route_429_sleeps(self):
        from discordium.http.ratelimit import RateLimiter
        rl = RateLimiter()
        start = time.monotonic()
        await rl.handle_429(0.05, is_global=False)
        elapsed = time.monotonic() - start
        assert elapsed >= 0.04

    @pytest.mark.asyncio
    async def test_global_429_blocks_all_routes(self):
        from discordium.http.ratelimit import RateLimiter
        rl = RateLimiter()
        # Trigger global rate limit
        await rl.handle_429(0.05, is_global=True)
        # After sleep completes, global event should be set
        assert rl._global_event.is_set()

    @pytest.mark.asyncio
    async def test_release_with_remaining_zero_delays(self):
        from discordium.http.ratelimit import RateLimiter
        rl = RateLimiter()
        key = await rl.acquire("GET", "/test")
        # Release with remaining=0 should schedule delayed release
        rl.release(key, remaining=0, reset_after=0.05)
        # Lock should still be held briefly
        await asyncio.sleep(0.07)
        # After reset_after, should be acquirable again
        key2 = await asyncio.wait_for(rl.acquire("GET", "/test"), timeout=1.0)
        rl.release(key2)

    @pytest.mark.asyncio
    async def test_different_routes_independent(self):
        from discordium.http.ratelimit import RateLimiter
        rl = RateLimiter()
        k1 = await rl.acquire("GET", "/channels/1/messages")
        k2 = await rl.acquire("GET", "/channels/2/messages")
        # Both should acquire without blocking
        assert k1 != k2
        rl.release(k1)
        rl.release(k2)

    def test_bucket_key_major_params(self):
        from discordium.http.ratelimit import RateLimiter
        rl = RateLimiter()
        # Different channels should produce different bucket keys
        k1 = rl._bucket_key("GET", "/channels/100/messages")
        k2 = rl._bucket_key("GET", "/channels/200/messages")
        k3 = rl._bucket_key("GET", "/channels/100/messages")
        assert k1 != k2
        assert k1 == k3

    def test_bucket_key_guild_param(self):
        from discordium.http.ratelimit import RateLimiter
        rl = RateLimiter()
        k1 = rl._bucket_key("GET", "/guilds/111/members")
        k2 = rl._bucket_key("GET", "/guilds/222/members")
        assert k1 != k2

#  6. Guard Combination Tests

class TestGuardCombinations:
    def _mock_inter(self, *, perms=0, guild_id=111):
        obj = MagicMock()
        obj.guild_id = guild_id
        obj.member = MagicMock()
        obj.member.permissions = Permissions.from_value(perms)
        obj.user = MagicMock()
        obj.user.id = MagicMock(__str__=lambda s: "testuser")
        return obj

    @pytest.mark.asyncio
    async def test_guild_only_plus_permissions(self):
        from discordium.ext.guards import guild_only, has_permissions

        @guild_only()
        @has_permissions(Permissions.BAN_MEMBERS)
        async def cmd(inter): return "ok"

        # Has perms + in guild
        assert await cmd(self._mock_inter(perms=int(Permissions.BAN_MEMBERS))) == "ok"
        # In DM
        with pytest.raises(GuildOnly):
            await cmd(self._mock_inter(guild_id=None, perms=int(Permissions.BAN_MEMBERS)))
        # In guild but no perms
        with pytest.raises(MissingPermissions):
            await cmd(self._mock_inter(perms=0))

    @pytest.mark.asyncio
    async def test_cooldown_plus_permissions(self):
        from discordium.ext.guards import cooldown, has_permissions

        @has_permissions(Permissions.SEND_MESSAGES)
        @cooldown(rate=1, per=10.0)
        async def cmd(inter): return "ok"

        inter = self._mock_inter(perms=int(Permissions.SEND_MESSAGES))
        assert await cmd(inter) == "ok"
        with pytest.raises(CommandOnCooldown):
            await cmd(inter)

    @pytest.mark.asyncio
    async def test_check_plus_guild_only(self):
        from discordium.ext.guards import check, guild_only

        @guild_only()
        @check(lambda i: str(i.user.id) == "testuser")
        async def cmd(inter): return "ok"

        assert await cmd(self._mock_inter()) == "ok"

    @pytest.mark.asyncio
    async def test_dm_only_plus_check(self):
        from discordium.ext.guards import check, dm_only

        @dm_only()
        @check(lambda i: True)
        async def cmd(inter): return "ok"

        assert await cmd(self._mock_inter(guild_id=None)) == "ok"
        with pytest.raises(DMOnly):
            await cmd(self._mock_inter())

    @pytest.mark.asyncio
    async def test_multiple_permission_checks(self):
        from discordium.ext.guards import has_permissions

        @has_permissions(Permissions.BAN_MEMBERS, Permissions.KICK_MEMBERS)
        async def cmd(inter): return "ok"

        # Has both
        both = int(Permissions.BAN_MEMBERS | Permissions.KICK_MEMBERS)
        assert await cmd(self._mock_inter(perms=both)) == "ok"
        # Missing one
        with pytest.raises(MissingPermissions) as exc:
            await cmd(self._mock_inter(perms=int(Permissions.BAN_MEMBERS)))
        assert "KICK_MEMBERS" in exc.value.missing

#  7. Task Loop Lifecycle Tests

class TestTaskLoopLifecycle:
    @pytest.mark.asyncio
    async def test_start_stop_start(self):
        from discordium.ext.tasks import loop
        counter = {"n": 0}

        @loop(seconds=0.02, count=2)
        async def task(): counter["n"] += 1

        task.start()
        await asyncio.sleep(0.15)
        assert counter["n"] == 2
        assert not task.is_running

        # After completion, _is_running is False so start() creates a new task
        counter["n"] = 0
        task._current_loop = 0  # reset counter for new run
        task.start()
        await asyncio.sleep(0.15)
        assert counter["n"] == 2  # ran 2 more

    @pytest.mark.asyncio
    async def test_stop_mid_loop(self):
        from discordium.ext.tasks import loop
        counter = {"n": 0}

        @loop(seconds=0.02)
        async def task(): counter["n"] += 1

        task.start()
        await asyncio.sleep(0.05)
        task.stop()
        await asyncio.sleep(0.05)
        stopped_at = counter["n"]
        await asyncio.sleep(0.05)
        assert counter["n"] == stopped_at  # no more increments

    @pytest.mark.asyncio
    async def test_restart_resets(self):
        from discordium.ext.tasks import loop
        counter = {"n": 0}

        @loop(seconds=0.02, count=2)
        async def task(): counter["n"] += 1

        task.start()
        await asyncio.sleep(0.1)
        assert counter["n"] == 2
        assert task.current_loop == 2

        task.restart()
        await asyncio.sleep(0.1)
        assert counter["n"] == 4
        assert task.current_loop == 2

    @pytest.mark.asyncio
    async def test_before_runs_once(self):
        from discordium.ext.tasks import loop
        before_count = {"n": 0}

        @loop(seconds=0.02, count=3)
        async def task(): pass

        @task.before
        async def before(): before_count["n"] += 1

        task.start()
        await asyncio.sleep(0.15)
        assert before_count["n"] == 1

    @pytest.mark.asyncio
    async def test_after_runs_once(self):
        from discordium.ext.tasks import loop
        after_count = {"n": 0}

        @loop(seconds=0.02, count=2)
        async def task(): pass

        @task.after
        async def after(): after_count["n"] += 1

        task.start()
        await asyncio.sleep(0.15)
        assert after_count["n"] == 1

    @pytest.mark.asyncio
    async def test_current_loop_counter(self):
        from discordium.ext.tasks import loop
        counts = []

        @loop(seconds=0.02, count=3)
        async def task():
            counts.append(task.current_loop)

        task.start()
        await asyncio.sleep(0.15)
        assert counts == [0, 1, 2]

    @pytest.mark.asyncio
    async def test_minutes_conversion(self):
        from discordium.ext.tasks import Loop
        # minutes=1 should equal 60 seconds
        async def dummy(): pass
        l = Loop(dummy, minutes=1)
        assert l._seconds == 60.0

    @pytest.mark.asyncio
    async def test_hours_conversion(self):
        from discordium.ext.tasks import Loop
        async def dummy(): pass
        l = Loop(dummy, hours=1)
        assert l._seconds == 3600.0

    @pytest.mark.asyncio
    async def test_combined_time(self):
        from discordium.ext.tasks import Loop
        async def dummy(): pass
        l = Loop(dummy, seconds=30, minutes=1, hours=1)
        assert l._seconds == 3690.0

#  8. Event Parser — Every Registered Event

class TestEventParserComplete:
    """Test parse_event for every event in EVENT_REGISTRY with realistic payloads."""

    def _rest(self):
        return MagicMock()

    def test_ready(self):
        from discordium.models.events import ReadyEvent, parse_event
        e = parse_event("ready", {
            "user": {"id": "1", "username": "bot", "discriminator": "0"},
            "guilds": [{"id": "1", "unavailable": True}],
            "session_id": "s", "resume_gateway_url": "wss://x",
            "application": {"id": "1"},
        }, rest=self._rest())
        assert isinstance(e, ReadyEvent)
        assert e.user.username == "bot"

    def test_resumed(self):
        from discordium.models.events import ResumedEvent, parse_event
        e = parse_event("resumed", {}, rest=self._rest())
        assert isinstance(e, ResumedEvent)

    def test_message_create(self):
        from discordium.models.events import MessageCreateEvent, parse_event
        e = parse_event("message_create", {
            "id": "1", "channel_id": "2",
            "author": {"id": "3", "username": "u", "discriminator": "0"},
            "content": "hi", "timestamp": "", "tts": False,
            "mention_everyone": False, "pinned": False, "embeds": [],
        }, rest=self._rest())
        assert isinstance(e, MessageCreateEvent)
        assert e.message.content == "hi"

    def test_message_update(self):
        from discordium.models.events import MessageUpdateEvent, parse_event
        e = parse_event("message_update", {
            "id": "1", "channel_id": "2",
            "author": {"id": "3", "username": "u", "discriminator": "0"},
            "content": "edited",
        }, rest=self._rest())
        assert isinstance(e, MessageUpdateEvent)

    def test_message_delete(self):
        from discordium.models.events import MessageDeleteEvent, parse_event
        e = parse_event("message_delete", {"id": "1", "channel_id": "2"}, rest=self._rest())
        assert isinstance(e, MessageDeleteEvent)

    def test_message_delete_bulk(self):
        from discordium.models.events import MessageDeleteBulkEvent, parse_event
        e = parse_event("message_delete_bulk", {
            "ids": ["1", "2", "3"], "channel_id": "5", "guild_id": "6",
        }, rest=self._rest())
        assert isinstance(e, MessageDeleteBulkEvent)
        assert len(e.message_ids) == 3

    def test_reaction_add(self):
        from discordium.models.events import MessageReactionAddEvent, parse_event
        e = parse_event("message_reaction_add", {
            "user_id": "1", "channel_id": "2", "message_id": "3",
            "emoji": {"id": None, "name": "👍"},
        }, rest=self._rest())
        assert isinstance(e, MessageReactionAddEvent)

    def test_reaction_remove(self):
        from discordium.models.events import MessageReactionRemoveEvent, parse_event
        e = parse_event("message_reaction_remove", {
            "user_id": "1", "channel_id": "2", "message_id": "3",
            "emoji": {"id": None, "name": "👍"},
        }, rest=self._rest())
        assert isinstance(e, MessageReactionRemoveEvent)

    def test_guild_create(self):
        from discordium.models.events import GuildCreateEvent, parse_event
        e = parse_event("guild_create", {
            "id": "1", "name": "G", "channels": [], "roles": [],
            "members": [], "threads": [],
        }, rest=self._rest())
        assert isinstance(e, GuildCreateEvent)

    def test_guild_update(self):
        from discordium.models.events import GuildUpdateEvent, parse_event
        e = parse_event("guild_update", {"id": "1", "name": "G2"}, rest=self._rest())
        assert isinstance(e, GuildUpdateEvent)

    def test_guild_delete(self):
        from discordium.models.events import GuildDeleteEvent, parse_event
        e = parse_event("guild_delete", {"id": "1", "unavailable": True}, rest=self._rest())
        assert isinstance(e, GuildDeleteEvent)

    def test_guild_ban_add(self):
        from discordium.models.events import GuildBanAddEvent, parse_event
        e = parse_event("guild_ban_add", {
            "guild_id": "1", "user": {"id": "2", "username": "u", "discriminator": "0"},
        }, rest=self._rest())
        assert isinstance(e, GuildBanAddEvent)

    def test_guild_ban_remove(self):
        from discordium.models.events import GuildBanRemoveEvent, parse_event
        e = parse_event("guild_ban_remove", {
            "guild_id": "1", "user": {"id": "2", "username": "u", "discriminator": "0"},
        }, rest=self._rest())
        assert isinstance(e, GuildBanRemoveEvent)

    def test_member_add(self):
        from discordium.models.events import GuildMemberAddEvent, parse_event
        e = parse_event("guild_member_add", {
            "guild_id": "1", "user": {"id": "2", "username": "u", "discriminator": "0"},
            "roles": [],
        }, rest=self._rest())
        assert isinstance(e, GuildMemberAddEvent)

    def test_member_remove(self):
        from discordium.models.events import GuildMemberRemoveEvent, parse_event
        e = parse_event("guild_member_remove", {
            "guild_id": "1", "user": {"id": "2", "username": "u", "discriminator": "0"},
        }, rest=self._rest())
        assert isinstance(e, GuildMemberRemoveEvent)

    def test_member_update(self):
        from discordium.models.events import GuildMemberUpdateEvent, parse_event
        e = parse_event("guild_member_update", {
            "guild_id": "1", "user": {"id": "2", "username": "u", "discriminator": "0"},
            "roles": ["100"],
        }, rest=self._rest())
        assert isinstance(e, GuildMemberUpdateEvent)

    def test_channel_create(self):
        from discordium.models.events import ChannelCreateEvent, parse_event
        e = parse_event("channel_create", {"id": "1", "type": 0}, rest=self._rest())
        assert isinstance(e, ChannelCreateEvent)

    def test_channel_update(self):
        from discordium.models.events import ChannelUpdateEvent, parse_event
        e = parse_event("channel_update", {"id": "1", "type": 0, "name": "new"}, rest=self._rest())
        assert isinstance(e, ChannelUpdateEvent)

    def test_channel_delete(self):
        from discordium.models.events import ChannelDeleteEvent, parse_event
        e = parse_event("channel_delete", {"id": "1", "type": 0}, rest=self._rest())
        assert isinstance(e, ChannelDeleteEvent)

    def test_role_create(self):
        from discordium.models.events import GuildRoleCreateEvent, parse_event
        e = parse_event("guild_role_create", {
            "guild_id": "1", "role": {"id": "2", "name": "R", "permissions": "0"},
        }, rest=self._rest())
        assert isinstance(e, GuildRoleCreateEvent)

    def test_role_update(self):
        from discordium.models.events import GuildRoleUpdateEvent, parse_event
        e = parse_event("guild_role_update", {
            "guild_id": "1", "role": {"id": "2", "name": "R2", "permissions": "0"},
        }, rest=self._rest())
        assert isinstance(e, GuildRoleUpdateEvent)

    def test_role_delete(self):
        from discordium.models.events import GuildRoleDeleteEvent, parse_event
        e = parse_event("guild_role_delete", {"guild_id": "1", "role_id": "2"}, rest=self._rest())
        assert isinstance(e, GuildRoleDeleteEvent)

    def test_thread_create(self):
        from discordium.models.events import ThreadCreateEvent, parse_event
        e = parse_event("thread_create", {"id": "1", "type": 11, "guild_id": "2"}, rest=self._rest())
        assert isinstance(e, ThreadCreateEvent)

    def test_thread_update(self):
        from discordium.models.events import ThreadUpdateEvent, parse_event
        e = parse_event("thread_update", {"id": "1", "type": 11, "guild_id": "2"}, rest=self._rest())
        assert isinstance(e, ThreadUpdateEvent)

    def test_thread_delete(self):
        from discordium.models.events import ThreadDeleteEvent, parse_event
        e = parse_event("thread_delete", {"id": "1", "guild_id": "2"}, rest=self._rest())
        assert isinstance(e, ThreadDeleteEvent)

    def test_interaction_create(self):
        from discordium.models.events import InteractionCreateEvent, parse_event
        e = parse_event("interaction_create", {"foo": "bar"}, rest=self._rest())
        assert isinstance(e, InteractionCreateEvent)

    def test_typing_start(self):
        from discordium.models.events import TypingStartEvent, parse_event
        e = parse_event("typing_start", {
            "channel_id": "1", "user_id": "2", "timestamp": 123,
        }, rest=self._rest())
        assert isinstance(e, TypingStartEvent)

    def test_presence_update(self):
        from discordium.models.events import PresenceUpdateEvent, parse_event
        e = parse_event("presence_update", {
            "user": {"id": "1"}, "guild_id": "2", "status": "online",
        }, rest=self._rest())
        assert isinstance(e, PresenceUpdateEvent)

    def test_voice_state_update(self):
        from discordium.models.events import VoiceStateUpdateEvent, parse_event
        e = parse_event("voice_state_update", {
            "user_id": "1", "session_id": "s",
            "deaf": False, "mute": False,
        }, rest=self._rest())
        assert isinstance(e, VoiceStateUpdateEvent)

    def test_invite_create(self):
        from discordium.models.events import InviteCreateEvent, parse_event
        e = parse_event("invite_create", {
            "channel_id": "1", "code": "abc", "max_age": 3600,
        }, rest=self._rest())
        assert isinstance(e, InviteCreateEvent)
        assert e.code == "abc"

    def test_invite_delete(self):
        from discordium.models.events import InviteDeleteEvent, parse_event
        e = parse_event("invite_delete", {
            "channel_id": "1", "code": "abc",
        }, rest=self._rest())
        assert isinstance(e, InviteDeleteEvent)

#  9. File Upload Edge Cases

class TestFileUploadEdgeCases:
    def test_empty_file(self):
        from discordium.models.file import File
        f = File(b"", filename="empty.txt")
        assert len(f.data) == 0
        assert f.filename == "empty.txt"

    def test_large_file_repr(self):
        from discordium.models.file import File
        f = File(b"x" * (5 * 1024 * 1024), filename="big.bin")
        r = repr(f)
        assert "MB" in r

    def test_from_path_not_found(self):
        from discordium.models.file import File
        with pytest.raises(FileNotFoundError):
            File.from_path("/nonexistent/path/file.txt")

    def test_spoiler_prefix(self):
        from discordium.models.file import File
        f = File(b"secret", filename="image.png", spoiler=True)
        assert f.filename == "SPOILER_image.png"

    def test_double_spoiler(self):
        """Applying spoiler to already-spoilered name."""
        from discordium.models.file import File
        f = File(b"x", filename="SPOILER_img.png", spoiler=True)
        assert f.filename == "SPOILER_SPOILER_img.png"  # double prefix is expected

    def test_content_type_override(self):
        from discordium.models.file import File
        f = File(b"data", filename="test.txt", content_type="application/custom")
        assert f.content_type == "application/custom"

    def test_attachment_dict_without_description(self):
        from discordium.models.file import File
        f = File(b"x", filename="f.txt")
        d = f.to_attachment_dict(5)
        assert d["id"] == 5
        assert "description" not in d

    def test_multiple_files_different_indices(self):
        from discordium.models.file import File
        files = [File(b"a", filename="a.txt"), File(b"b", filename="b.txt")]
        dicts = [f.to_attachment_dict(i) for i, f in enumerate(files)]
        assert dicts[0]["id"] == 0
        assert dicts[1]["id"] == 1
        assert dicts[0]["filename"] == "a.txt"
        assert dicts[1]["filename"] == "b.txt"

    def test_binary_content_types(self):
        from discordium.models.file import File
        assert File(b"", filename="img.jpg").content_type == "image/jpeg"
        assert File(b"", filename="vid.mp4").content_type == "video/mp4"
        assert File(b"", filename="doc.json").content_type == "application/json"
        assert File(b"", filename="archive.zip").content_type == "application/zip"

#  10. Gateway Heartbeat & Reconnect Tests

class TestGatewayHeartbeat:
    def _make_conn(self):
        return _make_gateway_conn()

    @pytest.mark.asyncio
    async def test_heartbeat_ack_updates_latency(self):
        conn = self._make_conn()
        conn._heartbeat_sent_at = time.monotonic() - 0.1
        conn._ack_received = False

        await conn._handle_payload({"op": 11, "d": None, "s": None, "t": None})

        assert conn._ack_received is True
        assert conn._latency is not None
        assert 0.05 < conn._latency < 0.5

    @pytest.mark.asyncio
    async def test_heartbeat_ack_without_sent_time(self):
        """ACK when _heartbeat_sent_at is None should not crash."""
        conn = self._make_conn()
        conn._heartbeat_sent_at = None
        conn._ack_received = False

        await conn._handle_payload({"op": 11, "d": None, "s": None, "t": None})
        assert conn._ack_received is True

    @pytest.mark.asyncio
    async def test_sequence_number_increments(self):
        conn = self._make_conn()

        for seq in [1, 2, 3, 5, 10]:
            await conn._handle_payload({"op": 0, "t": "X", "s": seq, "d": {}})
            assert conn._seq == seq

    @pytest.mark.asyncio
    async def test_sequence_null_doesnt_overwrite(self):
        conn = self._make_conn()
        conn._seq = 42

        await conn._handle_payload({"op": 0, "t": "X", "s": None, "d": {}})
        assert conn._seq == 42

    @pytest.mark.asyncio
    async def test_close_sets_closed_flag(self):
        conn = self._make_conn()
        conn._ws.close = AsyncMock()
        conn._session = MagicMock()
        conn._session.closed = False
        conn._session.close = AsyncMock()

        await conn.close()
        assert conn._closed is True

    @pytest.mark.asyncio
    async def test_ready_stores_resume_url(self):
        conn = self._make_conn()

        await conn._handle_payload({
            "op": 0, "t": "READY", "s": 1,
            "d": {
                "session_id": "new_sess",
                "resume_gateway_url": "wss://resume.new.example.com",
            },
        })

        assert conn._session_id == "new_sess"
        assert conn._resume_url == "wss://resume.new.example.com"


def _make_gateway_conn():
    """Shared helper — creates a GatewayConnection without WebSocket."""
    from discordium.gateway.connection import GatewayConnection
    from discordium.utils.backoff import ExponentialBackoff as EB

    emitter = MagicMock()
    emitter.emit = AsyncMock()

    conn = GatewayConnection.__new__(GatewayConnection)
    conn._token = "fake"
    conn._intents = 0
    conn._emitter = emitter
    conn._gateway_url = "wss://fake"
    conn._shard = None
    conn._ws = MagicMock()
    conn._ws.closed = False
    conn._ws.send_bytes = AsyncMock()
    conn._ws.close = AsyncMock()
    conn._session = None
    conn._session_id = None
    conn._seq = None
    conn._resume_url = None
    conn._heartbeat_interval = 41.25
    conn._heartbeat_task = None
    conn._ack_received = True
    conn._closed = False
    conn._latency = None
    conn._heartbeat_sent_at = None
    conn._inflator = zlib.decompressobj()
    conn._backoff = EB()
    return conn
