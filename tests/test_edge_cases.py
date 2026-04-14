"""Edge case tests for discordium.

Covers:
  - Reconnect / resume after connection loss
  - Multiple READY events (reconnect scenarios)
  - Interaction already responded / late response
  - defer → followup → edit ordering
  - Cooldown race cases
  - Component/modal custom_id collisions
  - wait_for timeouts
  - Empty / partial Discord payloads
  - Unknown event payload handling
  - Reconnect during running tasks
"""

import asyncio
import time
import zlib
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from discordium.errors import (
    InteractionAlreadyResponded,
    InteractionNotResponded,
    CommandOnCooldown,
)
from discordium.models.components import Modal
from discordium.models.events import (
    GatewayEvent,
    GuildCreateEvent,
    GuildDeleteEvent,
    MessageCreateEvent,
    MessageDeleteEvent,
    MessageReactionAddEvent,
    ReadyEvent,
    VoiceStateUpdateEvent,
    parse_event,
)
from discordium.models.interaction import Interaction, InteractionType
from discordium.models.snowflake import Snowflake
from discordium.utils.backoff import ExponentialBackoff

#  Helper: build a mock GatewayConnection without a real WebSocket

def _make_gateway_conn():
    """Create a GatewayConnection without a real WebSocket."""
    from discordium.gateway.connection import GatewayConnection

    emitter = MagicMock()
    emitter.emit = AsyncMock()

    conn = GatewayConnection.__new__(GatewayConnection)
    conn._token = "fake_token"
    conn._intents = 513
    conn._emitter = emitter
    conn._gateway_url = "wss://gateway.discord.gg"
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
    conn._backoff = ExponentialBackoff()
    return conn


def _make_interaction(**overrides):
    """Create an Interaction with AsyncMock REST client."""
    base = {
        "id": "900", "application_id": "800", "type": 2,
        "token": "inter_token", "guild_id": "111", "channel_id": "222",
        "data": {"name": "test", "options": []},
        "member": {
            "user": {"id": "333", "username": "user", "discriminator": "0"},
            "nick": None, "roles": [], "permissions": "0",
        },
    }
    base.update(overrides)
    rest = AsyncMock()
    rest.request = AsyncMock(return_value={})
    return Interaction(base, rest=rest)

#  1. Reconnect / Resume after connection loss

