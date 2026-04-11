  A. Things to Fix (Bugs & Quality Issues)

  Critical

  1. Path traversal in workspace resolution — agent_runner.py:36 builds a Path directly from inbound workspace_raw with no validation. A crafted
  message could reference ../../etc or similar. The sanitize_workspace_token() function exists but isn't used here.
  2. CLI channel silently drops all messages — channels/cli.py does _ = message in send(). Outbound responses to CLI are lost. This is the default
  enabled channel.
  3. Dead models.py — WorkspaceKind, InboundMessage, OutboundMessage are defined but never imported anywhere. The codebase uses raw dict[str, Any]
  instead.
  4. Test suite hangs — run_once() has a hardcoded asyncio.sleep(50) which blocks tests. E2E tests never complete in reasonable time.

  Medium

  5. Inconsistent retry/backoff across channels — Telegram and Feishu have proper exponential backoff with configurable attempts. Discord, Slack,
  WhatsApp, and CLI have zero error handling (_ = message). One transient failure = lost message on those channels.
  6. _sanitize_metadata is shallow — It strips keys containing sensitive tokens, but passes through arbitrary string/int/float values without depth
  checking. Nested dicts or lists with malicious content get silently dropped (not an error, but also not flagged).

  ---
  B. PRD Gaps (Specified but Not Done)

  ┌───────────────────────────────────────┬─────────┬───────────────────────────────────────────────────────────────────────────────────────────┐
  │            PRD Requirement            │ Status  │                                      What's Missing                                       │
  ├───────────────────────────────────────┼─────────┼───────────────────────────────────────────────────────────────────────────────────────────┤
  │ FR-4: at one-shot schedules           │ Partial │ schedule_kind="at" deletes after run but has no dedicated tests or CLI surface            │
  ├───────────────────────────────────────┼─────────┼───────────────────────────────────────────────────────────────────────────────────────────┤
  │ FR-4: cron expression schedules       │ Partial │ Parser exists but only handles *, */N, and exact values. No ranges (1-5), lists (1,3,5),  │
  │                                       │         │ or L/W modifiers                                                                          │
  ├───────────────────────────────────────┼─────────┼───────────────────────────────────────────────────────────────────────────────────────────┤
  │ FR-6: Channel config summaries in     │ Missing │ status only shows queue depths + runtime state. No per-channel config or health           │
  │ status                                │         │                                                                                           │
  ├───────────────────────────────────────┼─────────┼───────────────────────────────────────────────────────────────────────────────────────────┤
  │ FR-6: bot channels status command     │ Missing │ Not implemented at all                                                                    │
  ├───────────────────────────────────────┼─────────┼───────────────────────────────────────────────────────────────────────────────────────────┤
  │ FR-6: claudebot cron add/list/remove  │ Missing │ No CLI to manage cron jobs — only programmatic API exists                                 │
  ├───────────────────────────────────────┼─────────┼───────────────────────────────────────────────────────────────────────────────────────────┤
  │ NFR-4: restrict_to_workspace          │ Missing │ Config field doesn't exist. No filesystem/exec tool restriction wiring                    │
  │ enforcement                           │         │                                                                                           │
  ├───────────────────────────────────────┼─────────┼───────────────────────────────────────────────────────────────────────────────────────────┤
  │ Config: tools.exec.timeout            │ Missing │ Not in config or runtime                                                                  │
  ├───────────────────────────────────────┼─────────┼───────────────────────────────────────────────────────────────────────────────────────────┤
  │ Config: tools.web.search.api_key      │ Missing │ Not in config or runtime                                                                  │
  └───────────────────────────────────────┴─────────┴───────────────────────────────────────────────────────────────────────────────────────────┘

  ---
  C. Feature Extension Suggestions

  Here are concrete directions, roughly ordered by impact:

  Tier 1 — Make the existing system production-ready

  1. Make CLI channel actually work — Print responses to stdout (or write to a named pipe). This is the easiest channel to test end-to-end and would
   make --once --demo-text useful.
  2. Add cron CLI commands — cron add --every 3600 --prompt "..." --channel telegram --destination "chat:123", cron list, cron remove <id>. This is
  the only way to manage schedules without writing code.
  3. Add channel status to status output — Show which channels are enabled, their state (running/stopped/degraded), and last error. The data already
   exists in ChannelManager.status_snapshot() but isn't wired into HealthService.
  4. Harden workspace resolution — Use sanitize_workspace_token() in agent_runner.py and validate that resolved paths stay within the workspace
  root. Add a resolve() that checks path.is_relative_to(root).
  5. Replace models.py types with actual dataclasses — Either use InboundMessage/OutboundMessage throughout the codebase (replacing raw dicts) or
  delete the file. Raw dicts are a source of typos and missing-field bugs.

  Tier 2 — New capabilities

  6. [Low Priority] Discord adapter — Using discord.py or nextcord. Most of the channel interface is already defined (start, stop, poll_once, send). Telegram and
  Feishu are the reference implementations.
  7. [Low Priority] Slack adapter — Using Slack Bolt (slack_bolt + slack_sdk). Similar pattern to Telegram: webhook or WebSocket-based event consumption + REST API
   for sending.
  8. Message history / conversation context — Persist per-session message history in SQLite and inject it as context before each agent turn. The
  agent_turns table already stores prompts and responses but nothing reads them back for context injection.
  9. Rate limiting and backpressure — The PRD calls this out as an open question. Options: per-channel rate limit, per-sender rate limit, or
  queue-depth-based rejection (partially exists via try_publish_inbound).
  10. Tool registry — The PRD mentions ToolRegistry + Tools: filesystem, exec, web search/fetch, message, spawn, cron. Currently tools are
  configured as strings in ClaudeRuntimeOptions.tools but there's no validation or discovery mechanism.

  Tier 3 — Polish and operations

  11. Metrics endpoint — Extend the HTTP health server with a /metrics path that exposes counters (messages processed, errors, latency histogram,
  queue depths over time). Could be Prometheus-compatible or simple JSON.
  12. Config validation — Add a config validate CLI command that checks: required fields present, tokens are non-empty, paths are writable, channel
  configs are consistent. Fail fast before starting the daemon.
  13. Docker support — Add a Dockerfile and docker-compose.yml. The app is already stateless-ish (just SQLite + workspace files), making
  containerization straightforward.
  14. Structured logging with JSON option — Add --log-format json for machine-parseable logs. Useful for shipping to ELK/Grafana Loki.

  ---
  D. Recommended Next Session

  If I were picking up where you left off, I'd suggest this order:

  1. Fix the CLI channel (make send() actually print) — smallest change, biggest immediate payoff
  2. Fix the path traversal bug — security issue
  3. Wire ChannelManager.status_snapshot() into status output — already have the data
  4. Add cron add/list/remove CLI commands — unlocks scheduled execution
  5. Clean up or adopt models.py types — reduce dict-typing bugs