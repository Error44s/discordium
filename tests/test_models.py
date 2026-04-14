"""Comprehensive tests for all discordium data models.

Tests are written against the actual model API surface — every property
and method that exists is tested.
"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from discordium.models.snowflake import Snowflake
from discordium.models.intents import Intents
from discordium.models.permissions import Permissions, PermissionOverwrite
from discordium.models.enums import ChannelType

#  Snowflake

class TestSnowflake:
    def test_int_conversion(self):
        assert int(Snowflake(175928847299117063)) == 175928847299117063

    def test_str_conversion(self):
        assert int(Snowflake("175928847299117063")) == 175928847299117063

    def test_created_at(self):
        s = Snowflake(175928847299117063)
        assert isinstance(s.created_at, datetime)
        assert s.created_at.tzinfo == timezone.utc

    def test_equality(self):
        assert Snowflake(123) == Snowflake(123)
        assert Snowflake(123) == 123
        assert Snowflake(123) != Snowflake(456)

    def test_hashable(self):
        assert {Snowflake(123): "v"}[Snowflake(123)] == "v"

    def test_ordering(self):
        assert Snowflake(100) < Snowflake(200)

    def test_from_datetime(self):
        dt = datetime(2024, 1, 1, tzinfo=timezone.utc)
        s = Snowflake.from_datetime(dt)
        assert abs((s.created_at - dt).total_seconds()) < 1

    def test_worker_process_increment(self):
        s = Snowflake(175928847299117063)
        assert isinstance(s.worker_id, int)
        assert isinstance(s.process_id, int)
        assert isinstance(s.increment, int)

    def test_repr(self):
        assert repr(Snowflake(123)) == "Snowflake(123)"

#  User

class TestUser:
    PAYLOAD = {
        "id": "123456789", "username": "testuser", "discriminator": "0",
        "global_name": "Test User", "avatar": "abc123", "bot": False,
        "banner": "banner_hash", "accent_color": 0x5865F2,
        "public_flags": 256,
    }

    def test_from_payload(self):
        from discordium.models.user import User
        u = User.from_payload(self.PAYLOAD)
        assert int(u.id) == 123456789
        assert u.username == "testuser"
        assert u.bot is False

    def test_display_name_global(self):
        from discordium.models.user import User
        u = User.from_payload(self.PAYLOAD)
        assert u.display_name == "Test User"

    def test_display_name_fallback(self):
        from discordium.models.user import User
        u = User.from_payload({**self.PAYLOAD, "global_name": None})
        assert u.display_name == "testuser"

    def test_tag_migrated(self):
        from discordium.models.user import User
        u = User.from_payload(self.PAYLOAD)
        # Migrated users (discriminator "0") — tag is just username
        assert "testuser" in u.tag

    def test_tag_legacy(self):
        from discordium.models.user import User
        u = User.from_payload({**self.PAYLOAD, "discriminator": "1234"})
        assert u.tag == "testuser#1234"

    def test_mention(self):
        from discordium.models.user import User
        assert User.from_payload(self.PAYLOAD).mention == "<@123456789>"

    def test_avatar_url_png(self):
        from discordium.models.user import User
        u = User.from_payload(self.PAYLOAD)
        assert u.avatar_url is not None
        assert "abc123" in u.avatar_url
        assert ".png" in u.avatar_url

    def test_avatar_url_animated(self):
        from discordium.models.user import User
        u = User.from_payload({**self.PAYLOAD, "avatar": "a_animated"})
        assert ".gif" in u.avatar_url

    def test_avatar_url_none(self):
        from discordium.models.user import User
        u = User.from_payload({**self.PAYLOAD, "avatar": None})
        assert u.avatar_url is None

    def test_default_avatar_url(self):
        from discordium.models.user import User
        u = User.from_payload(self.PAYLOAD)
        assert u.default_avatar_url is not None
        assert "embed/avatars" in u.default_avatar_url

    def test_banner_url(self):
        from discordium.models.user import User
        u = User.from_payload(self.PAYLOAD)
        assert u.banner_url is not None
        assert "banner_hash" in u.banner_url

    def test_accent_color_hex(self):
        from discordium.models.user import User
        u = User.from_payload(self.PAYLOAD)
        assert u.accent_color_hex == "#5865f2"

    def test_is_migrated(self):
        from discordium.models.user import User
        assert User.from_payload(self.PAYLOAD).is_migrated is True
        assert User.from_payload({**self.PAYLOAD, "discriminator": "1234"}).is_migrated is False

    def test_created_at(self):
        from discordium.models.user import User
        u = User.from_payload(self.PAYLOAD)
        assert isinstance(u.created_at, datetime)

    def test_flags_property(self):
        from discordium.models.user import User
        u = User.from_payload(self.PAYLOAD)
        # flags should be accessible
        assert isinstance(u.flags, int) or hasattr(u.flags, '__int__')

    def test_has_nitro(self):
        from discordium.models.user import User
        u = User.from_payload({**self.PAYLOAD, "premium_type": 2})
        assert u.has_nitro is True
        u2 = User.from_payload(self.PAYLOAD)
        assert u2.has_nitro is False

    def test_minimal_payload(self):
        from discordium.models.user import User
        u = User.from_payload({"id": "1", "username": "x", "discriminator": "0"})
        assert u.username == "x"
        assert u.avatar is None
        assert u.bot is False

#  Guild

class TestGuild:
    PAYLOAD = {
        "id": "111", "name": "Test Guild", "icon": "icon_hash",
        "owner_id": "222", "member_count": 1234, "premium_tier": 2,
        "premium_subscription_count": 14, "features": ["COMMUNITY", "VERIFIED"],
        "vanity_url_code": "test-guild", "banner": "banner_hash",
        "description": "A test guild", "verification_level": 2,
    }

    def test_from_payload(self):
        from discordium.models.guild import Guild
        g = Guild.from_payload(self.PAYLOAD)
        assert g.name == "Test Guild"
        assert g.member_count == 1234
        assert g.premium_tier == 2

    def test_icon_url(self):
        from discordium.models.guild import Guild
        g = Guild.from_payload(self.PAYLOAD)
        assert g.icon_url is not None
        assert "icon_hash" in g.icon_url

    def test_no_icon(self):
        from discordium.models.guild import Guild
        g = Guild.from_payload({**self.PAYLOAD, "icon": None})
        assert g.icon_url is None

    def test_boost_level(self):
        from discordium.models.guild import Guild
        g = Guild.from_payload(self.PAYLOAD)
        assert g.boost_level == 2

    def test_is_community(self):
        from discordium.models.guild import Guild
        g = Guild.from_payload(self.PAYLOAD)
        assert g.is_community is True

    def test_is_verified(self):
        from discordium.models.guild import Guild
        g = Guild.from_payload(self.PAYLOAD)
        assert g.is_verified is True

    def test_is_partnered_false(self):
        from discordium.models.guild import Guild
        g = Guild.from_payload(self.PAYLOAD)
        assert g.is_partnered is False

    def test_has_vanity_url(self):
        from discordium.models.guild import Guild
        g = Guild.from_payload(self.PAYLOAD)
        assert g.has_vanity_url is True

    def test_vanity_url(self):
        from discordium.models.guild import Guild
        g = Guild.from_payload(self.PAYLOAD)
        assert g.vanity_url is not None
        assert "test-guild" in g.vanity_url

    def test_created_at(self):
        from discordium.models.guild import Guild
        g = Guild.from_payload(self.PAYLOAD)
        assert isinstance(g.created_at, datetime)

    def test_minimal_payload(self):
        from discordium.models.guild import Guild
        g = Guild.from_payload({"id": "1", "name": "Mini"})
        assert g.name == "Mini"
        assert g.premium_tier == 0

#  Channel

class TestChannel:
    def test_text_channel(self):
        from discordium.models.channel import Channel
        c = Channel.from_payload({"id": "1", "type": 0, "name": "general", "guild_id": "10"})
        assert c.is_text is True
        assert c.is_voice is False
        assert c.is_dm is False

    def test_voice_channel(self):
        from discordium.models.channel import Channel
        c = Channel.from_payload({"id": "1", "type": 2})
        assert c.is_voice is True
        assert c.is_text is False

    def test_category(self):
        from discordium.models.channel import Channel
        c = Channel.from_payload({"id": "1", "type": 4})
        assert c.is_category is True

    def test_dm(self):
        from discordium.models.channel import Channel
        c = Channel.from_payload({"id": "1", "type": 1})
        assert c.is_dm is True

    def test_thread(self):
        from discordium.models.channel import Channel
        c = Channel.from_payload({"id": "1", "type": 11, "guild_id": "10"})
        assert c.is_thread is True

    def test_forum(self):
        from discordium.models.channel import Channel
        c = Channel.from_payload({"id": "1", "type": 15})
        assert c.is_forum is True

    def test_stage(self):
        from discordium.models.channel import Channel
        c = Channel.from_payload({"id": "1", "type": 13})
        assert c.is_stage is True

    def test_mention(self):
        from discordium.models.channel import Channel
        assert Channel.from_payload({"id": "777", "type": 0}).mention == "<#777>"

    def test_jump_url(self):
        from discordium.models.channel import Channel
        c = Channel.from_payload({"id": "777", "type": 0, "guild_id": "111"})
        assert "111" in c.jump_url and "777" in c.jump_url

    def test_slowmode(self):
        from discordium.models.channel import Channel
        c = Channel.from_payload({"id": "1", "type": 0, "rate_limit_per_user": 10})
        assert c.slowmode_delay == 10

    def test_is_nsfw(self):
        from discordium.models.channel import Channel
        c = Channel.from_payload({"id": "1", "type": 0, "nsfw": True})
        assert c.is_nsfw is True

#  Member

class TestMember:
    PAYLOAD = {
        "user": {"id": "123", "username": "test", "discriminator": "0"},
        "nick": "Tester", "roles": ["100", "200"],
        "joined_at": "2024-01-15T12:00:00+00:00",
        "premium_since": "2024-06-01T00:00:00+00:00",
        "deaf": False, "mute": False,
    }

    def test_from_payload(self):
        from discordium.models.member import Member
        m = Member.from_payload(self.PAYLOAD)
        assert m.nick == "Tester"
        assert m.display_name == "Tester"

    def test_display_name_fallback(self):
        from discordium.models.member import Member
        m = Member.from_payload({**self.PAYLOAD, "nick": None})
        assert m.display_name == "test"

    def test_has_role(self):
        from discordium.models.member import Member
        m = Member.from_payload(self.PAYLOAD)
        assert m.has_role(100) is True
        assert m.has_role(999) is False

    def test_role_count(self):
        from discordium.models.member import Member
        m = Member.from_payload(self.PAYLOAD)
        assert m.role_count == 2

    def test_is_boosting(self):
        from discordium.models.member import Member
        assert Member.from_payload(self.PAYLOAD).is_boosting is True
        assert Member.from_payload({**self.PAYLOAD, "premium_since": None}).is_boosting is False

    def test_joined_at_dt(self):
        from discordium.models.member import Member
        m = Member.from_payload(self.PAYLOAD)
        assert m.joined_at_dt is not None
        assert m.joined_at_dt.year == 2024

    def test_timeout(self):
        from discordium.models.member import Member
        m = Member.from_payload({
            **self.PAYLOAD,
            "communication_disabled_until": "2099-01-01T00:00:00+00:00",
        })
        assert m.is_timed_out is True

    def test_not_timed_out(self):
        from discordium.models.member import Member
        assert Member.from_payload(self.PAYLOAD).is_timed_out is False

    def test_mention(self):
        from discordium.models.member import Member
        assert Member.from_payload(self.PAYLOAD).mention == "<@123>"

    def test_id_shortcut(self):
        from discordium.models.member import Member
        m = Member.from_payload(self.PAYLOAD)
        assert int(m.id) == 123

#  Role

class TestRole:
    PAYLOAD = {
        "id": "555", "name": "Moderator", "color": 0x5865F2,
        "hoist": True, "position": 5, "permissions": "104324673",
        "managed": False, "mentionable": True,
    }

    def test_from_payload(self):
        from discordium.models.role import Role
        r = Role.from_payload(self.PAYLOAD)
        assert r.name == "Moderator"
        assert r.hoist is True
        assert r.mentionable is True

    def test_color_hex(self):
        from discordium.models.role import Role
        r = Role.from_payload(self.PAYLOAD)
        assert r.color_hex == "#5865f2"

    def test_mention(self):
        from discordium.models.role import Role
        assert Role.from_payload(self.PAYLOAD).mention == "<@&555>"

    def test_is_default(self):
        from discordium.models.role import Role
        r = Role.from_payload({**self.PAYLOAD, "position": 0})
        assert r.is_default is True

    def test_is_booster_role(self):
        from discordium.models.role import Role
        r = Role.from_payload({**self.PAYLOAD, "tags": {"premium_subscriber": None}})
        assert r.is_booster_role is True

    def test_is_bot_managed(self):
        from discordium.models.role import Role
        r = Role.from_payload({**self.PAYLOAD, "tags": {"bot_id": "12345"}})
        assert r.is_bot_managed is True

    def test_display_icon_emoji(self):
        from discordium.models.role import Role
        r = Role.from_payload({**self.PAYLOAD, "unicode_emoji": "🎮"})
        assert r.display_icon == "🎮"

    def test_created_at(self):
        from discordium.models.role import Role
        r = Role.from_payload(self.PAYLOAD)
        assert isinstance(r.created_at, datetime)

#  Embed

class TestEmbed:
    def test_basic(self):
        from discordium.models.embed import Embed
        e = Embed(title="Hello", description="World", color=0xFF0000)
        d = e.to_dict()
        assert d["title"] == "Hello"
        assert d["color"] == 0xFF0000

    def test_add_field_immutable(self):
        from discordium.models.embed import Embed
        e1 = Embed(title="Test")
        e2 = e1.add_field(name="F1", value="V1")
        assert e1.fields is None
        assert len(e2.fields) == 1

    def test_builder_chain(self):
        from discordium.models.embed import Embed
        e = (
            Embed(title="Stats", color=0x00FF00)
            .add_field(name="A", value="1", inline=True)
            .add_field(name="B", value="2", inline=True)
            .set_footer(text="Footer")
            .set_author(name="Bot")
            .set_image(url="https://example.com/img.png")
            .set_thumbnail(url="https://example.com/thumb.png")
        )
        d = e.to_dict()
        assert len(d["fields"]) == 2
        assert d["footer"]["text"] == "Footer"
        assert d["author"]["name"] == "Bot"

    def test_empty_embed(self):
        from discordium.models.embed import Embed
        assert Embed().to_dict() == {}

    def test_field_count(self):
        from discordium.models.embed import Embed
        e = Embed().add_field(name="A", value="1").add_field(name="B", value="2")
        assert e.field_count == 2

    def test_total_char_count(self):
        from discordium.models.embed import Embed
        e = Embed(title="ABCD", description="12345").add_field(name="XX", value="YY")
        assert e.total_char_count == 4 + 5 + 2 + 2

    def test_remove_field(self):
        from discordium.models.embed import Embed
        e = Embed().add_field(name="A", value="1").add_field(name="B", value="2")
        e2 = e.remove_field(0)
        assert e2.field_count == 1
        assert e2.fields[0].name == "B"

    def test_clear_fields(self):
        from discordium.models.embed import Embed
        e = Embed().add_field(name="A", value="1").clear_fields()
        assert e.fields is None

    def test_set_timestamp(self):
        from discordium.models.embed import Embed
        e = Embed().set_timestamp()
        assert e.timestamp is not None

    def test_image_url(self):
        from discordium.models.embed import Embed
        e = Embed().set_image(url="https://img.com/x.png")
        assert e.image_url == "https://img.com/x.png"

    def test_thumbnail_url(self):
        from discordium.models.embed import Embed
        e = Embed().set_thumbnail(url="https://img.com/t.png")
        assert e.thumbnail_url == "https://img.com/t.png"

    def test_from_payload(self):
        from discordium.models.embed import Embed
        e = Embed.from_payload({
            "title": "Parsed", "color": 0xFF0000,
            "fields": [{"name": "F", "value": "V", "inline": True}],
            "footer": {"text": "Foot"},
            "author": {"name": "Auth"},
        })
        assert e.title == "Parsed"
        assert e.field_count == 1

#  Message

class TestMessage:
    BASE = {
        "id": "555", "channel_id": "777", "guild_id": "111",
        "author": {"id": "123", "username": "user", "discriminator": "0"},
        "content": "Hello World", "timestamp": "2024-01-01T00:00:00Z",
        "tts": False, "mention_everyone": False, "pinned": False,
        "type": 0, "flags": 0, "attachments": [], "embeds": [],
        "mentions": [], "mention_roles": [],
    }

    def test_from_payload(self):
        from discordium.models.message import Message
        m = Message.from_payload(self.BASE)
        assert m.content == "Hello World"
        assert int(m.id) == 555
        assert m.author.username == "user"

    def test_jump_url(self):
        from discordium.models.message import Message
        m = Message.from_payload(self.BASE)
        assert "111" in m.jump_url and "777" in m.jump_url and "555" in m.jump_url

    def test_jump_url_dm(self):
        from discordium.models.message import Message
        m = Message.from_payload({**self.BASE, "guild_id": None})
        assert "@me" in m.jump_url

    def test_is_reply(self):
        from discordium.models.message import Message
        # is_reply checks message_reference, not type
        assert Message.from_payload({
            **self.BASE, "type": 19,
            "message_reference": {"message_id": "444", "channel_id": "777"},
        }).is_reply is True
        assert Message.from_payload(self.BASE).is_reply is False

    def test_is_system(self):
        from discordium.models.message import Message
        assert Message.from_payload({**self.BASE, "type": 7}).is_system is True
        assert Message.from_payload(self.BASE).is_system is False

    def test_is_webhook(self):
        from discordium.models.message import Message
        assert Message.from_payload({**self.BASE, "webhook_id": "999"}).is_webhook is True
        assert Message.from_payload(self.BASE).is_webhook is False

    def test_is_ephemeral(self):
        from discordium.models.message import Message
        assert Message.from_payload({**self.BASE, "flags": 64}).is_ephemeral is True
        assert Message.from_payload(self.BASE).is_ephemeral is False

    def test_created_at(self):
        from discordium.models.message import Message
        m = Message.from_payload(self.BASE)
        assert m.created_at is not None

    def test_edited_at_none(self):
        from discordium.models.message import Message
        m = Message.from_payload(self.BASE)
        assert m.edited_at is None

    def test_edited_at_set(self):
        from discordium.models.message import Message
        m = Message.from_payload({**self.BASE, "edited_timestamp": "2024-02-01T00:00:00Z"})
        assert m.edited_at is not None

    def test_attachments_parsing(self):
        from discordium.models.message import Message
        m = Message.from_payload({
            **self.BASE,
            "attachments": [
                {"id": "1", "filename": "image.png", "size": 1024,
                 "url": "https://cdn/img.png", "content_type": "image/png",
                 "width": 800, "height": 600},
            ],
        })
        assert len(m.attachments) == 1
        att = m.attachments[0]
        assert att.filename == "image.png"
        assert att.is_image is True

    def test_image_attachments(self):
        from discordium.models.message import Message
        m = Message.from_payload({
            **self.BASE,
            "attachments": [
                {"id": "1", "filename": "img.png", "size": 100, "url": "u", "content_type": "image/png"},
                {"id": "2", "filename": "doc.pdf", "size": 100, "url": "u", "content_type": "application/pdf"},
            ],
        })
        images = m.image_attachments
        assert len(images) == 1
        assert images[0].filename == "img.png"

    def test_reactions_parsing(self):
        from discordium.models.message import Message
        m = Message.from_payload({
            **self.BASE,
            "reactions": [
                {"count": 5, "me": True, "emoji": {"id": None, "name": "👍"}},
            ],
        })
        assert len(m.reactions) == 1
        assert m.reactions[0].count == 5

    def test_get_reaction(self):
        from discordium.models.message import Message
        m = Message.from_payload({
            **self.BASE,
            "reactions": [
                {"count": 3, "me": False, "emoji": {"id": None, "name": "❤️"}},
                {"count": 1, "me": True, "emoji": {"id": None, "name": "👍"}},
            ],
        })
        r = m.get_reaction("👍")
        assert r is not None
        assert r.count == 1

    def test_mentions_user(self):
        from discordium.models.message import Message
        m = Message.from_payload({
            **self.BASE,
            "mentions": [{"id": "999", "username": "mentioned", "discriminator": "0"}],
        })
        assert m.mentions_user(999) is True
        assert m.mentions_user(888) is False

    def test_mentions_role(self):
        from discordium.models.message import Message
        m = Message.from_payload({
            **self.BASE,
            "mention_roles": ["555"],
        })
        assert m.mentions_role(555) is True
        assert m.mentions_role(444) is False

    def test_message_reference(self):
        from discordium.models.message import Message
        m = Message.from_payload({
            **self.BASE, "type": 19,
            "message_reference": {"message_id": "444", "channel_id": "777"},
        })
        assert m.message_reference is not None

    def test_sticker_items(self):
        from discordium.models.message import Message
        m = Message.from_payload({
            **self.BASE,
            "sticker_items": [{"id": "1", "name": "wave", "format_type": 1}],
        })
        assert len(m.sticker_items) == 1
        assert m.sticker_items[0].name == "wave"

    def test_embeds_parsing(self):
        from discordium.models.message import Message
        m = Message.from_payload({
            **self.BASE,
            "embeds": [{"title": "Embedded", "color": 0xFF0000}],
        })
        assert len(m.embeds) == 1
        assert m.embeds[0].title == "Embedded"

    def test_message_type_property(self):
        from discordium.models.message import Message, MessageType
        m = Message.from_payload(self.BASE)
        assert m.message_type == MessageType.DEFAULT

    def test_message_flags_property(self):
        from discordium.models.message import Message, MessageFlags
        m = Message.from_payload({**self.BASE, "flags": 64})
        assert m.message_flags & MessageFlags.EPHEMERAL

    def test_minimal_payload(self):
        from discordium.models.message import Message
        m = Message.from_payload({
            "id": "1", "channel_id": "2",
            "author": {"id": "3", "username": "u", "discriminator": "0"},
            "content": "", "type": 0, "flags": 0,
            "attachments": [], "embeds": [], "mentions": [], "mention_roles": [],
        })
        assert m.content == ""

    @pytest.mark.asyncio
    async def test_reply_requires_rest(self):
        from discordium.models.message import Message
        m = Message.from_payload(self.BASE)
        with pytest.raises(RuntimeError):
            await m.reply("hi")

    @pytest.mark.asyncio
    async def test_reply_with_rest(self):
        from discordium.models.message import Message
        rest = AsyncMock()
        rest.send_message = AsyncMock(return_value=MagicMock())
        m = Message.from_payload(self.BASE, rest=rest)
        await m.reply("hello")
        rest.send_message.assert_awaited_once()

    def test_repr(self):
        from discordium.models.message import Message
        m = Message.from_payload(self.BASE)
        r = repr(m)
        assert "555" in r

#  Thread

class TestThread:
    def test_from_payload(self):
        from discordium.models.thread import Thread
        t = Thread.from_payload({
            "id": "888", "type": 11, "guild_id": "111",
            "name": "Discussion", "owner_id": "222",
            "message_count": 42, "member_count": 5,
            "thread_metadata": {"archived": False, "auto_archive_duration": 1440, "locked": False},
        })
        assert t.name == "Discussion"
        assert t.message_count == 42
        assert t.is_archived is False
        assert t.is_locked is False

    def test_archived_locked(self):
        from discordium.models.thread import Thread
        t = Thread.from_payload({
            "id": "1", "type": 11,
            "thread_metadata": {"archived": True, "auto_archive_duration": 60, "locked": True},
        })
        assert t.is_archived is True
        assert t.is_locked is True

    def test_private_thread(self):
        from discordium.models.thread import Thread
        t = Thread.from_payload({"id": "1", "type": 12})
        assert t.is_private is True

    def test_mention(self):
        from discordium.models.thread import Thread
        assert Thread.from_payload({"id": "888", "type": 11}).mention == "<#888>"

#  Webhook

class TestWebhook:
    def test_from_payload(self):
        from discordium.models.webhook import Webhook
        w = Webhook.from_payload({
            "id": "999", "type": 1, "token": "abc_token",
            "channel_id": "777", "guild_id": "111", "name": "TestHook",
        })
        assert int(w.id) == 999
        assert w.name == "TestHook"

    def test_url(self):
        from discordium.models.webhook import Webhook
        w = Webhook.from_payload({"id": "999", "type": 1, "token": "abc"})
        assert w.url == "https://discord.com/api/webhooks/999/abc"

    def test_from_url(self):
        from discordium.models.webhook import Webhook
        w = Webhook.from_url(
            "https://discord.com/api/webhooks/123/secret-token",
            rest=MagicMock(),
        )
        assert int(w.id) == 123
        assert w.token == "secret-token"

    def test_invalid_url(self):
        from discordium.models.webhook import Webhook
        with pytest.raises(ValueError):
            Webhook.from_url("https://example.com/not-a-webhook", rest=MagicMock())

#  Audit Log

class TestAuditLog:
    def test_entry(self):
        from discordium.models.audit_log import AuditLogEntry
        e = AuditLogEntry.from_payload({
            "id": "1", "user_id": "222", "target_id": "333",
            "action_type": 22, "reason": "Spamming",
        })
        assert int(e.user_id) == 222
        assert e.reason == "Spamming"

    def test_container(self):
        from discordium.models.audit_log import AuditLog, AuditLogEvent
        log = AuditLog({
            "audit_log_entries": [
                {"id": "1", "action_type": 22, "user_id": "10", "target_id": "20"},
                {"id": "2", "action_type": 20, "user_id": "10", "target_id": "30"},
                {"id": "3", "action_type": 22, "user_id": "11", "target_id": "40"},
            ],
        })
        assert len(log) == 3
        bans = log.filter_by(AuditLogEvent.MEMBER_BAN_ADD)
        assert len(bans) == 2

    def test_changes(self):
        from discordium.models.audit_log import AuditLogEntry
        e = AuditLogEntry.from_payload({
            "id": "1", "action_type": 1,
            "changes": [{"key": "name", "old_value": "Old", "new_value": "New"}],
        })
        assert len(e.changes) == 1
        assert e.changes[0].key == "name"

#  Permissions & Intents

class TestPermissions:
    def test_basic_has(self):
        p = Permissions.SEND_MESSAGES | Permissions.EMBED_LINKS
        assert p.has(Permissions.SEND_MESSAGES)
        assert not p.has(Permissions.BAN_MEMBERS)

    def test_administrator_overrides(self):
        assert Permissions.ADMINISTRATOR.has(Permissions.BAN_MEMBERS)

    def test_has_any(self):
        p = Permissions.SEND_MESSAGES
        assert p.has_any(Permissions.SEND_MESSAGES, Permissions.BAN_MEMBERS)
        assert not p.has_any(Permissions.BAN_MEMBERS, Permissions.KICK_MEMBERS)

    def test_from_value_string(self):
        assert Permissions.from_value("2048").has(Permissions.SEND_MESSAGES)

    def test_presets(self):
        assert Permissions.moderator().has(Permissions.KICK_MEMBERS)

    def test_overwrite(self):
        ow = PermissionOverwrite(id=123, type=0, allow=2048, deny=4096)
        assert ow.allow.has(Permissions.SEND_MESSAGES)
        assert ow.to_dict()["id"] == "123"


class TestIntents:
    def test_default_excludes_privileged(self):
        d = Intents.default()
        assert not (d & Intents.GUILD_MEMBERS)
        assert not (d & Intents.MESSAGE_CONTENT)

    def test_all_includes_privileged(self):
        a = Intents.all()
        assert a & Intents.GUILD_MEMBERS
        assert a & Intents.MESSAGE_CONTENT

    def test_compose(self):
        i = Intents.default() | Intents.MESSAGE_CONTENT
        assert i & Intents.MESSAGE_CONTENT

    def test_none(self):
        assert int(Intents.none()) == 0