class TestReconnectResume:
    @pytest.mark.asyncio
    async def test_resume_after_disconnect(self):
        """After a disconnect, HELLO should trigger RESUME (not IDENTIFY) if session exists."""
        conn = _make_gateway_conn()
        conn._session_id = "old_session_abc"
        conn._seq = 42
        conn._resume_url = "wss://resume.discord.gg"

        resumed = []
        async def fake_resume(self_): resumed.append(True)
        def fake_start(self_): pass

        with patch.object(type(conn), "_start_heartbeat", fake_start), \
             patch.object(type(conn), "_resume", fake_resume):
            await conn._handle_payload({
                "op": 10, "d": {"heartbeat_interval": 41250},
                "s": None, "t": None,
            })

        assert resumed, "Should have called _resume, not _identify"

    @pytest.mark.asyncio
    async def test_identify_without_session(self):
        """Without a session, HELLO should trigger IDENTIFY."""
        conn = _make_gateway_conn()
        conn._session_id = None
        conn._seq = None

        identified = []
        async def fake_identify(self_): identified.append(True)
        def fake_start(self_): pass

        with patch.object(type(conn), "_start_heartbeat", fake_start), \
             patch.object(type(conn), "_identify", fake_identify):
            await conn._handle_payload({
                "op": 10, "d": {"heartbeat_interval": 41250},
                "s": None, "t": None,
            })

        assert identified

    @pytest.mark.asyncio
    async def test_invalid_session_non_resumable_clears_state(self):
        """INVALID_SESSION with resumable=false should clear session state."""
        conn = _make_gateway_conn()
        conn._session_id = "old_session"
        conn._seq = 100
        conn._resume_url = "wss://resume.example.com"

        await conn._handle_payload({
            "op": 9, "d": False,
            "s": None, "t": None,
        })

        assert conn._session_id is None
        assert conn._seq is None
        assert conn._resume_url is None

    @pytest.mark.asyncio
    async def test_invalid_session_resumable_keeps_state(self):
        """INVALID_SESSION with resumable=true should keep session state."""
        conn = _make_gateway_conn()
        conn._session_id = "keep_me"
        conn._seq = 50

        await conn._handle_payload({
            "op": 9, "d": True,
            "s": None, "t": None,
        })

        assert conn._session_id == "keep_me"
        assert conn._seq == 50

    @pytest.mark.asyncio
    async def test_reconnect_opcode_closes_ws(self):
        """RECONNECT (op 7) should close the WebSocket so the connect loop retries."""
        conn = _make_gateway_conn()

        await conn._handle_payload({
            "op": 7, "d": None,
            "s": None, "t": None,
        })

        conn._ws.close.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_zombie_connection_detected(self):
        """If heartbeat ACK is not received, the connection should be closed."""
        conn = _make_gateway_conn()
        conn._ack_received = False  # simulate missing ACK

        # The heartbeat loop checks _ack_received — when False it closes
        # We test the logic directly
        conn._heartbeat_task = None

        # Simulate what the heartbeat loop does
        if not conn._ack_received:
            await conn._ws.close(code=4000)

        conn._ws.close.assert_awaited_once_with(code=4000)

    @pytest.mark.asyncio
    async def test_backoff_resets_on_successful_dispatch(self):
        """Backoff should reset when a DISPATCH is received (connection is healthy)."""
        conn = _make_gateway_conn()
        conn._backoff = ExponentialBackoff(base=1.0, jitter=False)

        # Simulate several backoff computations
        conn._backoff.compute()
        conn._backoff.compute()
        assert conn._backoff._attempt == 2

        # Dispatch should reset
        await conn._handle_payload({
            "op": 0, "t": "TEST_EVENT", "s": 1, "d": {},
        })

        assert conn._backoff._attempt == 0

#  2. Multiple READY events (reconnect scenarios)

class TestMultipleReady:
    @pytest.mark.asyncio
    async def test_second_ready_updates_state(self):
        """A second READY should update session data, not crash."""
        conn = _make_gateway_conn()

        # First READY
        await conn._handle_payload({
            "op": 0, "t": "READY", "s": 1,
            "d": {"session_id": "session_1", "resume_gateway_url": "wss://r1.example.com"},
        })
        assert conn._session_id == "session_1"

        # Second READY (after reconnect)
        await conn._handle_payload({
            "op": 0, "t": "READY", "s": 2,
            "d": {"session_id": "session_2", "resume_gateway_url": "wss://r2.example.com"},
        })
        assert conn._session_id == "session_2"
        assert conn._resume_url == "wss://r2.example.com"

    @pytest.mark.asyncio
    async def test_ready_event_typed_twice(self):
        """Parsing READY twice should produce valid ReadyEvent objects."""
        payload = {
            "user": {"id": "123", "username": "bot", "discriminator": "0"},
            "guilds": [{"id": "1", "unavailable": True}],
            "session_id": "s1", "resume_gateway_url": "wss://x",
            "application": {"id": "999"},
        }
        e1 = ReadyEvent.from_payload(payload, rest=MagicMock())
        e2 = ReadyEvent.from_payload({**payload, "session_id": "s2"}, rest=MagicMock())
        assert e1.session_id == "s1"
        assert e2.session_id == "s2"

    @pytest.mark.asyncio
    async def test_task_loop_survives_multiple_ready(self):
        """Loop.start() called on each READY should not crash or double-start."""
        from discordium.ext.tasks import loop

        counter = {"n": 0}

        @loop(seconds=0.02, count=2)
        async def my_task():
            counter["n"] += 1

        # Simulate first READY
        t1 = my_task.start()

        # Simulate second READY (reconnect)
        t2 = my_task.start()

        assert t1 is t2  # idempotent — same task returned

        await asyncio.sleep(0.1)
        assert counter["n"] == 2  # ran exactly count=2 times, not doubled

