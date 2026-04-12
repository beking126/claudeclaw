# claudebot-gateway

Gateway daemon around Claude Agent SDK. Provides multi-channel messaging, cron scheduling, heartbeat checks, and session persistence via SQLite.

## Features

### Channels
- **CLI** — enabled by default, prints responses to stdout
- **Telegram** — full adapter with configurable retry/backoff
- **Feishu (Lark)** — full adapter with webhook + event handling, configurable retry/backoff
- **Discord, Slack, WhatsApp** — stub adapters (log warnings, ready for real implementations)

### Messaging pipeline
- Bounded async message bus (inbound/outbound queues)
- Agent worker consumes inbound, executes Claude Agent SDK, publishes outbound
- Outbound dispatcher with per-adapter error isolation
- Per-sender rate limiting (sliding window, configurable)

### Cron scheduling
- `cron add --every 3600 --prompt "..." --channel telegram --destination "chat:123"`
- `cron add --at "2026-04-12T15:30" --prompt "..." ...` (one-shot, accepts ISO datetime or epoch)
- `cron add --cron "*/5 * * * *" --prompt "..." ...` (supports `*`, `*/N`, ranges `1-5`, lists `1,3,5`)
- `cron list` / `cron remove --job-id <id>`
- Delivery retry with exponential backoff

### Heartbeat
- Reads `workspaces/heartbeat/HEARTBEAT.md` on a configurable interval
- Only triggers agent execution when file has actionable content
- Purges old agent turns based on retention config

### Session persistence
- Stores agent turns (prompt/response) in SQLite per session
- Automatically resumes previous session for same workspace/channel/destination
- Workspace prompt files: `SOUL.md`, `USER.md`, `TOOLS.md` composed into agent context

### Security
- Sender allow-lists per channel
- Workspace path traversal prevention (`validate_workspace_path`)
- `restrict_to_workspace` mode: denies filesystem escapes and shell access via SDK `can_use_tool` callback
- Metadata sanitization strips sensitive keys before runtime execution

### Observability
- `claudebot-gateway status` — queries live gateway HTTP health endpoint
- `claudebot-gateway channels status` — per-channel enabled/config/live state
- `GET /health` / `GET /ready` — HTTP health and readiness endpoints
- `GET /metrics` — runtime counters (queue depths, errors, due cron jobs)
- `--log-format json` — structured JSON logging for ELK/Loki

### CLI
```
claudebot-gateway gateway [--once] [--demo-text TEXT]
claudebot-gateway status
claudebot-gateway channels status
claudebot-gateway agent --prompt TEXT [--workspace NAME]
claudebot-gateway cron add --prompt TEXT --channel CH --destination DEST [--every N | --at TIME | --cron EXPR]
claudebot-gateway cron list
claudebot-gateway cron remove --job-id ID
claudebot-gateway validate
```

Global flags: `--verbose`, `--log-format text|json`

## Quick Start

### Prerequisites
- Python 3.12+
- `uv`

### Install and test

```bash
uv sync --dev
uv run pytest -q
uv run ruff check .
uv run mypy src tests
```

### Run gateway

```bash
uv run claudebot-gateway gateway
```

### One-shot smoke test

```bash
uv run claudebot-gateway gateway --once --demo-text "hello"
```

### Docker

```bash
docker build -t claudebot-gateway .
docker run -p 8787:8787 -v $(pwd)/workspaces:/app/workspaces claudebot-gateway
```

## Configuration

Place config at `.claudebot/config.json`:

```json
{
  "channels": {
    "telegram": {"enabled": true, "bot_token": "..."},
    "feishu": {"enabled": true, "app_id": "...", "app_secret": "...", "verify_token": "...", "encrypt_key": "..."}
  },
  "agent_runtime": {
    "claude": {
      "restrict_to_workspace": true,
      "session_persistence_enabled": true
    }
  },
  "rate_limit": {
    "max_requests_per_sender": 10,
    "window_seconds": 60
  },
  "health_http": {"enabled": true, "host": "127.0.0.1", "port": 8787},
  "heartbeat_interval_seconds": 300,
  "agent_turns_retention_days": 90
}
```

All fields optional with sensible defaults. Run `claudebot-gateway validate` to check config.

## Repository Structure

```
docs/                          PRD and planning docs
src/claudebot_gateway/         core gateway runtime and services
  agent_runtime/               provider-agnostic runtime + Claude SDK adapter
  channels/                    channel adapters (CLI, Telegram, Feishu, stubs)
  persistence/                 SQLite-backed store
  agent_runner.py              inbound processing + rate limiting
  cli.py                       CLI entry point and subcommands
  config.py                    configuration dataclasses and loading
  cron_service.py              cron scheduling with delivery retry
  health.py                    HTTP health/ready/metrics endpoints
  heartbeat_service.py         periodic heartbeat execution
  message_bus.py               bounded async message queues
  outbound_dispatcher.py       outbound delivery with error isolation
  rate_limiter.py              per-sender sliding window rate limiter
  runtime.py                   gateway app, workers, session context
  workspaces.py                workspace resolution and prompt composition
tests/                         unit and integration tests
```

## Remaining Roadmap

- Real Discord adapter (discord.py / nextcord)
- Real Slack adapter (Slack Bolt)
- Deeper Telegram reconnect lifecycle coverage
- Finer-grained tool permission controls
