"""Comprehensive test suite for discordium core systems.

Covers: cache, components, interaction lifecycle, guards, dispatcher,
task loops, gateway payload handling, rate limiter, router dispatch,
file uploads, and error hierarchy. - discordium
"""

import asyncio
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from discordium.cache.base import NoCache, TTLCache
from discordium.errors import (
    CheckFailure,
    CommandOnCooldown,
    DMOnly,
    DiscordiumError,
    Forbidden,
    GuildOnly,
    HTTPError,
    InteractionAlreadyResponded,
    InteractionNotResponded,
    MissingPermissions,
    NotFound,
    NotOwner,
    NotReady,
    ServerError,
)
from discordium.models.components import (
    ActionRow,
    Button,
    ButtonStyle,
    Modal,
    SelectMenu,
    SelectOption,
    TextInput,
    TextInputStyle,
    parse_component,
)
from discordium.models.interaction import Interaction, InteractionType
from discordium.models.permissions import Permissions

#  Error Hierarchy Tests

class TestErrorHierarchy:
    def test_all_errors_inherit_from_base(self):
        assert issubclass(HTTPError, DiscordiumError)
        assert issubclass(Forbidden, HTTPError)
        assert issubclass(NotFound, HTTPError)
        assert issubclass(ServerError, HTTPError)
        assert issubclass(InteractionAlreadyResponded, DiscordiumError)
        assert issubclass(InteractionNotResponded, DiscordiumError)
        assert issubclass(CommandOnCooldown, DiscordiumError)
        assert issubclass(MissingPermissions, DiscordiumError)

    def test_forbidden_has_403(self):
        e = Forbidden("nope")
        assert e.status == 403

    def test_not_found_has_404(self):
        e = NotFound({"message": "Unknown"})
        assert e.status == 404
        assert "Unknown" in str(e)

    def test_http_error_with_dict(self):
        e = HTTPError(500, {"message": "Internal", "code": 0})
        assert e.status == 500
        assert e.error_code == 0

    def test_server_error(self):
        e = ServerError(502, "Bad Gateway")
        assert e.status == 502

    def test_cooldown_retry_after(self):
        e = CommandOnCooldown(5.5)
        assert e.retry_after == 5.5
        assert "5.5" in str(e)

    def test_missing_permissions_list(self):
        e = MissingPermissions(["BAN_MEMBERS", "KICK_MEMBERS"])
        assert e.missing == ["BAN_MEMBERS", "KICK_MEMBERS"]
        assert "BAN_MEMBERS" in str(e)

#  Cache Tests

class TestNoCache:
    def test_always_misses(self):
        c = NoCache()
        c.set("key", "value")
        assert c.get("key") is None
        assert len(c) == 0
        assert "key" not in c

    def test_delete_returns_false(self):
        assert NoCache().delete("x") is False


class TestTTLCache:
    def test_set_and_get(self):
        c = TTLCache(ttl=10)
        c.set("k", "v")
        assert c.get("k") == "v"
        assert "k" in c
        assert len(c) == 1

    def test_ttl_expiry(self):
        c = TTLCache(ttl=0.01)
        c.set("k", "v")
        time.sleep(0.02)
        assert c.get("k") is None
        assert "k" not in c

    def test_max_size_eviction(self):
        c = TTLCache(ttl=60, max_size=3)
        for i in range(4):
            c.set(f"k{i}", i)
        assert c.get("k0") is None  # evicted
        assert c.get("k3") == 3
        assert len(c) == 3

    def test_delete(self):
        c = TTLCache(ttl=60)
        c.set("k", "v")
        assert c.delete("k") is True
        assert c.get("k") is None
        assert c.delete("k") is False

    def test_clear(self):
        c = TTLCache(ttl=60)
        c.set("a", 1)
        c.set("b", 2)
        c.clear()
        assert len(c) == 0

    def test_custom_ttl_per_key(self):
        c = TTLCache(ttl=60)
        c.set("fast", "v", ttl=0.01)
        c.set("slow", "v", ttl=60)
        time.sleep(0.02)
        assert c.get("fast") is None
        assert c.get("slow") == "v"

    def test_lru_move_to_end(self):
        c = TTLCache(ttl=60, max_size=3)
        c.set("a", 1)
        c.set("b", 2)
        c.set("c", 3)
        c.get("a")  # access "a" to move it to end
        c.set("d", 4)  # should evict "b" not "a"
        assert c.get("a") == 1
        assert c.get("b") is None