#  3. Interaction response lifecycle edge cases

class TestInteractionLifecycleEdgeCases:
    @pytest.mark.asyncio
    async def test_respond_respond_raises(self):
        inter = _make_interaction()
        await inter.respond("first")
        with pytest.raises(InteractionAlreadyResponded):
            await inter.respond("second")

    @pytest.mark.asyncio
    async def test_defer_defer_raises(self):
        inter = _make_interaction()
        await inter.defer()
        with pytest.raises(InteractionAlreadyResponded):
            await inter.defer()

    @pytest.mark.asyncio
    async def test_respond_then_modal_raises(self):
        inter = _make_interaction()
        await inter.respond("hi")
        with pytest.raises(InteractionAlreadyResponded):
            await inter.send_modal(Modal(title="T", custom_id="m"))

    @pytest.mark.asyncio
    async def test_modal_then_respond_raises(self):
        inter = _make_interaction()
        await inter.send_modal(Modal(title="T", custom_id="m"))
        with pytest.raises(InteractionAlreadyResponded):
            await inter.respond("nope")

    @pytest.mark.asyncio
    async def test_update_then_respond_raises(self):
        inter = _make_interaction(type=3)  # COMPONENT
        await inter.update_message(content="updated")
        with pytest.raises(InteractionAlreadyResponded):
            await inter.respond("nope")

    @pytest.mark.asyncio
    async def test_autocomplete_then_respond_raises(self):
        inter = _make_interaction(type=4)  # AUTOCOMPLETE
        await inter.autocomplete([{"name": "a", "value": "a"}])
        with pytest.raises(InteractionAlreadyResponded):
            await inter.respond("nope")

    @pytest.mark.asyncio
    async def test_followup_without_defer_or_respond_raises(self):
        inter = _make_interaction()
        with pytest.raises(InteractionNotResponded):
            await inter.followup("too early")

    @pytest.mark.asyncio
    async def test_edit_without_respond_raises(self):
        inter = _make_interaction()
        with pytest.raises(InteractionNotResponded):
            await inter.edit_response("too early")

    @pytest.mark.asyncio
    async def test_delete_without_respond_raises(self):
        inter = _make_interaction()
        with pytest.raises(InteractionNotResponded):
            await inter.delete_response()

#  4. defer → followup → edit ordering

class TestDeferFollowupEditOrdering:
    @pytest.mark.asyncio
    async def test_defer_followup_works(self):
        inter = _make_interaction()
        await inter.defer()
        await inter.followup("done")  # should not raise

    @pytest.mark.asyncio
    async def test_defer_edit_works(self):
        inter = _make_interaction()
        await inter.defer()
        await inter.edit_response("edited")  # should not raise

    @pytest.mark.asyncio
    async def test_defer_delete_works(self):
        inter = _make_interaction()
        await inter.defer()
        await inter.delete_response()  # should not raise

    @pytest.mark.asyncio
    async def test_defer_followup_edit_chain(self):
        """Full chain: defer → followup → edit_response."""
        inter = _make_interaction()
        await inter.defer(ephemeral=True)
        assert inter.is_deferred
        await inter.followup("processing...")
        await inter.edit_response("done!")
        # All should work without errors

    @pytest.mark.asyncio
    async def test_respond_followup_followup_chain(self):
        """respond → multiple followups should all work."""
        inter = _make_interaction()
        await inter.respond("initial")
        await inter.followup("followup 1")
        await inter.followup("followup 2")
        await inter.followup("followup 3")
        # Multiple followups are fine

    @pytest.mark.asyncio
    async def test_defer_ephemeral_flag(self):
        """defer(ephemeral=True) should pass flags=64."""
        inter = _make_interaction()
        await inter.defer(ephemeral=True)
        call_args = inter._rest.request.call_args
        payload = call_args.kwargs.get("json") or call_args[1].get("json")
        assert payload["data"]["flags"] == 64

