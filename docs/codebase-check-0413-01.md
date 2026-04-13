# Project Roadmap: claudebot-gateway Next Steps 

## Context 

The claudebot-gateway has a solid foundation: 3 working channels (CLI, Telegram, Feishu), bounded async message bus, SQLite persistence,
cron/heartbeat services, rate limiting, session persistence, workspace management, health endpoints, and 22 test files. However, 3 channels 
 remain stubs, there's no CI/CD, no database migration system, and several PRD-specified features are incomplete. This plan identifies and
prioritizes the gaps. 

--- 
### P0 -- Critical / Spec'd but Missing 

P0-1: .env.example and environment variable documentation 

- What: Create .env.example documenting every env var the gateway reads. Currently env vars are scattered across channels (e.g. 
telegram.py:36 reads os.getenv) with no single reference. 
- Files: Create .env.example; update README.md Configuration section
- Complexity: Small | Dependencies: None

P0-2: Discord adapter (real implementation) [Skip]

- What: Replace 13-line stub at src/claudebot_gateway/channels/discord.py with real adapter using discord.py/nextcord. Follow 
Telegram/Feishu pattern: start()/stop()/_send_message()/health(), publish normalized inbound, handle reconnect. Add DiscordChannelConfig in 
 config.py. Wire in runtime.py _build_channels. 
- Files: Rewrite channels/discord.py; modify config.py, runtime.py; create tests/test_discord_channel.py
- Complexity: Medium | Dependencies: None 

P0-3: Slack adapter (real implementation) [Skip]

- What: Replace 13-line stub at src/claudebot_gateway/channels/slack.py with real adapter using Slack Bolt (Socket Mode). Same contract as
Telegram/Feishu. Add SlackChannelConfig with bot_token, app_token.
- Files: Rewrite channels/slack.py; modify config.py, runtime.py; create tests/test_slack_channel.py
- Complexity: Medium | Dependencies: None 

P0-4: Database migration system 

- What: Replace ad-hoc CREATE TABLE IF NOT EXISTS + _ensure_cron_jobs_columns() hack in sqlite_store.py with proper migration tracking
(schema_migrations table, numbered migration scripts, idempotent on startup). 
- Files: Modify persistence/sqlite_store.py; create persistence/migrations.py; update tests/test_sqlite_store_mappers.py
- Complexity: Medium | Dependencies: None (but do before adapter work that needs new tables)

--- 
### P1 -- High-Value Enhancements 

P1-1: Finer-grained tool permission controls

- What: Current restrict_to_workspace is binary -- deny all shell + restrict filesystem. Add per-tool allow/deny patterns, tool-specific
timeouts, allow specific shell commands. Config fields allowed_tools/disallowed_tools exist but are passed through without gateway
enforcement.
- Files: Modify agent_runtime/claude_adapter.py (_make_workspace_guard), config.py, agent_runner.py; update tests 
- Complexity: Medium | Dependencies: None 

P1-2: Telegram reconnect lifecycle hardening

- What: TelegramChannel relies on SDK's internal polling via start_polling. No reconnect loop if polling stops (network partition, API
outage). Add reconnect detection, exponential backoff, health signal exposure. Explicitly in README roadmap.
- Files: Modify channels/telegram.py, channel_manager.py; update tests/test_telegram_channel.py 
- Complexity: Medium | Dependencies: None 

P1-3: WhatsApp bridge adapter [Skip]

- What: PRD states "WhatsApp requires Node 20+ bridge." Replace stub with adapter that communicates with external Node.js bridge via
HTTP/WebSocket. Detect bridge availability, reconnect on failure, gracefully degrade when absent. 
- Files: Rewrite channels/whatsapp.py; modify config.py, runtime.py; create tests 
- Complexity: Large | Dependencies: P0-4 (if new persistence tables needed) 

P1-4: Dynamic config hot-reload 

- What: Config loaded once at startup (config.py load_gateway_config()). Changing settings requires full restart. Implement SIGHUP or 
file-watch reload for channel toggles, rate limits, allow-lists without dropping in-flight messages.
- Files: Modify config.py, runtime.py, cli.py; create tests/test_config_reload.py 
- Complexity: Large | Dependencies: None

P1-5: Multi-provider runtime support

- What: PRD mentions "LiteLLM-backed multi-provider client." Factory pattern in factory.py already supports extension. Add
OpenAI-compatible provider adapter. Config-driven selection.
- Files: Create agent_runtime/openai_adapter.py; modify factory.py, config.py; update tests 
- Complexity: Large | Dependencies: None

--- 
### P2 -- Quality / DevEx Improvements

P2-1: CI/CD pipeline (GitHub Actions) 

