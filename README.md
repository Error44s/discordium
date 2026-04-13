# Discordium

> Async-first, typed Discord API wrapper for Python 3.11+

⚠️ **discordium is in active development.**
APIs may change and some features are still being hardened.

Built from scratch with a focus on modern Python, type safety, and a clean developer experience.

---

### Philosophy

discordium is designed to be:

* **Typed-first** → no more guessing payloads
* **Async-native** → built for modern Python
* **Minimal but powerful** → no heavy abstractions
* **Explicit over magic** → predictable behavior

---

### Installation

```bash
pip install discordium
pip install discordium[speed]   # optional performance deps
pip install discordium[voice]   # optional voice support
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
    print(f"Online as {event.user.display_name}")

slash.attach(bot)
bot.run()
```

---

### Typed Events

Every event handler receives a structured, typed object.

```python
from discordium.models.events import MessageCreateEvent

@bot.on_event("message_create")
async def on_message(event: MessageCreateEvent):
    if event.message.content == "hello":
        await event.message.reply("Hey!")
```

---

### Slash Commands (First-Class)

```python
@slash.command(name="info", description="User info")
async def info(inter: Interaction):
    await inter.respond("Hello!")
```

Features include:

* autocomplete
* subcommands
* typed options
* permission guards
* modals & components

---

### Components & Modals

```python
from discordium.models.components import *

row = ActionRow(
    Button(label="Yes", custom_id="vote:yes"),
    Button(label="No", custom_id="vote:no"),
)

await inter.respond("Vote:", components=[row])

@slash.on_component("vote:")
async def vote(inter: Interaction):
    await inter.respond("Vote received!", ephemeral=True)
```

---

### Structured Errors

```python
try:
    await rest.ban_member(guild_id, user_id)
except discordium.Forbidden:
    print("Missing permissions")
except discordium.NotFound:
    print("User not found")
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

### Guards & Cooldowns

```python
from discordium.ext.guards import has_permissions, cooldown

@slash.command(name="ban")
@has_permissions(Permissions.BAN_MEMBERS)
@cooldown(rate=1, per=30)
async def ban(inter: Interaction):
    ...
```

---

### Background Tasks

```python
from discordium.ext.tasks import loop

@loop(minutes=5)
async def job():
    ...

job.start()
```

---

### Current Status

* Core features implemented
* Actively evolving
* Suitable for development and early production use
* API stability is still improving

---

### Roadmap

* [ ] API stabilization
* [ ] Expanded REST coverage
* [ ] Improved rate limiting
* [ ] More typed models
* [ ] Voice support improvements
* [ ] Documentation expansion

---

### Getting Help

* Open an issue for bugs or feature requests
* Discussions may be added later

---

### License

MIT