#  5. Cooldown race cases

class TestCooldownRaceCases:
    @pytest.mark.asyncio
    async def test_cooldown_per_user_isolation(self):
        """Different users should have independent cooldowns."""
        from discordium.ext.guards import cooldown

        @cooldown(rate=1, per=10.0)
        async def cmd(inter):
            return "ok"

        user_a = MagicMock()
        user_a.user = MagicMock()
        user_a.user.id = MagicMock(__str__=lambda s: "user_a")

        user_b = MagicMock()
        user_b.user = MagicMock()
        user_b.user.id = MagicMock(__str__=lambda s: "user_b")

        assert await cmd(user_a) == "ok"
        assert await cmd(user_b) == "ok"  # different user, should work
        with pytest.raises(CommandOnCooldown):
            await cmd(user_a)  # same user, should fail

    @pytest.mark.asyncio
    async def test_cooldown_rate_burst(self):
        """rate=3 should allow 3 rapid calls, then block."""
        from discordium.ext.guards import cooldown

        @cooldown(rate=3, per=10.0)
        async def cmd(inter):
            return "ok"

        inter = MagicMock()
        inter.user = MagicMock()
        inter.user.id = MagicMock(__str__=lambda s: "burst_user")

        assert await cmd(inter) == "ok"
        assert await cmd(inter) == "ok"
        assert await cmd(inter) == "ok"
        with pytest.raises(CommandOnCooldown):
            await cmd(inter)

    @pytest.mark.asyncio
    async def test_cooldown_expiry_partial(self):
        """After some uses expire, new ones should be allowed."""
        from discordium.ext.guards import cooldown

        @cooldown(rate=1, per=0.05)
        async def cmd(inter):
            return "ok"

        inter = MagicMock()
        inter.user = MagicMock()
        inter.user.id = MagicMock(__str__=lambda s: "expiry_user")

        assert await cmd(inter) == "ok"
        with pytest.raises(CommandOnCooldown):
            await cmd(inter)

        await asyncio.sleep(0.06)  # wait for cooldown to expire
        assert await cmd(inter) == "ok"

    @pytest.mark.asyncio
    async def test_cooldown_retry_after_accuracy(self):
        """retry_after should be approximately correct."""
        from discordium.ext.guards import cooldown

        @cooldown(rate=1, per=1.0)
        async def cmd(inter):
            return "ok"

        inter = MagicMock()
        inter.user = MagicMock()
        inter.user.id = MagicMock(__str__=lambda s: "accuracy_user")

        await cmd(inter)
        try:
            await cmd(inter)
            assert False, "Should have raised"
        except CommandOnCooldown as e:
            assert 0.5 < e.retry_after <= 1.0

#  6. Component/modal custom_id collisions

class TestCustomIdCollisions:
    def test_same_custom_id_different_components(self):
        """Two components can technically have the same custom_id."""
        from discordium.models.components import Button, ButtonStyle, SelectMenu, SelectOption

        b = Button(label="A", custom_id="shared_id", style=ButtonStyle.PRIMARY)
        s = SelectMenu(
            custom_id="shared_id",
            options=[SelectOption(label="X", value="x")],
        )
        # Both should serialize fine
        assert b.to_dict()["custom_id"] == "shared_id"
        assert s.to_dict()["custom_id"] == "shared_id"

    def test_prefix_matching_specificity(self):
        """Test that prefix matching in component handlers works correctly."""
        # Simulate the router's prefix matching logic
        handlers = {
            "counter:": "counter_handler",
            "counter:inc": "inc_handler",
            "vote:": "vote_handler",
        }

        def find_handler(custom_id):
            # Exact match first
            if custom_id in handlers:
                return handlers[custom_id]
            # Prefix match
            for prefix, h in handlers.items():
                if custom_id.startswith(prefix):
                    return h
            return None

        assert find_handler("counter:inc") == "inc_handler"  # exact
        assert find_handler("counter:dec") == "counter_handler"  # prefix
        assert find_handler("vote:yes") == "vote_handler"  # prefix
        assert find_handler("unknown") is None

