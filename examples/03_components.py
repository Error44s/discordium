"""
03_components.py — Buttons, Select Menus, and Modals.

Demonstrates:
  - Creating interactive buttons
  - Handling button clicks
  - Select menus (dropdowns)
  - Modal popups with text inputs
  - Updating messages from components
"""

import os
import discordium
from discordium.ext.slash import SlashRouter, slash_option, OptionType
from discordium.models.events import ReadyEvent
from discordium.models.interaction import Interaction
from discordium.models.components import (
    ActionRow, Button, ButtonStyle,
    SelectMenu, SelectOption,
    Modal, TextInput, TextInputStyle,
)

bot = discordium.GatewayClient(
    token=os.environ["DISCORD_TOKEN"],
    intents=discordium.Intents.default(),
)
slash = SlashRouter()

#  Buttons

@slash.command(name="counter", description="Interactive counter with buttons")
async def counter(inter: Interaction) -> None:
    # Buttons persist across bot restarts because the custom_id pattern
    # is registered with on_component, not tied to a specific message.
    row = ActionRow(
        Button(label="-1", custom_id="counter:dec", style=ButtonStyle.DANGER),
        Button(label="0", custom_id="counter:display", style=ButtonStyle.SECONDARY, disabled=True),
        Button(label="+1", custom_id="counter:inc", style=ButtonStyle.SUCCESS),
        Button(label="Reset", custom_id="counter:reset", style=ButtonStyle.PRIMARY),
    )
    await inter.respond("**Counter:** 0", components=[row])

# NOTE: Components use prefix matching — "counter:" catches all counter buttons.
# The full custom_id is available via inter.custom_id for dispatching.

@slash.on_component("counter:")
async def on_counter(inter: Interaction) -> None:
    # Parse current value from the message content
    msg = inter.message_data or {}
    content = msg.get("content", "**Counter:** 0")
    try:
        current = int(content.split(":** ")[1])
    except (IndexError, ValueError):
        current = 0

    action = inter.custom_id.split(":")[1] if inter.custom_id else ""

    match action:
        case "inc":
            current += 1
        case "dec":
            current -= 1
        case "reset":
            current = 0

    # Update the button label to show current value
    row = ActionRow(
        Button(label="-1", custom_id="counter:dec", style=ButtonStyle.DANGER),
        Button(label=str(current), custom_id="counter:display", style=ButtonStyle.SECONDARY, disabled=True),
        Button(label="+1", custom_id="counter:inc", style=ButtonStyle.SUCCESS),
        Button(label="Reset", custom_id="counter:reset", style=ButtonStyle.PRIMARY),
    )
    await inter.update_message(content=f"**Counter:** {current}", components=[row])

#  Select Menus

@slash.command(name="pizza", description="Build your pizza order")
async def pizza(inter: Interaction) -> None:
    menu = SelectMenu(
        custom_id="pizza_toppings",
        placeholder="Choose your toppings (up to 3)...",
        min_values=1,
        max_values=3,
        options=[
            SelectOption(label="Pepperoni", value="pepperoni", emoji="🍕"),
            SelectOption(label="Mushrooms", value="mushrooms", emoji="🍄"),
            SelectOption(label="Onions", value="onions", emoji="🧅"),
            SelectOption(label="Olives", value="olives", emoji="🫒"),
            SelectOption(label="Pineapple", value="pineapple", emoji="🍍", description="Yes, it belongs on pizza"),
        ],
    )
    await inter.respond("Build your pizza:", components=[ActionRow(menu)])

@slash.on_component("pizza_toppings")
async def on_pizza(inter: Interaction) -> None:
    toppings = ", ".join(inter.values)
    await inter.respond(f"Your pizza with **{toppings}** is on its way!", ephemeral=True)

#  Modals

@slash.command(name="report", description="Report an issue")
async def report(inter: Interaction) -> None:
    modal = Modal(title="Bug Report", custom_id="bug_report")
    modal.add_field(
        label="Summary",
        custom_id="report_summary",
        style=TextInputStyle.SHORT,
        placeholder="Brief description of the issue",
        max_length=100,
        required=True,
    )
    modal.add_field(
        label="Steps to Reproduce",
        custom_id="report_steps",
        style=TextInputStyle.PARAGRAPH,
        placeholder="1. Go to...\n2. Click on...\n3. See error",
        required=True,
    )
    modal.add_field(
        label="Expected Behavior",
        custom_id="report_expected",
        style=TextInputStyle.PARAGRAPH,
        placeholder="What should have happened?",
        required=False,
    )
    await inter.send_modal(modal)

@slash.on_modal("bug_report")
async def on_bug_report(inter: Interaction) -> None:
    # get_all_fields() returns {custom_id: value} for all text inputs
    fields = inter.get_all_fields()

    embed = (
        discordium.Embed(title="Bug Report", color=0xED4245)
        .add_field(name="Summary", value=fields.get("report_summary", "N/A"), inline=False)
        .add_field(name="Steps", value=fields.get("report_steps", "N/A"), inline=False)
        .add_field(name="Expected", value=fields.get("report_expected", "Not specified"), inline=False)
        .set_footer(text=f"Reported by {inter.user.display_name}" if inter.user else "Anonymous")
    )
    await inter.respond("Bug report submitted! Thank you.", embed=embed)

# Startup 
@bot.on_event("ready")
async def on_ready(event: ReadyEvent) -> None:
    await bot.sync_commands(slash)
    print(f"Components example ready! Bot: {event.user.display_name}")


slash.attach(bot)
bot.run()
