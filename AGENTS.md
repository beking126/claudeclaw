# AGENTS.md

## 1) Source of Truth

- Planning/source-of-truth baseline:
  - `docs/PRD_GATEWAY_DAEMON.md` (primary product requirements)
  - `README.md` (current implementation overview and remaining roadmap)
- Current implementation evidence scope:
  - `src/claudebot_gateway/**`
  - `tests/**`
  - `pyproject.toml`

## 2) Runtime and Architecture Invariants

- Keep a provider-agnostic runtime contract and factory boundary:
  - Runtime consumers depend on `AgentRuntime` protocol, not concrete SDK classes.
  - Runtime selection is config-driven.
- Supported provider today: `claude`.
- Unknown provider behavior is fail-fast with clear configuration error.
- Gateway composition remains worker-based asyncio orchestration:
  - agent worker (consumes inbound, executes runtime, publishes outbound)
  - outbound dispatch worker (sends outbound via channel adapters)
  - cron worker (polls due jobs, executes agent, delivers results)
  - heartbeat worker (reads HEARTBEAT.md, executes agent, purges old turns)
- Message bus queues remain bounded and reject-newest when full for inbound try-publish paths.
- Shutdown semantics remain:
  - close inbound intake
  - set stop event
  - drain/cancel worker tasks within configured timeout

## 3) Claude Runtime Adapter Contract

- Claude execution is implemented through the runtime adapter, not directly from gateway/CLI.
- Adapter responsibilities:
  - Build SDK options from `ClaudeRuntimeOptions`.
  - Map `sub_agents` to SDK `agents`.
  - Pass workspace as `cwd`.
  - Preserve session-related settings (`continue_conversation`, `resume`, etc.).
  - When `restrict_to_workspace` is enabled, wire a `can_use_tool` callback that denies filesystem path escapes and shell access.
  - Return final text + metadata (`message_count`, session mode, and available result metadata).
- Query invocation must match SDK signature expectations (keyword arguments for `prompt` and `options`).
- Error handling rules:
  - Internal errors are logged with context.
  - External/user-facing errors are sanitized (no secret leakage).

## 4) Routing and Message Processing Rules

- Agent worker consumes inbound bus messages and produces outbound messages via runtime execution.
- Preserve inbound routing fields in outbound:
  - `channel` stays aligned with inbound channel
  - `destination` stays aligned with inbound destination
- On runtime failure, return safe fallback outbound text instead of crashing worker loops.
- Outbound dispatcher wraps each `adapter.send()` in try/except — a single channel failure does not crash the dispatch worker.
- Rate limiting: when configured, per-sender sliding-window check runs before runtime execution. Exceeded limits return an immediate rejection without consuming agent time.

## 5) CLI Contract

- Entry point remains:
  - script: `claudebot-gateway`
  - target: `claudebot_gateway.cli:main`
- Supported subcommands:
  - `gateway` — start daemon (`--once`, `--demo-text`)
  - `status` — query live gateway health endpoint (falls back to empty snapshot)
  - `agent` — execute single prompt (`--prompt`, `--workspace`)
  - `cron add/list/remove` — manage scheduled jobs (`--every`, `--at`, `--cron`)
  - `channels status` — show per-channel enabled/config/live state
  - `validate` — check config validity
- Global flags: `--verbose`, `--log-format text|json`
- `agent` command contract:
  - requires `--prompt`
  - default `--workspace-root` is `workspaces`
  - default `--workspace` is `main`
  - workspace path is validated against traversal
  - prints final response text to stdout
  - returns stable exit codes: `0` success, `1` failure, `130` keyboard interrupt
- Logging for CLI/runtime must include operational key paths and runtime provider, without exposing secrets.

## 6) Configuration Contract

- Python version floor: `>=3.12`.
- Config file: `.claudebot/config.json` (instance-level).
- Gateway config must continue to include:
  - `agent_runtime.provider` (default `claude`)
  - `agent_runtime.claude` options object (including `restrict_to_workspace`, `session_persistence_enabled`, `session_scope`)
  - channel toggles (CLI enabled by default; Telegram, Feishu with credentials; Discord/WhatsApp/Slack stubs)
  - message bus bounds
  - health HTTP toggle/options
  - heartbeat interval
  - sqlite path
  - `agent_turns_retention_days` (default 90)
  - `rate_limit.max_requests_per_sender` and `rate_limit.window_seconds` (default 0 = unlimited)
- Do not silently change defaults without corresponding spec/test updates.

## 7) Workspace and Persistence Constraints

- Workspace resolution is deterministic and sanitized through `WorkspaceResolver`.
- `validate_workspace_path()` prevents path traversal — used by `agent_runner.py`.
- Keep named workspaces and key-derived paths behavior intact (`main`, `heartbeat`, channel/cron scopes).
- Persist runtime data through existing SQLite-backed services and schema patterns.
- Agent turns table is periodically purged by the heartbeat worker based on `agent_turns_retention_days`.
- Single shared `SqliteStore` instance across GatewayApp, CronService, and HeartbeatService.

## 8) Testing and Verification Requirements

- Required baseline checks for runtime-related changes:
  - `uv run pytest -q`
  - `uv run ruff check .`
  - `uv run mypy src tests`
- Mandatory coverage areas (must stay green):
  - runtime factory selection + unknown provider rejection
  - Claude adapter option propagation and sanitized error mapping
  - workspace restriction guard (path escape denial, shell denial)
  - gateway routing through runtime abstraction
  - agent CLI default workspace and override behavior
  - cron expression parser (wildcard, step, range, list)
  - rate limiter sliding window behavior
- Running the gateway daemon:
  - `uv run claudebot-gateway gateway`
  - `uv run claudebot-gateway status`
- `agent` command:
  - `uv run claudebot-gateway agent --prompt "hello"`

## 9) Change Safety Rules

- Do not bypass runtime abstraction by calling SDK directly from unrelated modules.
- Do not replace bounded queues with unbounded structures.
- Do not alter shutdown ordering that protects graceful drain.
- Do not add undocumented providers, channels, or scheduling models without a spec update.
- Any contract change requires:
  - spec/task/checklist update
  - tests proving new behavior
  - preservation of existing verified behaviors unless intentionally superseded