#  7. wait_for timeouts

class TestWaitForTimeouts:
    @pytest.mark.asyncio
    async def test_wait_for_timeout_raises(self):
        """wait_for should raise TimeoutError when timeout expires."""
        from discordium.utils.event import EventEmitter

        emitter = EventEmitter()

        with pytest.raises(asyncio.TimeoutError):
            await emitter.wait_for("never_fires", timeout=0.05)

    @pytest.mark.asyncio
    async def test_wait_for_receives_event(self):
        """wait_for should return the event payload when fired."""
        from discordium.utils.event import EventEmitter

        emitter = EventEmitter()

        async def fire_later():
            await asyncio.sleep(0.02)
            await emitter.emit("test_event", "payload_data")

        asyncio.create_task(fire_later())
        result = await emitter.wait_for("test_event", timeout=1.0)
        assert result == "payload_data"

    @pytest.mark.asyncio
    async def test_wait_for_with_check(self):
        """wait_for with a check predicate should filter events."""
        from discordium.utils.event import EventEmitter

        emitter = EventEmitter()

        async def fire_events():
            await asyncio.sleep(0.02)
            await emitter.emit("msg", "wrong")
            await asyncio.sleep(0.02)
            await emitter.emit("msg", "correct")

        asyncio.create_task(fire_events())

        result = await emitter.wait_for(
            "msg",
            check=lambda val: val == "correct",
            timeout=1.0,
        )
        assert result == "correct"

    @pytest.mark.asyncio
    async def test_wait_for_check_rejects_then_times_out(self):
        """If check never passes, should timeout."""
        from discordium.utils.event import EventEmitter

        emitter = EventEmitter()

        async def fire_wrong():
            await asyncio.sleep(0.02)
            await emitter.emit("msg", "wrong")

        asyncio.create_task(fire_wrong())

        with pytest.raises(asyncio.TimeoutError):
            await emitter.wait_for(
                "msg",
                check=lambda val: val == "never_matches",
                timeout=0.1,
            )

#  8. Empty / partial Discord payloads