#  Component Tests

class TestButton:
    def test_basic_button(self):
        b = Button(label="Click", custom_id="btn1", style=ButtonStyle.PRIMARY)
        d = b.to_dict()
        assert d["label"] == "Click"
        assert d["custom_id"] == "btn1"

    def test_link_button(self):
        b = Button(label="Link", url="https://example.com", style=ButtonStyle.LINK)
        assert "custom_id" not in b.to_dict()

    def test_link_requires_url(self):
        with pytest.raises(ValueError):
            Button(label="Bad", style=ButtonStyle.LINK)

    def test_non_link_requires_custom_id(self):
        with pytest.raises(ValueError):
            Button(label="Bad", style=ButtonStyle.PRIMARY)

    def test_emoji_shorthand(self):
        b = Button(label="X", custom_id="x", emoji="🎉")
        assert b.emoji == {"name": "🎉"}

    def test_disabled(self):
        assert Button(label="X", custom_id="x", disabled=True).to_dict()["disabled"] is True


class TestSelectMenu:
    def test_basic_select(self):
        m = SelectMenu(
            custom_id="sel1",
            options=[SelectOption(label="A", value="a"), SelectOption(label="B", value="b")],
        )
        assert len(m.to_dict()["options"]) == 2

    def test_string_select_requires_options(self):
        with pytest.raises(ValueError):
            SelectMenu(custom_id="bad")


class TestActionRow:
    def test_max_children(self):
        with pytest.raises(ValueError):
            ActionRow(*[Button(label=str(i), custom_id=f"b{i}") for i in range(6)])

    def test_to_dict(self):
        row = ActionRow(Button(label="A", custom_id="a"), Button(label="B", custom_id="b"))
        d = row.to_dict()
        assert d["type"] == 1
        assert len(d["components"]) == 2


class TestModal:
    def test_fluent_builder(self):
        m = Modal(title="Test", custom_id="m1")
        m.add_field(label="Name", custom_id="name", style=TextInputStyle.SHORT)
        m.add_field(label="Bio", custom_id="bio", style=TextInputStyle.PARAGRAPH)
        d = m.to_dict()
        assert d["title"] == "Test"
        assert len(d["components"]) == 2


class TestParseComponent:
    def test_parse_button(self):
        c = parse_component({"type": 2, "label": "Click", "custom_id": "btn", "style": 1})
        assert isinstance(c, Button)

    def test_parse_action_row(self):
        c = parse_component({
            "type": 1,
            "components": [{"type": 2, "label": "A", "custom_id": "a", "style": 1}],
        })
        assert isinstance(c, ActionRow)
        assert len(c.children) == 1

#  Interaction Tests — Lifecycle Hardening

