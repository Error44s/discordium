"""
01_quickstart.py — Your first discordium bot.

This is the simplest possible bot. It responds to /ping with "Pong!".

Run:
    DISCORD_TOKEN=your_token python examples/01_quickstart.py

--- Syncing slash commands ---

Slash commands must be registered with Discord before they appear in clients.
You only need to sync when your command list actually changes.

DEV: sync inside on_ready so every bot start picks up changes.
     Use guild_id= for instant updates (global commands can take up to 1h).

PROD: sync once from a deploy script — not on every boot.
      See the README for a standalone sync example.
"""

import os

import discordium
from discordium.ext.slash import SlashRouter
from discordium.models.event_names import Events
from discordium.models.events import ReadyEvent
from discordium.models.interaction import Interaction

bot = discordium.GatewayClient(
    token=os.environ["DISCORD_TOKEN"],
    intents=discordium.Intents.default(),
)
slash = SlashRouter()


@slash.command(name="ping", description="Check if the bot is alive")
async def ping(inter: Interaction) -> None:
    await inter.respond("Pong!", ephemeral=True)


# DEV: sync in on_ready with a guild_id for instant feedback.
# PROD: remove this and sync from your deploy pipeline instead.
@bot.on_event(Events.READY)
async def on_ready(event: ReadyEvent) -> None:
    MY_DEV_GUILD_ID = None  # set to your guild int for dev, None for global
    await bot.sync_commands(slash, guild_id=MY_DEV_GUILD_ID)
    print(f"Bot is online as {event.user.display_name}!")


slash.attach(bot)
bot.run()
