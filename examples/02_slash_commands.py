"""
02_slash_commands.py — Slash commands with options, subcommands, and autocomplete.

Demonstrates:
  - Simple commands with typed options
  - Subcommand groups
  - Autocomplete suggestions
  - High-level option resolvers (option_string, option_user, etc.)
"""

import os
import discordium
from discordium.ext.slash import SlashRouter, slash_option, OptionType
from discordium.models.events import ReadyEvent
from discordium.models.interaction import Interaction

bot = discordium.GatewayClient(
    token=os.environ["DISCORD_TOKEN"],
    intents=discordium.Intents.default(),
)
slash = SlashRouter()

# Simple command with typed option resolvers 

@slash.command(name="greet", description="Greet someone")
@slash_option("user", "Who to greet", type=OptionType.USER, required=True)
@slash_option("message", "Custom greeting", type=OptionType.STRING)
async def greet(inter: Interaction) -> None:
    # option_user() auto-resolves the snowflake into a full User object
    target = inter.option_user("user")
    msg = inter.option_string("message", default="Hello!")

    if target:
        await inter.respond(f"{msg}, {target.display_name}!")
    else:
        await inter.respond("Could not resolve user.", ephemeral=True)

@slash.command(name="roll", description="Roll dice")
@slash_option("sides", "Number of sides", type=OptionType.INTEGER, min_value=2, max_value=100)
@slash_option("count", "How many dice", type=OptionType.INTEGER, min_value=1, max_value=20)
async def roll(inter: Interaction) -> None:
    import random

    sides = inter.option_int("sides", default=6)
    count = inter.option_int("count", default=1)
    results = [random.randint(1, sides) for _ in range(count)]
    total = sum(results)

    if count == 1:
        await inter.respond(f"You rolled a **{total}**")
    else:
        rolls_str = ", ".join(str(r) for r in results)
        await inter.respond(f"Rolled {count}d{sides}: {rolls_str} = **{total}**")

# Subcommand group 

config = slash.group("config", "Bot configuration")

@config.command(name="language", description="Set display language")
@slash_option(
    "lang", "Language", type=OptionType.STRING, required=True,
    choices=[("English", "en"), ("Deutsch", "de"), ("Francais", "fr")],
)
async def set_language(inter: Interaction) -> None:
    lang = inter.option_string("lang")
    await inter.respond(f"Language set to `{lang}`", ephemeral=True)

@config.command(name="notifications", description="Toggle notifications")
@slash_option("enabled", "Enable notifications?", type=OptionType.BOOLEAN, required=True)
async def set_notifications(inter: Interaction) -> None:
    enabled = inter.option_bool("enabled")
    status = "enabled" if enabled else "disabled"
    await inter.respond(f"Notifications {status}", ephemeral=True)

# Autocomplete 

FRUITS = ["Apple", "Banana", "Cherry", "Date", "Elderberry", "Fig", "Grape",
          "Honeydew", "Kiwi", "Lemon", "Mango", "Nectarine", "Orange"]

@slash.command(name="fruit", description="Pick a fruit")
@slash_option("name", "Fruit name", type=OptionType.STRING, required=True, autocomplete=True)
async def fruit_cmd(inter: Interaction) -> None:
    name = inter.option_string("name")
    await inter.respond(f"You picked: {name}")

@fruit_cmd.autocomplete("name")
async def fruit_autocomplete(inter: Interaction) -> None:
    current = (inter.option_string("name") or "").lower()
    matches = [
        {"name": f, "value": f.lower()}
        for f in FRUITS if current in f.lower()
    ]
    await inter.autocomplete(matches[:25])

# Startup 
@bot.on_event("ready")
async def on_ready(event: ReadyEvent) -> None:
    await bot.sync_commands(slash)
    print(f"Slash commands synced! Bot: {event.user.display_name}")


slash.attach(bot)
bot.run()