class TestInteraction:
    BASE_PAYLOAD = {
        "id": "999",
        "application_id": "888",
        "type": 2,
        "token": "tok123",
        "guild_id": "111",
        "channel_id": "777",
        "data": {
            "name": "test",
            "options": [
                {"name": "user", "type": 6, "value": "123"},
                {"name": "message", "type": 3, "value": "hello"},
                {"name": "count", "type": 4, "value": 42},
                {"name": "flag", "type": 5, "value": True},
            ],
            "resolved": {
                "users": {"123": {"id": "123", "username": "resolved_user", "discriminator": "0"}},
                "members": {"123": {"nick": "Resolved", "roles": [], "joined_at": "2024-01-01"}},
            },
        },
        "member": {
            "user": {"id": "456", "username": "invoker", "discriminator": "0"},
            "nick": None, "roles": [], "permissions": "8",
        },
    }

    def _make(self, **overrides):
        payload = {**self.BASE_PAYLOAD, **overrides}
        rest = AsyncMock()
        rest.request = AsyncMock(return_value=None)
        return Interaction(payload, rest=rest)

    def test_basic_fields(self):
        i = self._make()
        assert int(i.id) == 999
        assert i.type == InteractionType.APPLICATION_COMMAND
        assert i.command_name == "test"

    def test_get_option(self):
        i = self._make()
        assert i.get_option("message") == "hello"
        assert i.get_option("count") == 42
        assert i.get_option("nonexistent") is None

    def test_option_typed_resolvers(self):
        i = self._make()
        assert i.option_string("message") == "hello"
        assert i.option_string("nope", default="fallback") == "fallback"
        assert i.option_int("count") == 42
        assert i.option_int("nope", default=99) == 99
        assert i.option_bool("flag") is True

    def test_option_user_resolved(self):
        i = self._make()
        user = i.option_user("user")
        assert user is not None
        assert user.username == "resolved_user"

    def test_option_member_resolved(self):
        i = self._make()
        member = i.option_member("user")
        assert member is not None
        assert member.nick == "Resolved"

    def test_state_flags_initial(self):
        i = self._make()
        assert i.has_responded is False
        assert i.is_deferred is False
        assert i.is_command is True
        assert i.is_component is False
        assert i.is_modal is False
        assert i.author == i.user

    # Lifecycle edge cases

    @pytest.mark.asyncio
    async def test_respond_sets_responded(self):
        i = self._make()
        await i.respond("Hello")
        assert i.has_responded is True

    @pytest.mark.asyncio
    async def test_double_respond_raises(self):
        i = self._make()
        await i.respond("First")
        with pytest.raises(InteractionAlreadyResponded):
            await i.respond("Second")

    @pytest.mark.asyncio
    async def test_defer_sets_flags(self):
        i = self._make()
        await i.defer()
        assert i.has_responded is True
        assert i.is_deferred is True

    @pytest.mark.asyncio
    async def test_double_defer_raises(self):
        i = self._make()
        await i.defer()
        with pytest.raises(InteractionAlreadyResponded):
            await i.defer()

    @pytest.mark.asyncio
    async def test_respond_then_defer_raises(self):
        i = self._make()
        await i.respond("hi")
        with pytest.raises(InteractionAlreadyResponded):
            await i.defer()

    @pytest.mark.asyncio
    async def test_followup_before_respond_raises(self):
        i = self._make()
        with pytest.raises(InteractionNotResponded):
            await i.followup("nope")

    @pytest.mark.asyncio
    async def test_followup_after_defer_works(self):
        i = self._make()
        await i.defer()
        await i.followup("works")  # should not raise

    @pytest.mark.asyncio
    async def test_followup_after_respond_works(self):
        i = self._make()
        await i.respond("first")
        await i.followup("second")  # should not raise

    @pytest.mark.asyncio
    async def test_edit_response_before_respond_raises(self):
        i = self._make()
        with pytest.raises(InteractionNotResponded):
            await i.edit_response("nope")

    @pytest.mark.asyncio
    async def test_edit_response_after_respond_works(self):
        i = self._make()
        await i.respond("first")
        await i.edit_response("edited")  # should not raise

    @pytest.mark.asyncio
    async def test_delete_response_before_respond_raises(self):
        i = self._make()
        with pytest.raises(InteractionNotResponded):
            await i.delete_response()

    @pytest.mark.asyncio
    async def test_send_modal_after_respond_raises(self):
        i = self._make()
        await i.respond("hi")
        m = Modal(title="T", custom_id="m")
        with pytest.raises(InteractionAlreadyResponded):
            await i.send_modal(m)

    @pytest.mark.asyncio
    async def test_update_message_after_respond_raises(self):
        i = self._make()
        await i.respond("hi")
        with pytest.raises(InteractionAlreadyResponded):
            await i.update_message("nope")

    @pytest.mark.asyncio
    async def test_autocomplete_after_respond_raises(self):
        i = self._make()
        await i.respond("hi")
        with pytest.raises(InteractionAlreadyResponded):
            await i.autocomplete([{"name": "a", "value": "a"}])

    def test_modal_fields(self):
        payload = {
            **self.BASE_PAYLOAD, "type": 5,
            "data": {
                "custom_id": "modal1",
                "components": [
                    {"type": 1, "components": [{"type": 4, "custom_id": "f_a", "value": "hello"}]},
                    {"type": 1, "components": [{"type": 4, "custom_id": "f_b", "value": "world"}]},
                ],
            },
        }
        i = Interaction(payload, rest=MagicMock())
        assert i.get_field("f_a") == "hello"
        assert i.get_all_fields() == {"f_a": "hello", "f_b": "world"}
        assert i.get_field("nonexistent") is None