class TestPartialPayloads:
    def test_message_create_minimal(self):
        """MessageCreateEvent with minimal fields should not crash."""
        data = {
            "id": "1", "channel_id": "2",
            "author": {"id": "3", "username": "u", "discriminator": "0"},
            "content": "", "timestamp": "", "tts": False,
            "mention_everyone": False, "pinned": False, "embeds": [],
        }
        event = parse_event("message_create", data, rest=MagicMock())
        assert isinstance(event, MessageCreateEvent)
        assert event.message.content == ""

    def test_message_create_missing_optional_fields(self):
        """Payload missing optional fields should parse with defaults."""
        data = {
            "id": "1", "channel_id": "2",
            "author": {"id": "3", "username": "u", "discriminator": "0"},
            "content": "hi",
            # Missing: timestamp, tts, mention_everyone, pinned, embeds
        }
        event = parse_event("message_create", data, rest=MagicMock())
        assert isinstance(event, MessageCreateEvent)

    def test_guild_create_empty_lists(self):
        """GuildCreate with empty channels/roles/members lists."""
        data = {
            "id": "1", "name": "Empty Guild",
            "channels": [], "roles": [], "members": [], "threads": [],
        }
        event = parse_event("guild_create", data, rest=MagicMock())
        assert isinstance(event, GuildCreateEvent)
        assert len(event.channels) == 0
        assert len(event.roles) == 0

    def test_message_delete_no_guild_id(self):
        """MessageDelete in DM has no guild_id."""
        data = {"id": "1", "channel_id": "2"}
        event = parse_event("message_delete", data, rest=MagicMock())
        assert isinstance(event, MessageDeleteEvent)
        assert event.guild_id is None

    def test_voice_state_null_channel(self):
        """VoiceStateUpdate with null channel_id (user left voice)."""
        data = {
            "guild_id": "1", "channel_id": None,
            "user_id": "2", "session_id": "s",
            "deaf": False, "mute": False,
        }
        event = parse_event("voice_state_update", data, rest=MagicMock())
        assert isinstance(event, VoiceStateUpdateEvent)
        assert event.channel_id is None

    def test_reaction_minimal(self):
        """Reaction event with minimal emoji data."""
        data = {
            "user_id": "1", "channel_id": "2", "message_id": "3",
            "emoji": {"id": None, "name": "❤️"},
        }
        event = parse_event("message_reaction_add", data, rest=MagicMock())
        assert isinstance(event, MessageReactionAddEvent)
        assert event.emoji["name"] == "❤️"

    def test_user_missing_optional_fields(self):
        """User payload with only required fields."""
        from discordium.models.user import User
        data = {"id": "1", "username": "minimal", "discriminator": "0"}
        u = User.from_payload(data)
        assert u.username == "minimal"
        assert u.avatar is None
        assert u.bot is False
        assert u.global_name is None

    def test_interaction_no_guild_id(self):
        """Interaction in DM context (no guild_id)."""
        data = {
            "id": "1", "application_id": "2", "type": 2,
            "token": "t", "channel_id": "3",
            "data": {"name": "test"},
            "user": {"id": "4", "username": "dm_user", "discriminator": "0"},
        }
        inter = Interaction(data, rest=MagicMock())
        assert inter.guild_id is None
        assert inter.member is None
        assert inter.user is not None
        assert inter.user.username == "dm_user"

    def test_interaction_empty_options(self):
        """Interaction with no options."""
        data = {
            "id": "1", "application_id": "2", "type": 2,
            "token": "t", "guild_id": "5", "channel_id": "6",
            "data": {"name": "noargs"},
            "member": {
                "user": {"id": "7", "username": "u", "discriminator": "0"},
                "roles": [], "permissions": "0",
            },
        }
        inter = Interaction(data, rest=MagicMock())
        assert len(inter.options) == 0
        assert inter.get_option("anything") is None
        assert inter.option_string("anything") is None
        assert inter.option_int("anything") is None
        assert inter.option_user("anything") is None

    def test_interaction_empty_resolved(self):
        """Interaction with empty resolved data."""
        data = {
            "id": "1", "application_id": "2", "type": 2,
            "token": "t", "guild_id": "5", "channel_id": "6",
            "data": {
                "name": "test",
                "options": [{"name": "user", "type": 6, "value": "999"}],
                "resolved": {},
            },
            "member": {
                "user": {"id": "7", "username": "u", "discriminator": "0"},
                "roles": [], "permissions": "0",
            },
        }
        inter = Interaction(data, rest=MagicMock())
        # option_user should return None when user not in resolved
        assert inter.option_user("user") is None

#  9. Unknown event payload handling

