# Gateway Daemon Design (Python-first, uv, Claude Agent SDK)

## 1. Scope and Goals

This design defines a long-running gateway daemon built with Python and managed by `uv`, centered on Claude Agent SDK execution.  
V1 scope:
- Runtime: always-on daemon with graceful startup/shutdown.
- Channels: CLI and Telegram.
- Services: message processing loop, cron scheduling, heartbeat checks.
- Isolation: workspace/session separation per source.
- Health: CLI status plus optional HTTP health endpoint behind a feature flag.

Out of scope for V1:
- Multi-tenant hosting.
- Distributed scheduling.
- HA clustering and leader election.

Primary references:
- [PRD_GATEWAY_DAEMON.md](file:///d:/Works/dev/vibe/claudeclaw/docs/PRD_GATEWAY_DAEMON.md)
- [claude-sdk-app-builder/SKILL.md](file:///d:/Works/dev/vibe/claudeclaw/.trae/skills/claude-sdk-app-builder/SKILL.md)

## 2. Architecture Overview

The daemon uses one asyncio process with a supervisor (`GatewayRuntime`) that owns all lifecycle operations.

### 2.1 Runtime Components

- ConfigLoader: loads instance and user configuration.
- WorkspaceResolver: resolves/sanitizes workspace keys and paths.
- IdentityRegistry: maps raw channel identifiers to canonical/sanitized keys.
- MessageBus: bounded inbound queue and outbound queue.
- AgentRunner: Claude Agent SDK execution wrapper.
- OutboundDispatcher: sends outbound payloads to channel adapters.
- ChannelManager: starts/stops adapters (CLI and Telegram in V1).
- CronService: persistent local scheduler and executor.
- HeartbeatService: periodic actionable check and trigger.
- HealthService:
  - CLI status (always enabled),
  - Optional HTTP `/healthz` (feature-flag controlled).

### 2.2 Process Model

- Single process, single event loop.
- Components run as supervised async tasks.
- Channel failures are isolated and must not terminate the process.
- Supervisor enforces ordered startup and shutdown.

## 3. Workspace and Session Isolation

Workspace root layout is fixed:

```text
workspaces/
  main/
  heartbeat/
  <channel_name>_<channel_id>/
  cron_<job_id>
```

Rules:
- `main` is used for web/CLI conversation context.
- `heartbeat` is dedicated to heartbeat turns.
- `<channel_name>_<channel_id>` is used for channel conversation threads.
- `cron_<job_id>` is used for cron job context and history.

### 3.1 Sanitization Contract

For `<channel_name>` and `<channel_id>`:
- Lowercase normalization.
- Allowed characters: `a-z`, `0-9`, `_`, `-`.
- All other characters map to `_`.
- Consecutive `_` collapse to one.
- Leading/trailing `_` are trimmed.
- Empty result after sanitization is rejected.

Sanitized path keys are deterministic but never considered the sole source of identity.

### 3.2 Identity Mapping

IdentityRegistry stores:
- `channel_type` (telegram, slack, feishu, ...).
- Raw provider IDs (chat, user, thread as applicable).
- Sanitized IDs used in workspace naming.
- Canonical source key for routing.
- Workspace key/path mapping.

This enables later channel expansion without changing daemon core contracts.

## 4. Data Flow

### 4.1 Inbound Path

1. Channel adapter receives inbound message/event.
2. Adapter resolves canonical source via IdentityRegistry.
3. WorkspaceResolver selects workspace path.
4. Adapter publishes `InboundMessage` to bounded queue.
5. If queue full: reject newest message and send busy response.

### 4.2 Agent Execution Path

1. AgentRunner consumes inbound event.
2. Loads relevant session/history from workspace.
3. Executes Claude Agent SDK turn.
4. Produces outbound payload(s) and tool effects.
5. Publishes `OutboundMessage` to outbound queue.

### 4.3 Outbound Path

1. OutboundDispatcher consumes outbound queue.
2. Routes by `OutboundMessage.channel`.
3. Sends to channel adapter destination.
4. On send failure:
   - user chat response: adapter/runtime error recorded, daemon continues;
   - cron delivery: immediate failure record and drop.

## 5. Scheduling and Heartbeat

### 5.1 Cron

Supported schedule kinds:
- one-shot (`at`)
- fixed interval (`every`)
- cron expression

Execution:
- Each run uses `cron_<job_id>` workspace/session.
- Run metadata and results are persisted.
- Optional delivery to selected channel/destination.
- If channel unavailable, V1 policy is: drop immediately and record failure.

### 5.2 Heartbeat

- Periodic interval scans actionable source in heartbeat workspace.
- If non-actionable, no agent turn executes.
- If actionable, executes a standard prompt in `heartbeat` workspace.
- Heartbeat runs are persisted for observability.

## 6. Backpressure, Fairness, and Reliability

- Inbound queue is bounded and monitored.
- Policy: reject newest when full and issue busy response.
- Daemon should never use unbounded queue growth.
- Channel adapter exceptions are isolated and logged.
- Provider/tool/channel errors return structured failures and never crash supervisor.
- Graceful shutdown includes bounded drain timeout and task cancellation.

## 7. Health and Observability

### 7.1 Health Signals

Mandatory liveness checks:
- daemon supervisor loop alive
- agent consumer loop alive
- outbound dispatcher loop alive

Optional checks:
- channel adapter status (running/degraded/offline)
- queue depths
- scheduler heartbeat timestamps

### 7.2 Surfaces

- CLI status command: always available.
- HTTP `/healthz`: enabled only when `health_http.enabled=true`.

### 7.3 Logging

Structured logs with component prefixes:
- `gateway.supervisor`
- `gateway.agent`
- `gateway.channels.<name>`
- `gateway.cron`
- `gateway.heartbeat`
- `gateway.dispatch`

Secrets are never logged.

## 8. Data Persistence Design

V1 persistence uses hybrid local storage:
- Filesystem for workspace/session artifacts.
- SQLite (WAL mode) for operational metadata.

### 8.1 Filesystem State

Under each workspace:
- session snapshots/checkpoints
- turn-level artifacts if needed
- optional local context files

Requirements:
- atomic writes (temp file + rename)
- crash-safe read on restart
- bounded retention for large logs/artifacts

### 8.2 SQLite Metadata

Recommended tables:

- `channel_identity`
  - canonical source key
  - channel type
  - raw provider identifiers
  - sanitized ids
  - workspace key/path
  - timestamps

- `cron_jobs`
  - job id
  - schedule kind/expression
  - prompt/config payload
  - delivery config (enabled/target)
  - enabled flag
  - created/updated timestamps

- `cron_runs`
  - run id
  - job id
  - triggered time
  - status (ok/error/skipped)
  - latency
  - workspace key
  - error details

- `deliveries`
  - delivery id
  - source type (cron/agent/system)
  - target channel/destination
  - status (ok/error/dropped)
  - failure reason
  - timestamp

- `heartbeat_runs`
  - run id
  - trigger time
  - actionable flag
  - status
  - error details
  - workspace key

### 8.3 Persistence Semantics

- Append-only for run/delivery history.
- Upsert for identity/job records.
- Startup recovery:
  - load jobs and schedule next runs,
  - rebuild health baselines from recent records.
- Shutdown:
  - flush pending state,
  - close DB cleanly.

### 8.4 Retention

- Configurable retention windows for run history.
- Periodic cleanup task to prevent indefinite growth.

## 9. Security and Safety

- Enforce workspace path sanitization and deny traversal.
- Reject unknown/unauthorized sender identities by channel allow-list policy.
- Treat channel metadata as untrusted input.
- Respect `restrict_to_workspace` tool constraints where configured.
- Avoid logging secrets, tokens, raw credentials.

## 10. Open Technical Choices for Implementation Phase

- Exact Claude Agent SDK session persistence API integration details.
- SQLite access layer (`sqlite3` vs async wrapper).
- HTTP health implementation (`aiohttp`/`fastapi`/stdlib) behind flag.
- Queue sizing defaults and telemetry thresholds.

## 11. Acceptance Alignment Matrix

- Telegram enabled: inbound/outbound end-to-end works.
- CLI enabled: local interactive message loop works in `main`.
- Cron run: executes in `cron_<job_id>` and persists run outcome.
- Heartbeat: only triggers on actionable content in `heartbeat`.
- Health: CLI status available; HTTP health optional via feature flag.
- Shutdown: no unhandled exceptions; tasks stopped and state flushed.

