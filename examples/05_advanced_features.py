"""
05_advanced_features.py — Files, Webhooks, Threads, and Audit Logs.

Demonstrates:
  - Uploading files as attachments
  - Creating and using webhooks
  - Creating threads (text + forum)
  - Querying audit logs
  - Permission checks with guards
  - Background tasks with loop safety
"""

import os
import discordium
from discordium.ext.slash import SlashRouter, slash_option, OptionType
from discordium.ext.tasks import loop
from discordium.ext.guards import has_permissions, cooldown, guild_only
from discordium.models.events import ReadyEvent
from discordium.models.interaction import Interaction

bot = discordium.GatewayClient(
    token=os.environ["DISCORD_TOKEN"],
    intents=discordium.Intents.default(),
)
slash = SlashRouter()

#  File Uploads

@slash.command(name="export", description="Export server info as a file")
@guild_only()
async def export_cmd(inter: Interaction) -> None:
    await inter.defer()

    guild = await bot.fetch_guild(inter.guild_id)
    roles = await bot.fetch_roles(inter.guild_id)

    lines = [
        f"Server: {guild.name}",
        f"ID: {guild.id}",
        f"Boost Level: {guild.premium_tier}",
        f"Boosts: {guild.premium_subscription_count}",
        "",
        f"Roles ({len(roles)}):",
    ]
    for role in sorted(roles, key=lambda r: r.position, reverse=True):
        lines.append(f"  - {role.name} ({role.color_hex})")

    file = discordium.File(
        "\n".join(lines).encode("utf-8"),
        filename=f"{guild.name}_info.txt",
        description="Server information export",
    )
    await inter.followup("Here is your server export:", files=[file])

#  Webhooks

@slash.command(name="webhook-test", description="Create and send a webhook message")
@has_permissions(discordium.Permissions.MANAGE_WEBHOOKS)
@guild_only()
async def webhook_test(inter: Interaction) -> None:
    await inter.defer(ephemeral=True)

    # Create a temporary webhook
    webhook = await bot.rest.create_webhook(inter.channel_id, name="discordium-test")

    # Send a message through it
    await webhook.send(
        "Hello from a webhook!",
        username="Webhook Bot",
        embed=discordium.Embed(
            title="Webhook Message",
            description="This was sent via the discordium webhook API.",
            color=0x5865F2,
        ),
    )

    # Clean up
    await webhook.delete()
    await inter.followup("Webhook message sent and cleaned up!")

#  Threads

@slash.command(name="discuss", description="Start a discussion thread")
@slash_option("topic", "Thread topic", type=OptionType.STRING, required=True)
@slash_option("message", "Opening message", type=OptionType.STRING)
@guild_only()
async def discuss(inter: Interaction) -> None:
    await inter.defer()

    topic = inter.option_string("topic")
    opening = inter.option_string("message", default=f"Discussion: {topic}")

    thread = await bot.rest.create_thread(
        inter.channel_id,
        name=topic,
        auto_archive_duration=1440,  # 24 hours
    )

    await bot.rest.send_message(thread.id, opening)
    await inter.followup(f"Thread created: {thread.mention}")

#  Audit Logs

@slash.command(name="recent-bans", description="Show recent bans from the audit log")
@has_permissions(discordium.Permissions.VIEW_AUDIT_LOG)
@guild_only()
async def recent_bans(inter: Interaction) -> None:
    await inter.defer(ephemeral=True)

    logs = await bot.rest.get_audit_log(
        inter.guild_id,
        action_type=discordium.AuditLogEvent.MEMBER_BAN_ADD,
        limit=10,
    )

    if not logs.entries:
        await inter.followup("No recent bans found.")
        return

    lines = []
    for entry in logs.entries:
        moderator = f"<@{entry.user_id}>" if entry.user_id else "Unknown"
        target = f"<@{entry.target_id}>" if entry.target_id else "Unknown"
        reason = entry.reason or "No reason"
        lines.append(f"{moderator} banned {target}: {reason}")

    embed = discordium.Embed(
        title="Recent Bans",
        description="\n".join(lines),
        color=0xED4245,
    )
    await inter.followup(embed=embed)

#  Guards (Permission Checks + Cooldowns)

@slash.command(name="slow", description="A rate-limited command")
@cooldown(rate=1, per=30.0)  # 1 use per 30 seconds per user
async def slow_cmd(inter: Interaction) -> None:
    await inter.respond("You used the slow command! (30s cooldown)", ephemeral=True)

#  Background Tasks (with loop safety)

@loop(minutes=10)
async def health_check():
    """Runs every 10 minutes. Safe to call .start() multiple times."""
    print(f"Health check: {bot.guild_count} guilds, uptime: {bot.uptime:.0f}s")

@health_check.before
async def before_health():
    print("Health check loop starting...")

@health_check.error
async def on_health_error(exc: Exception):
    print(f"Health check error: {exc}")

# Startup 
@bot.on_event("ready")
async def on_ready(event: ReadyEvent) -> None:
    await bot.sync_commands(slash)
    # Safe to call multiple times — won't start a second loop on reconnect
    health_check.start()
    print(f"Advanced bot ready: {event.user.display_name}")

@bot.on_error
async def on_error(event_name: str, error: Exception) -> None:
    # Handle specific error types
    if isinstance(error, discordium.Forbidden):
        print(f"Permission error in {event_name}: {error}")
    elif isinstance(error, discordium.NotFound):
        print(f"Not found error in {event_name}: {error}")
    else:
        print(f"Error in {event_name}: {type(error).__name__}: {error}")


slash.attach(bot)
bot.run()