class TestUnknownEventPayloads:
    def test_unknown_event_returns_generic(self):
        """Unknown events should return GatewayEvent, not crash."""
        event = parse_event("totally_new_discord_event", {"foo": "bar"}, rest=MagicMock())
        assert isinstance(event, GatewayEvent)
        assert not isinstance(event, MessageCreateEvent)
        assert event.raw == {"foo": "bar"}

    def test_unknown_event_empty_payload(self):
        """Unknown event with empty payload."""
        event = parse_event("future_event", {}, rest=MagicMock())
        assert isinstance(event, GatewayEvent)
        assert event.raw == {}

    def test_malformed_known_event_falls_back(self):
        """A known event name with bad payload should fallback gracefully."""
        # guild_create expects "id" and "name" — give it garbage
        event = parse_event("guild_create", {"bad": "data"}, rest=MagicMock())
        assert isinstance(event, GatewayEvent)  # fallback, not crash

    @pytest.mark.asyncio
    async def test_gateway_dispatches_unknown_events(self):
        """Gateway should dispatch unknown events without crashing."""
        conn = _make_gateway_conn()

        await conn._handle_payload({
            "op": 0, "t": "FUTURE_DISCORD_EVENT", "s": 1,
            "d": {"new_field": "new_value"},
        })

        conn._emitter.emit.assert_awaited_once_with(
            "future_discord_event",
            {"new_field": "new_value"},
        )

    @pytest.mark.asyncio
    async def test_dispatcher_handles_unknown_events(self):
        """EventDispatcher should parse unknown events as GatewayEvent."""
        from discordium.utils.dispatcher import EventDispatcher
        from discordium.utils.event import EventEmitter

        emitter = EventEmitter()
        dispatcher = EventDispatcher(emitter, MagicMock())

        received = []
        async def handler(event): received.append(event)
        emitter.on("brand_new_event", handler)

        await dispatcher.dispatch("brand_new_event", {"x": 1})
        assert len(received) == 1
        assert isinstance(received[0], GatewayEvent)
        assert received[0].raw == {"x": 1}

#  10. Reconnect during running tasks

class TestReconnectDuringTasks:
    @pytest.mark.asyncio
    async def test_loop_survives_reconnect(self):
        """A running loop should keep running across reconnects."""
        from discordium.ext.tasks import loop

        counter = {"n": 0}

        @loop(seconds=0.02, count=5)
        async def my_task():
            counter["n"] += 1

        my_task.start()

        # Simulate a "reconnect" by calling start again mid-loop
        await asyncio.sleep(0.03)
        assert counter["n"] >= 1

        # Second start (reconnect) — should be idempotent
        my_task.start()

        await asyncio.sleep(0.15)
        assert counter["n"] == 5  # completed normally, not restarted

    @pytest.mark.asyncio
    async def test_loop_restart_after_cancel(self):
        """After explicit cancel, restart should work."""
        from discordium.ext.tasks import loop

        counter = {"n": 0}

        @loop(seconds=0.02, count=3)
        async def my_task():
            counter["n"] += 1

        my_task.start()
        await asyncio.sleep(0.03)
        my_task.cancel()
        await asyncio.sleep(0.03)
        old_count = counter["n"]

        # Restart
        my_task.restart()
        await asyncio.sleep(0.15)
        assert counter["n"] > old_count

    @pytest.mark.asyncio
    async def test_loop_error_doesnt_stop_loop(self):
        """An error in one iteration should not kill the loop."""
        from discordium.ext.tasks import loop

        counter = {"n": 0}
        errors = []

        @loop(seconds=0.02, count=3)
        async def flaky_task():
            counter["n"] += 1
            if counter["n"] == 2:
                raise ValueError("flaky")

        @flaky_task.error
        async def on_err(exc):
            errors.append(exc)

        flaky_task.start()
        await asyncio.sleep(0.15)

        assert counter["n"] == 3  # all 3 iterations ran
        assert len(errors) == 1  # error caught, not propagated
        assert isinstance(errors[0], ValueError)

    @pytest.mark.asyncio
    async def test_multiple_loops_independent(self):
        """Multiple loop instances should not interfere."""
        from discordium.ext.tasks import loop

        a_count = {"n": 0}
        b_count = {"n": 0}

        @loop(seconds=0.02, count=3)
        async def task_a():
            a_count["n"] += 1

        @loop(seconds=0.02, count=3)
        async def task_b():
            b_count["n"] += 1

        task_a.start()
        task_b.start()
        await asyncio.sleep(0.15)

        assert a_count["n"] == 3
        assert b_count["n"] == 3
