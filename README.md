# Discordium

Async-first Discord API wrapper for Python 3.11+

Fully typed, modern architecture built for performance, correctness, and developer experience.

---

### Why discordium?

- Async-first design built for Python 3.11+
- Immutable, slotted dataclass models
- Fully typed API with strict mypy support (PEP 561)
- Typed event system no raw dict payloads
- High-performance JSON via orjson
- Pluggable caching (NoCache, TTLCache, or custom strategies)
- Built-in slash command system with autocomplete, components, and modals
- Structured error system with 20+ exception types
- Flexible sharding (auto, manual, distributed)
- Event middleware (before/after hooks)

---

### Command System

discordium is **slash-first**. The slash command system is fully featured:
autocomplete, subcommands, components, modals, typed options, and permission guards.

**Prefix commands** (`CommandRouter`) are supported as a lightweight secondary
option useful for quick development bots or mixed environments. They are intentionally
minimal and not on par with the slash system.

---

### Installation

```bash
pip install discordium
pip install discordium[speed]   # aiodns + Brotli
pip install discordium[voice]   # PyNaCl
```

---

### Quick Start

```python
import discordium
from discordium.ext.slash import SlashRouter
from discordium.models.events import ReadyEvent
from discordium.models.interaction import Interaction

bot = discordium.GatewayClient(
    token="YOUR_TOKEN",
    intents=discordium.Intents.default(),
)
slash = SlashRouter()

@slash.command(name="ping", description="Check latency")
async def ping(inter: Interaction) -> None:
    await inter.respond("Pong!", ephemeral=True)

@bot.on_event("ready")
async def on_ready(event: ReadyEvent) -> None:
    print(f"Online as {event.user.display_name}!")

slash.attach(bot)
bot.run()
```

---

### Typed Event Names

Avoid magic strings with the `Events` constants or the `EventName` literal type:

```python
from discordium.models.event_names import Events, EventName

@bot.on_event(Events.MESSAGE_CREATE)
async def on_msg(event): ...

@bot.on_event(Events.GUILD_MEMBER_ADD)
async def on_join(event): ...
```

---

### Typed Events

Every event handler receives a proper typed object no more `data: dict`:

```python
from discordium.models.events import MessageCreateEvent

@bot.on_event("message_create")
async def on_msg(event: MessageCreateEvent) -> None:
    if event.message.content == "hello":
        await event.message.reply("Hey!")
```

30+ typed events supported (messages, guilds, members, reactions, threads, voice, etc.)

---

### High-Level Option Resolvers

```python
@slash.command(name="info")
async def info(inter: Interaction) -> None:
    user = inter.option_user("user")
    detailed = inter.option_bool("detailed", default=False)
```

---

### Components

```python
from discordium.models.components import *

row = ActionRow(
    Button(label="Yes", custom_id="vote:yes"),
    Button(label="No", custom_id="vote:no"),
)

await inter.respond("Vote:", components=[row])

@slash.on_component("vote:")
async def on_vote(inter):
    choice = inter.custom_id.split(":")[1]
    await inter.respond(f"You voted {choice}!", ephemeral=True)
```

---

### Modals

```python
modal = Modal(title="Feedback", custom_id="feedback")
modal.add_field(label="Message", custom_id="msg")

await inter.send_modal(modal)

@slash.on_modal("feedback")
async def on_fb(inter):
    fields = inter.get_all_fields()
    await inter.respond(fields["msg"])
```

---

### Structured Errors

```python
try:
    await rest.ban_member(guild_id, user_id)
except discordium.Forbidden:
    ...
except discordium.NotFound:
    ...
```

---

### Middleware

```python
@bot.before_event
async def before(event_name, event):
    ...

@bot.after_event
async def after(event_name, event):
    ...
```

---

### Guards and Cooldowns

```python
from discordium.ext.guards import has_permissions, cooldown

@slash.command(name="ban")
@has_permissions(...)
@cooldown(rate=1, per=30)
async def ban(inter):
    ...
```

---

### Background Tasks

```python
from discordium.ext.tasks import loop

@loop(minutes=5)
async def task():
    ...

task.start()
```

---

### File Uploads

```python
file = discordium.File(data.encode(), filename="export.txt")
await rest.send_message(channel_id, "Here:", files=[file])
```

---

### Webhooks

```python
wh = await rest.create_webhook(channel_id, name="Alerts")
await wh.send("Server alert!")
```

---

### Architecture

```
discordium/
├── client.py
├── errors.py
├── models/
├── gateway/
├── http/
├── cache/
├── ext/
└── utils/
```

---

### Versioning

Discordium follows Semantic Versioning.

During the 0.x phase, breaking changes may occur between releases.

---

### License

MIT