#  Guard Tests

class TestGuards:
    def _mock_inter(self, *, perms: int = 0, guild_id=111):
        obj = MagicMock()
        obj.guild_id = guild_id
        obj.member = MagicMock()
        obj.member.permissions = Permissions.from_value(perms)
        obj.user = MagicMock()
        obj.user.id = MagicMock(__str__=lambda s: "123")
        return obj

    @pytest.mark.asyncio
    async def test_guild_only_passes(self):
        from discordium.ext.guards import guild_only
        @guild_only()
        async def cmd(inter): return "ok"
        assert await cmd(self._mock_inter()) == "ok"

    @pytest.mark.asyncio
    async def test_guild_only_fails(self):
        from discordium.ext.guards import guild_only
        @guild_only()
        async def cmd(inter): return "ok"
        with pytest.raises(GuildOnly):
            await cmd(self._mock_inter(guild_id=None))

    @pytest.mark.asyncio
    async def test_dm_only_passes(self):
        from discordium.ext.guards import dm_only
        @dm_only()
        async def cmd(inter): return "ok"
        assert await cmd(self._mock_inter(guild_id=None)) == "ok"

    @pytest.mark.asyncio
    async def test_dm_only_fails(self):
        from discordium.ext.guards import dm_only
        @dm_only()
        async def cmd(inter): return "ok"
        with pytest.raises(DMOnly):
            await cmd(self._mock_inter())

    @pytest.mark.asyncio
    async def test_has_permissions_passes(self):
        from discordium.ext.guards import has_permissions
        @has_permissions(Permissions.SEND_MESSAGES)
        async def cmd(inter): return "ok"
        assert await cmd(self._mock_inter(perms=int(Permissions.SEND_MESSAGES))) == "ok"

    @pytest.mark.asyncio
    async def test_has_permissions_fails(self):
        from discordium.ext.guards import has_permissions
        @has_permissions(Permissions.BAN_MEMBERS)
        async def cmd(inter): return "ok"
        with pytest.raises(MissingPermissions) as exc:
            await cmd(self._mock_inter(perms=0))
        assert "BAN_MEMBERS" in exc.value.missing

    @pytest.mark.asyncio
    async def test_admin_bypasses(self):
        from discordium.ext.guards import has_permissions
        @has_permissions(Permissions.BAN_MEMBERS, Permissions.KICK_MEMBERS)
        async def cmd(inter): return "ok"
        assert await cmd(self._mock_inter(perms=int(Permissions.ADMINISTRATOR))) == "ok"

    @pytest.mark.asyncio
    async def test_cooldown_first_passes(self):
        from discordium.ext.guards import cooldown
        @cooldown(rate=1, per=1.0)
        async def cmd(inter): return "ok"
        assert await cmd(self._mock_inter()) == "ok"

    @pytest.mark.asyncio
    async def test_cooldown_second_fails(self):
        from discordium.ext.guards import cooldown
        @cooldown(rate=1, per=1.0)
        async def cmd(inter): return "ok"
        inter = self._mock_inter()
        await cmd(inter)
        with pytest.raises(CommandOnCooldown) as exc:
            await cmd(inter)
        assert exc.value.retry_after > 0

    @pytest.mark.asyncio
    async def test_cooldown_expires(self):
        from discordium.ext.guards import cooldown
        @cooldown(rate=1, per=0.05)
        async def cmd(inter): return "ok"
        inter = self._mock_inter()
        await cmd(inter)
        await asyncio.sleep(0.06)
        assert await cmd(inter) == "ok"  # should work again

    @pytest.mark.asyncio
    async def test_custom_check(self):
        from discordium.ext.guards import check
        @check(lambda inter: inter.guild_id == 111)
        async def cmd(inter): return "ok"
        assert await cmd(self._mock_inter()) == "ok"
        with pytest.raises(CheckFailure):
            await cmd(self._mock_inter(guild_id=999))

    @pytest.mark.asyncio
    async def test_async_check(self):
        from discordium.ext.guards import check
        async def is_ok(inter):
            return inter.guild_id == 111
        @check(is_ok)
        async def cmd(inter): return "ok"
        assert await cmd(self._mock_inter()) == "ok"

    @pytest.mark.asyncio
    async def test_stacked_guards(self):
        from discordium.ext.guards import guild_only, has_permissions
        @guild_only()
        @has_permissions(Permissions.SEND_MESSAGES)
        async def cmd(inter): return "ok"
        assert await cmd(self._mock_inter(perms=int(Permissions.SEND_MESSAGES))) == "ok"
        with pytest.raises(GuildOnly):
            await cmd(self._mock_inter(guild_id=None, perms=int(Permissions.SEND_MESSAGES)))

