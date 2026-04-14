# Changelog

All notable changes to discordium will be documented in this file.

### [0.1.0-beta] - 2026-04-14

### Initial beta release

**Core**
- `GatewayClient` with typed event dispatch, lifecycle guards, guild caching
- `EventDispatcher` architecture (no monkeypatching)
- `EventEmitter` with `wait_for()`, `@listener`, `@once`
- 30+ typed gateway events (no more `data: dict`)
- Structured exception hierarchy (20+ error classes)
- Before/after middleware hooks
- Global error handler

**Models**
- Comprehensive models: User, Guild, Channel, Member, Role, Message, Embed
- Attachment, Reaction, Emoji, Sticker, Poll models
- Thread, Webhook, AuditLog, AutoMod models
- Permissions bitfield with presets and helpers
- Intents bitfield with presets
- Interaction with high-level option resolvers
- Components: Button, SelectMenu, Modal, TextInput, ActionRow
- All models are frozen slotted dataclasses (immutable)
- `evolve()` for safe mutation

**HTTP**
- REST client with 60+ endpoints
- Automatic per-route rate limiting
- Multipart file upload support
- orjson for fast JSON serialisation
- Retry on 5xx with exponential backoff

**Gateway**
- WebSocket connection with zlib compression
- Heartbeat loop with latency tracking
- Automatic resume after disconnect
- Exponential backoff with jitter
- ShardManager for auto/manual sharding

**Extensions**
- `SlashRouter` - slash commands with options, subcommands, autocomplete
- `CommandRouter` - prefix commands
- `@loop()` - background tasks with lifecycle hooks (idempotent start)
- Guards: `@has_permissions`, `@cooldown`, `@guild_only`, `@dm_only`, `@owner_only`
- `Paginator` - embed pagination with button navigation

**Testing**
- 400+ tests across 5 test files
- Models, events, interactions, guards, dispatcher, gateway, rate limiter, components
- Edge cases: reconnect, multiple READY, interaction lifecycle, cooldown races, partial payloads

**Infrastructure**
- GitHub Actions CI (lint, typecheck, test on 3.11/3.12/3.13, build)
- PEP-561 compliant (`py.typed`)
- pyproject.toml with optional dependencies
