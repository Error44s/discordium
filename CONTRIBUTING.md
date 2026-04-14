# Contributing to Discordium

Thanks for your interest in contributing!

### Development Setup

```bash
git clone https://github.com/Error44s/discordium.git
cd discordium
pip install -e ".[dev]"
```

### Running Tests

```bash
python -m pytest tests/ -v
```

### Code Style

We use **ruff** for linting and formatting:

```bash
ruff check discordium/
ruff format discordium/
```

### Type Checking

```bash
mypy discordium/ --ignore-missing-imports
```

### Pull Request Guidelines

1. Fork the repo and create a branch from `main`
2. Add tests for any new functionality
3. Ensure all tests pass
4. Run linting and fix any issues
5. Update documentation if needed
6. Submit a PR with a clear description

### Architecture

- `discordium/models/` - Immutable frozen dataclasses for all Discord objects
- `discordium/gateway/` - WebSocket connection, heartbeat, reconnection
- `discordium/http/` - REST client with rate limiting
- `discordium/ext/` - Extensions (slash commands, prefix commands, tasks, guards)
- `discordium/utils/` - Event system, dispatcher, backoff
- `discordium/client.py` - High-level GatewayClient
- `discordium/errors.py` - Structured exception hierarchy

### Versioning

We follow [SemVer](https://semver.org/). During beta (0.x), minor versions may include breaking changes.
