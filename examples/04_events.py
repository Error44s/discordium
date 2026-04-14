"""
04_events.py — Typed event system.

Demonstrates:
  - Typed event handlers (no more raw dicts!)
  - All major event types
  - Error handling hooks
  - Before/after middleware
  - wait_for with typed events
"""

import os
import discordium
from discordium.ext.slash import SlashRouter
from discordium.models.events import (
    ReadyEvent,
    MessageCreateEvent,
    GuildMemberAddEvent,
    GuildMemberRemoveEvent,
    MessageReactionAddEvent,
    GuildBanAddEvent,
    GatewayEvent,
)
from discordium.models.interaction import Interaction

bot = discordium.GatewayClient(
    token=os.environ["DISCORD_TOKEN"],
    intents=discordium.Intents.all(),  # all intents for this demo
)
slash = SlashRouter()

#  Typed Events — every handler gets a proper typed object

@bot.on_event("ready")
async def on_ready(event: ReadyEvent) -> None:
    """ReadyEvent gives you: event.user, event.guilds, event.session_id"""
    await bot.sync_commands(slash)
    print(f"Logged in as {event.user.display_name} (ID: {event.user.id})")
    print(f"Connected to {len(event.guilds)} guild(s)")
    print(f"Session: {event.session_id[:8]}...")

@bot.on_event("message_create")
async def on_message(event: MessageCreateEvent) -> None:
    """MessageCreateEvent gives you: event.message (a full Message object)"""
    msg = event.message

    # Ignore bots
    if msg.author and msg.author.bot:
        return

    if msg.content.lower() == "hello":
        await msg.reply(f"Hey {msg.author.display_name}!")

    if msg.content.lower() == "react":
        await msg.react("👍")

@bot.on_event("guild_member_add")
async def on_member_join(event: GuildMemberAddEvent) -> None:
    """GuildMemberAddEvent gives you: event.member, event.guild_id"""
    member = event.member
    print(f"{member.display_name} joined guild {event.guild_id}")

    # NOTE: In production, you'd store the welcome channel ID in config,
    # not search for it. This is just a demo.

@bot.on_event("guild_member_remove")
async def on_member_leave(event: GuildMemberRemoveEvent) -> None:
    """GuildMemberRemoveEvent gives you: event.user, event.guild_id"""
    print(f"{event.user.display_name} left guild {event.guild_id}")

@bot.on_event("message_reaction_add")
async def on_reaction(event: MessageReactionAddEvent) -> None:
    """MessageReactionAddEvent gives you: event.user_id, event.emoji, event.member"""
    emoji_name = event.emoji.get("name", "?")
    print(f"Reaction {emoji_name} added by {event.user_id}")

@bot.on_event("guild_ban_add")
async def on_ban(event: GuildBanAddEvent) -> None:
    """GuildBanAddEvent gives you: event.user, event.guild_id"""
    print(f"{event.user.display_name} was banned from {event.guild_id}")

#  wait_for — block until a specific event occurs

@slash.command(name="confirm", description="Test the wait_for system")
async def confirm_cmd(inter: Interaction) -> None:
    await inter.respond("Type `yes` to confirm or `no` to cancel (30s timeout)")

    try:
        event: MessageCreateEvent = await bot.wait_for(
            "message_create",
            check=lambda e: (
                isinstance(e, MessageCreateEvent)
                and e.message.author
                and inter.user
                and e.message.author.id == inter.user.id
                and e.message.content.lower() in ("yes", "no")
            ),
            timeout=30.0,
        )

        if event.message.content.lower() == "yes":
            await inter.followup("Confirmed!")
        else:
            await inter.followup("Cancelled.")

    except TimeoutError:
        await inter.followup("Timed out — no response received.")

#  Error Handling — catch errors from any event handler

@bot.on_error
async def handle_error(event_name: str, error: Exception) -> None:
    """Global error handler — catches errors from all event handlers."""
    print(f"[ERROR] in {event_name}: {type(error).__name__}: {error}")

#  Middleware — before/after every event

@bot.before_event
async def log_events(event_name: str, event: GatewayEvent) -> None:
    """Runs before every event handler. Return False to cancel dispatch."""
    # Uncomment for verbose logging:
    # print(f"[EVENT] {event_name}")
    pass

@bot.after_event
async def track_events(event_name: str, event: GatewayEvent) -> None:
    """Runs after every event handler completes."""
    # Good place for metrics, analytics, etc.
    pass

# Run 

slash.attach(bot)
bot.run()