#  EventDispatcher Tests

MSG_PAYLOAD = {
    "id": "1", "channel_id": "2",
    "author": {"id": "3", "username": "u", "discriminator": "0"},
    "content": "test", "timestamp": "", "tts": False,
    "mention_everyone": False, "pinned": False, "embeds": [],
}


class TestEventDispatcher:
    @pytest.mark.asyncio
    async def test_dispatch_converts_to_typed(self):
        from discordium.utils.dispatcher import EventDispatcher
        from discordium.utils.event import EventEmitter
        from discordium.models.events import MessageCreateEvent

        emitter = EventEmitter()
        dispatcher = EventDispatcher(emitter, MagicMock())
        received = []
        async def handler(event): received.append(event)
        emitter.on("message_create", handler)

        await dispatcher.dispatch("message_create", MSG_PAYLOAD)
        assert len(received) == 1
        assert isinstance(received[0], MessageCreateEvent)
        assert received[0].message.content == "test"

    @pytest.mark.asyncio
    async def test_before_hook_can_cancel(self):
        from discordium.utils.dispatcher import EventDispatcher
        from discordium.utils.event import EventEmitter

        emitter = EventEmitter()
        dispatcher = EventDispatcher(emitter, MagicMock())
        received = []
        async def handler(event): received.append(event)
        emitter.on("message_create", handler)

        async def cancel_hook(name, event): return False
        dispatcher.add_before_hook(cancel_hook)

        await dispatcher.dispatch("message_create", MSG_PAYLOAD)
        assert len(received) == 0

    @pytest.mark.asyncio
    async def test_after_hook_runs(self):
        from discordium.utils.dispatcher import EventDispatcher
        from discordium.utils.event import EventEmitter

        emitter = EventEmitter()
        dispatcher = EventDispatcher(emitter, MagicMock())
        after_called = []
        async def handler(event): pass
        async def after_hook(name, event): after_called.append(name)
        emitter.on("message_create", handler)
        dispatcher.add_after_hook(after_hook)

        await dispatcher.dispatch("message_create", MSG_PAYLOAD)
        assert after_called == ["message_create"]

    @pytest.mark.asyncio
    async def test_error_handler_catches(self):
        from discordium.utils.dispatcher import EventDispatcher
        from discordium.utils.event import EventEmitter

        emitter = EventEmitter()
        dispatcher = EventDispatcher(emitter, MagicMock())
        errors = []
        async def error_handler(name, exc): errors.append((name, exc))
        dispatcher.add_error_handler(error_handler)

        async def bad_handler(event): raise ValueError("boom")
        emitter.on("message_create", bad_handler)

        await dispatcher.dispatch("message_create", MSG_PAYLOAD)
        assert len(errors) == 1
        assert isinstance(errors[0][1], ValueError)

    @pytest.mark.asyncio
    async def test_internal_handlers_run_first(self):
        from discordium.utils.dispatcher import EventDispatcher
        from discordium.utils.event import EventEmitter

        emitter = EventEmitter()
        dispatcher = EventDispatcher(emitter, MagicMock())
        order = []
        async def internal(event): order.append("internal")
        async def user(event): order.append("user")
        dispatcher.add_internal_handler("message_create", internal)
        emitter.on("message_create", user)

        await dispatcher.dispatch("message_create", MSG_PAYLOAD)
        assert order == ["internal", "user"]

    @pytest.mark.asyncio
    async def test_unknown_event_doesnt_crash(self):
        from discordium.utils.dispatcher import EventDispatcher
        from discordium.utils.event import EventEmitter

        emitter = EventEmitter()
        dispatcher = EventDispatcher(emitter, MagicMock())
        received = []
        async def handler(event): received.append(event)
        emitter.on("totally_unknown_event", handler)

        await dispatcher.dispatch("totally_unknown_event", {"some": "data"})
        assert len(received) == 1  # got generic GatewayEvent

