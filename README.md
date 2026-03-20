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
- Harden remaining stub adapters (Discord, WhatsApp bridge, Slack bridge) into production-ready integrations.
- Continue Telegram hardening for deeper reconnect lifecycle/failure-mode coverage.
- Extend adapter health signals into richer unified channel resilience reporting.

### Agent integration
- Claude Agent SDK runtime orchestration is implemented through adapter/factory boundaries.
- Remaining work focuses on richer provider/tool-loop semantics and stronger delivery guarantees.

### Session management
- Read-only session persistence and resume-by-scope are implemented.
- Workspace prompt-file loading/composition for `SOUL.md` / `USER.md` / `TOOLS.md` is implemented.
- Remaining work is explicit policy controls for channel/session scope behavior.

### Scheduling
- `at` / `every` / cron-expression scheduling is implemented.
- Delivery retry handling is implemented.
- Remaining work is policy refinement for prolonged channel outages.

### Security and safety
- Sender allow-lists for inbound channels are implemented.
- Add workspace restriction policy wiring for filesystem/exec surfaces.
- Expand hardening for untrusted channel metadata and prompt-injection vectors.

### Observability and operations
- CLI status snapshots and optional HTTP health/readiness serving are implemented.
- Expand structured logs for reconnect attempts, cron outcomes, heartbeat outcomes, and latency/error signals.

## Repository Structure

```text
docs/                 PRD and planning docs
src/claudebot_gateway core gateway runtime and services
tests/                unit and integration tests
state/                local sqlite state (runtime artifact)
```
