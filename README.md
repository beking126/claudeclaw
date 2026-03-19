# claudebot-gateway

Gateway daemon around a Claude-style agent runtime.  
This repository is currently in an active implementation phase with a working core runtime and a defined roadmap toward full PRD coverage.

## Current Implementation

### Runtime and lifecycle
- Long-running gateway runtime with supervised worker tasks and graceful stop/drain behavior.
- Inbound intake can be closed during shutdown to stop accepting new messages.
- Message bus provides bounded inbound/outbound queues.

### Messaging flow
- Channel polling worker, agent worker, and outbound dispatcher worker are wired through a shared async bus.
- Channel manager isolates individual channel poll failures so one channel does not crash the whole loop.
- Current channel adapters in tree: CLI and Telegram scaffolds.

### Cron and heartbeat
- Cron service supports persisted jobs with interval-based due execution.
- Cron runs and delivery outcomes are recorded in SQLite.
- Heartbeat service reads `workspaces/heartbeat/HEARTBEAT.md` and only triggers on actionable content.
- Last heartbeat run metadata is persisted in SQLite.

### Health, status, and logging
- `claudebot-gateway status` returns runtime and operational signals.
- Status includes worker/error state plus queue depths and due cron count.
- `--verbose` enables debug logging.
- Key paths are logged (workspace root, main workspace, sqlite path).

### Persistence
- SQLite-backed persistence currently includes:
  - channel identity registry,
  - cron runs,
  - deliveries,
  - cron jobs,
  - heartbeat runs.

### Test coverage snapshot
- Runtime lifecycle and shutdown semantics.
- Message bus capacity and intake closure behavior.
- Cron persistence and due execution behavior.
- Heartbeat actionable behavior and file-based sourcing.
- CLI status and verbose logging behavior.
- End-to-end flow across bus, agent runner, cron, and heartbeat.

## Quick Start

### Prerequisites
- Python 3.12+
- `uv`

### Install dependencies

```bash
uv sync --dev
```

### Run tests

```bash
uv run pytest -q
```

### Start gateway

```bash
uv run claudebot-gateway gateway
```

### Run one-shot smoke turn

```bash
uv run claudebot-gateway gateway --once --demo-text "hello"
```

### Check status (verbose)

```bash
uv run claudebot-gateway --verbose status
```

## Future Implementation (Roadmap)

The following items are planned to align fully with `docs/PRD_GATEWAY_DAEMON.md`.

### Channels and connectivity
- Add additional production-ready adapters (Discord, Feishu, WhatsApp bridge, Slack bridge).
- Improve Telegram from scaffold to fully robust integration.
- Add reconnect/backoff policies and channel-level resilience metrics.

### Agent integration
- Replace placeholder/default turn handling with full Claude Agent SDK orchestration.
- Integrate provider/tool loops, richer context composition, and stronger delivery semantics.

### Session management
- Add session state persistence per-channel or per-workspace.
- Extend session context to include channel-specific settings.
- Can load SOUL.md/USER.md/TOOLS.md files from workspace root. These files are used as System Prompt and User Prompt respectively.

### Scheduling
- Extend cron model to support:
  - one-shot `at`,
  - interval `every`,
  - cron expressions.
- Add stronger retry/handling strategy for channel-down delivery cases.

### Security and safety
- Enforce sender allow-lists for inbound channels.
- Add workspace restriction policy wiring for filesystem/exec surfaces.
- Expand hardening for untrusted channel metadata and prompt-injection vectors.

### Observability and operations
- Add richer health/liveness surfaces beyond CLI status snapshots.
- Expand structured logs for reconnect attempts, cron outcomes, heartbeat outcomes, and latency/error signals.
- Add optional HTTP health/readiness endpoint if adopted by runtime mode.

## Repository Structure

```text
docs/                 PRD and planning docs
src/claudebot_gateway core gateway runtime and services
tests/                unit and integration tests
state/                local sqlite state (runtime artifact)
```