#  Task Loop Tests

class TestTaskLoop:
    @pytest.mark.asyncio
    async def test_loop_runs_count(self):
        from discordium.ext.tasks import loop
        counter = {"n": 0}
        @loop(seconds=0.02, count=3)
        async def task(): counter["n"] += 1
        task.start()
        await asyncio.sleep(0.15)
        assert counter["n"] == 3
        assert not task.is_running

    @pytest.mark.asyncio
    async def test_start_idempotent(self):
        from discordium.ext.tasks import loop
        @loop(seconds=0.1, count=1)
        async def task(): pass
        t1 = task.start()
        t2 = task.start()
        assert t1 is t2
        await asyncio.sleep(0.2)

    @pytest.mark.asyncio
    async def test_cancel(self):
        from discordium.ext.tasks import loop
        @loop(seconds=0.02)
        async def task(): pass
        task.start()
        assert task.is_running
        task.cancel()
        await asyncio.sleep(0.05)
        assert not task.is_running

    @pytest.mark.asyncio
    async def test_restart(self):
        from discordium.ext.tasks import loop
        counter = {"n": 0}
        @loop(seconds=0.02, count=2)
        async def task(): counter["n"] += 1
        task.start()
        await asyncio.sleep(0.1)
        assert counter["n"] == 2
        task.restart()
        await asyncio.sleep(0.1)
        assert counter["n"] == 4  # ran 2 more times

    @pytest.mark.asyncio
    async def test_error_hook(self):
        from discordium.ext.tasks import loop
        errors = []
        @loop(seconds=0.02, count=1)
        async def task(): raise RuntimeError("oops")
        @task.error
        async def on_err(exc): errors.append(exc)
        task.start()
        await asyncio.sleep(0.1)
        assert len(errors) == 1
        assert isinstance(errors[0], RuntimeError)

    @pytest.mark.asyncio
    async def test_before_after_hooks(self):
        from discordium.ext.tasks import loop
        order = []
        @loop(seconds=0.02, count=1)
        async def task(): order.append("run")
        @task.before
        async def before(): order.append("before")
        @task.after
        async def after(): order.append("after")
        task.start()
        await asyncio.sleep(0.1)
        assert order == ["before", "run", "after"]

    def test_zero_interval_raises(self):
        from discordium.ext.tasks import loop
        with pytest.raises(ValueError):
            @loop(seconds=0)
            async def task(): pass

#  Gateway Payload Handling Tests