- What: Create .github/workflows/ci.yml running uv sync --dev, pytest -q, ruff check ., mypy src tests on push/PR. AGENTS.md section 8
mandates these checks. Currently no .github/ directory. 
- Files: Create .github/workflows/ci.yml; update README.md with CI badge
- Complexity: Small | Dependencies: None

P2-2: Channel adapter tests (for new adapters)

- What: When P0-2/P0-3 replace stubs, add proper tests following test_telegram_channel.py pattern (SDK loader injection, mock-based 
integration tests). 
- Files: Create test_discord_channel.py, test_slack_channel.py; extend test_channel_manager.py
- Complexity: Small (per adapter) | Dependencies: P0-2, P0-3

P2-3: Clean up stale examples 

- What: examples/channels/ references nanobot imports from previous project name. Update to current patterns or remove. 
- Files: Modify/remove examples/channels/base.py, telegram.py, feishu.py
- Complexity: Small | Dependencies: None

P2-4: Optional dependency groups in pyproject.toml

- What: Currently pyproject.toml has zero runtime dependencies. Channel SDKs installed ad-hoc. Add [discord], [slack], [telegram],
[feishu], [all] optional groups.
- Files: Modify pyproject.toml, README.md, Dockerfile 
- Complexity: Small | Dependencies: P0-2, P0-3

P2-5: Operational runbook 

- What: Create docs/OPERATIONS.md covering: startup errors, channel failure diagnosis via /health//metrics, structured log reading, cron
management, workspace configuration.
- Files: Create docs/OPERATIONS.md
- Complexity: Medium | Dependencies: None 

--- 
### P3 -- Future Considerations 

P3-1: Message queue backpressure and fairness 

- Per-chat fairness scheduling (round-robin), configurable backpressure strategies (drop-oldest vs reject-newest vs per-chat quota). PRD
raises this as an open question.
- Complexity: Large 

P3-2: Prometheus-compatible metrics 

- Replace JSON /metrics with Prometheus exposition format. Add histograms (latency), counters (errors by type), gauges (queue depths). PRD
lists optional metrics. 
- Complexity: Medium

P3-3: HTTP API for remote management

- Authenticated endpoints for prompt submission, agent turn queries, cron management (currently CLI-only). Enables dashboard UIs. 
- Complexity: Large 

P3-4: Multi-tenancy support 

- Per-tenant workspaces, rate limits, channel configs, session namespaces. PRD lists as non-goal but WorkspaceResolver partial foundation 
exists. 
- Complexity: Very Large

--- 
### Recommended Execution Order 

┌───────┬────────────────────┬────────────────────────────────────────────────────────────────────────────────┐ 
│ Phase │ Items│ Rationale│ 
├───────┼────────────────────┼────────────────────────────────────────────────────────────────────────────────┤ 
│ 1 │ P0-1 + P2-1 + P0-4 │ Small foundational work: env docs, CI, migration system -- unblocks everything │ 
├───────┼────────────────────┼────────────────────────────────────────────────────────────────────────────────┤ 
│ 2 │ P0-2 + P0-3│ Discord + Slack adapters in parallel (medium, independent) │ 
├───────┼────────────────────┼────────────────────────────────────────────────────────────────────────────────┤ 
│ 3 │ P1-1 + P1-2│ Tool permissions + Telegram hardening (medium, independent)│ 
├───────┼────────────────────┼────────────────────────────────────────────────────────────────────────────────┤ 
│ 4 │ P2-2 + P2-3 + P2-4 │ Adapter tests, examples cleanup, dependency groups (follow-up on Phase 2)│ 
├───────┼────────────────────┼────────────────────────────────────────────────────────────────────────────────┤ 
│ 5 │ P1-3 │ WhatsApp bridge (large, after migration system)│ 
├───────┼────────────────────┼────────────────────────────────────────────────────────────────────────────────┤ 
│ 6 │ P1-4 + P1-5│ Config hot-reload + multi-provider (large, independent)│ 
├───────┼────────────────────┼────────────────────────────────────────────────────────────────────────────────┤ 
│ 7 │ P2-5 │ Operations guide (documentation) │ 
├───────┼────────────────────┼────────────────────────────────────────────────────────────────────────────────┤ 
│ 8 │ P3 items │ As needed based on usage patterns│ 
└───────┴────────────────────┴────────────────────────────────────────────────────────────────────────────────┘ 

--- 
### Verification

After each phase, run the mandatory checks from AGENTS.md section 8:
uv run pytest -q
uv run ruff check . 
uv run mypy src tests 

For adapter work specifically:
- Test with --once --demo-text smoke test 
- Verify channel appears in channels status output
- Verify health endpoint reports channel state correctly 