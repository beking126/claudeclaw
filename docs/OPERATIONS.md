# Operations Guide

## Quick Start

```bash
uv sync --dev
uv run claudebot-gateway gateway
```

For channel SDKs, install the optional groups you need:

```bash
uv sync --dev --extra telegram   # Telegram support
uv sync --dev --extra feishu     # Feishu/Lark support
uv sync --dev --extra all        # All channels
```

## Startup Errors

### "telegram bot token is not configured"
The Telegram channel is enabled in config but no token was provided. Either:
- Set `bot_token` in `channels.telegram` config section, or
- Set `CLAUDEBOT_TELEGRAM_BOT_TOKEN` or `TELEGRAM_BOT_TOKEN` environment variable, or
- Set `channels.telegram.enabled` to `false`

### "Feishu app_id and app_secret not configured"
The Feishu channel is enabled but credentials are missing. Set `app_id` and `app_secret` in `channels.feishu` config section, or disable the channel.

### "Claude runtime requires claude-agent-sdk"
The Claude Agent SDK is not installed. Install it following the Claude Code SDK documentation. Ensure `ANTHROPIC_API_KEY` is set in your environment.

### "Unsupported agent runtime provider '...'"
The `agent_runtime.provider` field in config must be `claude` (the only supported provider).

## Health Monitoring

### HTTP Endpoints

When `health_http.enabled` is `true` (default: `false`), the gateway exposes:

| Endpoint | Purpose |
|----------|---------|
| `GET /health` | Liveness check — returns `{"status": "ok"}` |
| `GET /ready` | Readiness check — includes channel states and queue depths |
| `GET /metrics` | Runtime counters — queue depths, error counts, due cron jobs |

### CLI Status

```bash
uv run claudebot-gateway status           # Gateway health snapshot
uv run claudebot-gateway channels status   # Per-channel enabled/config/live state
```

### Interpreting Channel Status

- **enabled**: Channel is toggled on in config
- **configured**: Required credentials are present
- **running**: Channel adapter is actively processing
- **degraded**: Channel started but encountered errors (check `last_error`)
- **stopped**: Channel is shut down

## Structured Logging

Enable JSON logging for ELK/Loki integration:

```bash
uv run claudebot-gateway gateway --log-format json
```

Log event names follow the pattern `component_action` (e.g., `agent_runner_inbound_received`, `telegram_connected`). All logs avoid exposing secrets — API keys and tokens are never included.

For verbose/debug output:

```bash
uv run claudebot-gateway gateway --verbose
```

## Cron Management

```bash
# Add recurring job (every 1 hour)
uv run claudebot-gateway cron add --every 3600 --prompt "Summarize recent events" --channel telegram --destination "chat:12345"

# Add one-shot job at specific time
uv run claudebot-gateway cron add --at "2026-05-01T09:00" --prompt "Morning briefing" --channel cli --destination "cli:stdout"

# Add cron expression job (every 5 minutes)
uv run claudebot-gateway cron add --cron "*/5 * * * *" --prompt "Check status" --channel cli --destination "cli:stdout"

# List jobs
uv run claudebot-gateway cron list

# Remove job
uv run claudebot-gateway cron remove --job-id <id>
```

Cron state persists in SQLite and survives daemon restarts. Failed deliveries are retried with exponential backoff.

## Workspace Configuration

Each workspace directory can contain prompt files that compose the agent's context:

| File | Purpose |
|------|---------|
| `SOUL.md` | Core personality and behavioral instructions |
| `USER.md` | User preferences and interaction style |
| `TOOLS.md` | Tool usage guidance and constraints |
| `AGENTS.md` | Multi-agent coordination rules |
| `MEMORY.md` | Persistent context and learned information |

The heartbeat workspace (`workspaces/heartbeat/`) uses `HEARTBEAT.md` for periodic proactive checks. Only non-empty, actionable content triggers agent execution.

## Session Persistence

Agent turns are stored in SQLite at the configured `sqlite_path` (default: `state/gateway.db`). Sessions automatically resume for the same workspace/channel/destination combination.

Old agent turns are automatically purged based on `agent_turns_retention_days` (default: 90).

## Rate Limiting

Configure per-sender rate limiting in config:

```json
{
  "rate_limit": {
    "max_requests_per_sender": 10,
    "window_seconds": 60
  }
}
```

When a sender exceeds the limit, they receive an immediate rejection message without consuming agent time. Set `max_requests_per_sender` to `0` (default) for unlimited.

## Tool Permissions

When `restrict_to_workspace` is enabled, the agent is sandboxed to the workspace directory. Fine-grained controls are available:

```json
{
  "agent_runtime": {
    "claude": {
      "restrict_to_workspace": true,
      "tool_permissions": {
        "allowed_shell_patterns": ["git status", "git log*", "ls *"],
        "denied_tools": ["NotebookEdit"],
        "allowed_tools": []
      }
    }
  }
}
```

- `allowed_shell_patterns`: Glob patterns for shell commands permitted under restriction
- `denied_tools`: Tool names always denied regardless of other settings
- `allowed_tools`: If non-empty, only these tools are permitted

## Docker Deployment

```bash
docker build -t claudebot-gateway .
docker run -p 8787:8787 \
  -v $(pwd)/workspaces:/app/workspaces \
  -v $(pwd)/state:/app/state \
  -e ANTHROPIC_API_KEY=... \
  claudebot-gateway
```

## Troubleshooting

### Messages not being processed
1. Check `claudebot-gateway status` for queue depths
2. Verify channel health with `channels status`
3. Check if rate limiting is rejecting senders
4. Review structured logs for `agent_runner_runtime_failed` events

### Telegram polling stopped
The gateway automatically detects polling failures and attempts reconnection with exponential backoff (up to 10 attempts, max 120s backoff). If reconnection fails, check:
- Network connectivity to Telegram API
- Bot token validity
- Structured logs for `telegram_reconnect_failed` events

### High memory usage
- Check inbound queue depth via `/metrics` — if consistently full, messages are being produced faster than consumed
- Reduce `heartbeat_interval_seconds` if heartbeat runs are accumulating
- Check `agent_turns_retention_days` — old turns may need earlier purging