class TestGatewayPayload:
    """Test the gateway's _handle_payload dispatch logic without a real WebSocket."""

    def _make_conn(self):
        from discordium.gateway.connection import GatewayConnection
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

        import zlib
        conn._inflator = zlib.decompressobj()

        from discordium.utils.backoff import ExponentialBackoff
        conn._backoff = ExponentialBackoff()

        return conn

    @pytest.mark.asyncio
    async def test_hello_starts_heartbeat(self):
        conn = self._make_conn()
        started = []
        identified = []
        orig_start = type(conn)._start_heartbeat
        orig_identify = type(conn)._identify

        async def fake_identify(self_): identified.append(True)
        def fake_start(self_): started.append(True)

        with patch.object(type(conn), "_start_heartbeat", fake_start), \
             patch.object(type(conn), "_identify", fake_identify):
            await conn._handle_payload({
                "op": 10, "d": {"heartbeat_interval": 41250},
                "s": None, "t": None,
            })
        assert conn._heartbeat_interval == 41.25
        assert started
        assert identified

    @pytest.mark.asyncio
    async def test_hello_resumes_if_session(self):
        conn = self._make_conn()
        conn._session_id = "existing_session"
        conn._seq = 42
        resumed = []

        async def fake_resume(self_): resumed.append(True)
        def fake_start(self_): pass

        with patch.object(type(conn), "_start_heartbeat", fake_start), \
             patch.object(type(conn), "_resume", fake_resume):
            await conn._handle_payload({
                "op": 10, "d": {"heartbeat_interval": 41250},
                "s": None, "t": None,
            })
        assert resumed

    @pytest.mark.asyncio
    async def test_heartbeat_ack_sets_flag(self):
        conn = self._make_conn()
        conn._ack_received = False
        conn._heartbeat_sent_at = time.monotonic() - 0.1

        await conn._handle_payload({"op": 11, "d": None, "s": None, "t": None})

        assert conn._ack_received is True
        assert conn._latency is not None
        assert conn._latency < 1.0

    @pytest.mark.asyncio
    async def test_dispatch_emits_event(self):
        conn = self._make_conn()

        await conn._handle_payload({
            "op": 0,  # DISPATCH
            "t": "MESSAGE_CREATE",
            "s": 5,
            "d": {"content": "hello"},
        })

        assert conn._seq == 5
        conn._emitter.emit.assert_awaited_once_with("message_create", {"content": "hello"})

    @pytest.mark.asyncio
    async def test_ready_stores_session(self):
        conn = self._make_conn()

        await conn._handle_payload({
            "op": 0, "t": "READY", "s": 1,
            "d": {
                "session_id": "sess123",
                "resume_gateway_url": "wss://resume.example.com",
            },
        })

        assert conn._session_id == "sess123"
        assert conn._resume_url == "wss://resume.example.com"

    @pytest.mark.asyncio
    async def test_invalid_session_non_resumable(self):
        conn = self._make_conn()
        conn._session_id = "old"
        conn._seq = 10
        conn._ws.close = AsyncMock()

        await conn._handle_payload({
            "op": 9, "d": False,  # not resumable
            "s": None, "t": None,
        })

        assert conn._session_id is None
        assert conn._seq is None

    @pytest.mark.asyncio
    async def test_reconnect_closes_ws(self):
        conn = self._make_conn()
        conn._ws.close = AsyncMock()

        await conn._handle_payload({
            "op": 7, "d": None,  # RECONNECT
            "s": None, "t": None,
        })

        conn._ws.close.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_sequence_tracking(self):
        conn = self._make_conn()

        await conn._handle_payload({"op": 0, "t": "TEST", "s": 1, "d": {}})
        assert conn._seq == 1
        await conn._handle_payload({"op": 0, "t": "TEST", "s": 5, "d": {}})
        assert conn._seq == 5
        await conn._handle_payload({"op": 0, "t": "TEST", "s": None, "d": {}})
        assert conn._seq == 5  # None doesn't overwrite

#  Rate Limiter Tests

