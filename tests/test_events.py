"""Tests for typed event parsing."""

from unittest.mock import MagicMock

from discordium.models.events import (
    EVENT_REGISTRY,
    ChannelCreateEvent,
    GatewayEvent,
    GuildBanAddEvent,
    GuildCreateEvent,
    GuildDeleteEvent,
    GuildMemberAddEvent,
    GuildMemberRemoveEvent,
    GuildRoleCreateEvent,
    MessageCreateEvent,
    MessageDeleteEvent,
    MessageReactionAddEvent,
    ReadyEvent,
    ResumedEvent,
    ThreadCreateEvent,
    TypingStartEvent,
    VoiceStateUpdateEvent,
    parse_event,
)
from discordium.models.snowflake import Snowflake


def _mock_rest():
    return MagicMock()


class TestEventRegistry:
    def test_all_events_have_classes(self):
        assert len(EVENT_REGISTRY) >= 25

    def test_all_classes_have_from_payload(self):
        for name, cls in EVENT_REGISTRY.items():
            assert hasattr(cls, "from_payload"), f"{name} missing from_payload"


class TestParseEvent:
    def test_unknown_event_returns_generic(self):
        event = parse_event("unknown_event_xyz", {"foo": "bar"}, rest=_mock_rest())
        assert isinstance(event, GatewayEvent)
        assert event.raw == {"foo": "bar"}

    def test_malformed_payload_returns_generic(self):
        # MessageCreateEvent expects "id", "channel_id" etc — this should not crash
        event = parse_event("message_create", {"bad": "data"}, rest=_mock_rest())
        assert isinstance(event, GatewayEvent)


class TestReadyEvent:
    PAYLOAD = {
        "user": {"id": "123", "username": "bot", "discriminator": "0"},
        "guilds": [{"id": "111", "unavailable": True}],
        "session_id": "abc123",
        "resume_gateway_url": "wss://gateway.discord.gg",
        "application": {"id": "999"},
    }

    def test_parse(self):
        event = ReadyEvent.from_payload(self.PAYLOAD, rest=_mock_rest())
        assert event.user.username == "bot"
        assert int(event.user.id) == 123
        assert len(event.guilds) == 1
        assert event.session_id == "abc123"
        assert int(event.application_id) == 999

    def test_via_parse_event(self):
        event = parse_event("ready", self.PAYLOAD, rest=_mock_rest())
        assert isinstance(event, ReadyEvent)


class TestMessageCreateEvent:
    PAYLOAD = {
        "id": "555",
        "channel_id": "777",
        "guild_id": "111",
        "author": {"id": "123", "username": "user", "discriminator": "0"},
        "content": "Hello World",
        "timestamp": "2024-01-01T00:00:00Z",
        "tts": False,
        "mention_everyone": False,
        "pinned": False,
        "embeds": [],
    }

    def test_parse(self):
        event = MessageCreateEvent.from_payload(self.PAYLOAD, rest=_mock_rest())
        assert event.message.content == "Hello World"
        assert int(event.message.id) == 555
        assert event.message.author.username == "user"

    def test_via_parse_event(self):
        event = parse_event("message_create", self.PAYLOAD, rest=_mock_rest())
        assert isinstance(event, MessageCreateEvent)


class TestMessageDeleteEvent:
    def test_parse(self):
        data = {"id": "555", "channel_id": "777", "guild_id": "111"}
        event = MessageDeleteEvent.from_payload(data, rest=_mock_rest())
        assert int(event.message_id) == 555
        assert int(event.channel_id) == 777
        assert int(event.guild_id) == 111


class TestGuildCreateEvent:
    def test_parse(self):
        data = {
            "id": "111",
            "name": "Test Guild",
            "channels": [{"id": "777", "type": 0}],
            "roles": [{"id": "555", "name": "everyone", "permissions": "0"}],
            "members": [],
            "threads": [],
            "member_count": 10,
        }
        event = GuildCreateEvent.from_payload(data, rest=_mock_rest())
        assert event.guild.name == "Test Guild"
        assert len(event.channels) == 1
        assert len(event.roles) == 1
        assert event.member_count == 10


class TestGuildDeleteEvent:
    def test_parse(self):
        data = {"id": "111", "unavailable": True}
        event = GuildDeleteEvent.from_payload(data, rest=_mock_rest())
        assert int(event.guild_id) == 111
        assert event.unavailable is True


class TestGuildMemberAddEvent:
    def test_parse(self):
        data = {
            "guild_id": "111",
            "user": {"id": "123", "username": "new", "discriminator": "0"},
            "roles": [],
            "joined_at": "2024-06-01T00:00:00Z",
        }
        event = GuildMemberAddEvent.from_payload(data, rest=_mock_rest())
        assert int(event.guild_id) == 111
        assert event.member.user.username == "new"


class TestGuildMemberRemoveEvent:
    def test_parse(self):
        data = {
            "guild_id": "111",
            "user": {"id": "123", "username": "left", "discriminator": "0"},
        }
        event = GuildMemberRemoveEvent.from_payload(data, rest=_mock_rest())
        assert event.user.username == "left"


class TestGuildBanAddEvent:
    def test_parse(self):
        data = {
            "guild_id": "111",
            "user": {"id": "123", "username": "banned", "discriminator": "0"},
        }
        event = GuildBanAddEvent.from_payload(data, rest=_mock_rest())
        assert event.user.username == "banned"


class TestGuildRoleCreateEvent:
    def test_parse(self):
        data = {
            "guild_id": "111",
            "role": {"id": "555", "name": "NewRole", "permissions": "0"},
        }
        event = GuildRoleCreateEvent.from_payload(data, rest=_mock_rest())
        assert event.role.name == "NewRole"


class TestReactionEvent:
    def test_parse(self):
        data = {
            "user_id": "123",
            "channel_id": "777",
            "message_id": "555",
            "guild_id": "111",
            "emoji": {"id": None, "name": "👍"},
        }
        event = MessageReactionAddEvent.from_payload(data, rest=_mock_rest())
        assert int(event.user_id) == 123
        assert event.emoji["name"] == "👍"


class TestTypingStartEvent:
    def test_parse(self):
        data = {
            "channel_id": "777",
            "user_id": "123",
            "timestamp": 1234567890,
        }
        event = TypingStartEvent.from_payload(data, rest=_mock_rest())
        assert int(event.user_id) == 123


class TestVoiceStateUpdateEvent:
    def test_parse(self):
        data = {
            "guild_id": "111",
            "channel_id": "888",
            "user_id": "123",
            "session_id": "sess",
            "deaf": False,
            "mute": True,
            "self_deaf": False,
            "self_mute": True,
        }
        event = VoiceStateUpdateEvent.from_payload(data, rest=_mock_rest())
        assert event.mute is True
        assert event.self_mute is True