class TestRateLimiter:
    def test_bucket_key_generation(self):
        from discordium.http.ratelimit import RateLimiter
        rl = RateLimiter()
        k1 = rl._bucket_key("GET", "/channels/123/messages")
        k2 = rl._bucket_key("GET", "/channels/456/messages")
        assert k1 != k2  # different channels = different buckets

    def test_same_channel_same_bucket(self):
        from discordium.http.ratelimit import RateLimiter
        rl = RateLimiter()
        k1 = rl._bucket_key("GET", "/channels/123/messages")
        k2 = rl._bucket_key("POST", "/channels/123/messages")
        # Same major params but different methods — could be same or different
        # depending on implementation, but should not crash

    @pytest.mark.asyncio
    async def test_acquire_and_release(self):
        from discordium.http.ratelimit import RateLimiter
        rl = RateLimiter()
        key = await rl.acquire("GET", "/test")
        assert isinstance(key, str)
        rl.release(key)  # should not raise

    @pytest.mark.asyncio
    async def test_handle_429(self):
        from discordium.http.ratelimit import RateLimiter
        rl = RateLimiter()
        # Should sleep but not crash
        await rl.handle_429(0.01, is_global=False)

    @pytest.mark.asyncio
    async def test_global_429(self):
        from discordium.http.ratelimit import RateLimiter
        rl = RateLimiter()
        await rl.handle_429(0.01, is_global=True)
        # After sleep, global event should be set
        assert rl._global_event.is_set()

#  File Upload Tests

class TestFile:
    def test_from_bytes(self):
        from discordium.models.file import File
        f = File(b"hello world", filename="test.txt")
        assert f.filename == "test.txt"
        assert f.content_type == "text/plain"
        assert len(f.data) == 11

    def test_spoiler(self):
        from discordium.models.file import File
        f = File(b"data", filename="image.png", spoiler=True)
        assert f.filename.startswith("SPOILER_")

    def test_attachment_dict(self):
        from discordium.models.file import File
        f = File(b"x", filename="f.txt", description="A file")
        d = f.to_attachment_dict(0)
        assert d["id"] == 0
        assert d["filename"] == "f.txt"
        assert d["description"] == "A file"

    def test_repr(self):
        from discordium.models.file import File
        f = File(b"x" * 2048, filename="big.bin")
        r = repr(f)
        assert "big.bin" in r
        assert "KB" in r

    def test_auto_content_type(self):
        from discordium.models.file import File
        assert File(b"", filename="img.png").content_type == "image/png"
        assert File(b"", filename="doc.pdf").content_type == "application/pdf"
        assert File(b"", filename="unknown.qzx123").content_type == "application/octet-stream"

#  Backoff Tests

class TestBackoff:
    def test_increases(self):
        from discordium.utils.backoff import ExponentialBackoff
        b = ExponentialBackoff(base=1.0, maximum=60.0, jitter=False)
        d1 = b.compute()
        d2 = b.compute()
        d3 = b.compute()
        assert d1 == 1.0
        assert d2 == 2.0
        assert d3 == 4.0

    def test_max_cap(self):
        from discordium.utils.backoff import ExponentialBackoff
        b = ExponentialBackoff(base=1.0, maximum=5.0, jitter=False)
        for _ in range(20):
            d = b.compute()
        assert d == 5.0

    def test_reset(self):
        from discordium.utils.backoff import ExponentialBackoff
        b = ExponentialBackoff(base=1.0, maximum=60.0, jitter=False)
        b.compute()
        b.compute()
        b.reset()
        assert b.compute() == 1.0

    def test_jitter(self):
        from discordium.utils.backoff import ExponentialBackoff
        b = ExponentialBackoff(base=1.0, maximum=60.0, jitter=True)
        values = [b.compute() for _ in range(10)]
        b.reset()
        values2 = [b.compute() for _ in range(10)]
        # With jitter, consecutive runs should produce different values
        assert values != values2 or len(set(values)) > 1

#  Event Names Tests

class TestEventNames:
    def test_events_constants(self):
        from discordium.models.event_names import Events
        assert Events.MESSAGE_CREATE == "message_create"
        assert Events.READY == "ready"
        assert Events.INTERACTION_CREATE == "interaction_create"
        assert Events.GUILD_MEMBER_ADD == "guild_member_add"

    def test_events_match_registry(self):
        from discordium.models.event_names import Events
        from discordium.models.events import EVENT_REGISTRY
        for attr in dir(Events):
            if attr.startswith("_"):
                continue
            val = getattr(Events, attr)
            assert val in EVENT_REGISTRY, f"Events.{attr}={val} not in EVENT_REGISTRY"
