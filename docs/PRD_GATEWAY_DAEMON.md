# PRD: Gateway Daemon (around `Claude Code Agent`)

## Summary
Build a long-running gateway daemon that wraps `Claude Code Agent` and provides a stable, always-on runtime for channel adapters (Telegram/Discord/Feishu/WhatsApp/Slack bridge), scheduled execution (cron), and periodic proactive checks (heartbeat). The daemon should be easy to start/stop, observable, resilient to transient failures, and safe by default.

This PRD describes product behavior and requirements; the current implementation basis is the `gateway` command in the CLI and the runtime components it composes.

## Goals
- Provide an always-on runtime that continuously processes inbound chat messages and returns replies.
- Run multiple channels concurrently and route outbound messages correctly.
- Run cron jobs and heartbeat checks in the same daemon lifecycle.
- Separated workspace for each channel/cron job to store session state (ref to Claude Agent SDK features).
- Recover from transient errors without manual restarts (network hiccups, channel reconnects, provider timeouts).
- Support graceful shutdown and clean task cancellation.
- Provide operational visibility (status, basic health, logs) without requiring deep debugging.

## Non-Goals
- Multi-tenant hosting and isolation across multiple users/organizations.
- High-availability clustering and leader election.
- A full HTTP API for third-party integrations (beyond what channels already provide).
- Persistent distributed job scheduling (cron is local-file backed only).
- Full secrets management solution beyond existing config file/env.

## Users / Personas
- **Personal operator**: runs claudebot on a laptop or home server; wants “set it and forget it”.
- **Developer/researcher**: iterates on tools/agent behavior; wants predictable lifecycle and debuggability.
- **Chat power-user**: uses Telegram/Discord/WhatsApp; expects fast responses and stable connectivity.

## Key User Stories
- As an operator, I can start the gateway and it stays running, reconnecting as needed.
- As an operator, I can stop the gateway and it shuts down cleanly without corrupting state.
- As a user, I can message from an enabled channel and receive a response with the correct routing.
- As an operator, I can schedule a reminder and have it delivered to a chosen channel.
- As a developer, I can see which channels are enabled/running and whether the agent loop is healthy.

## Product Scope
### In Scope
- `gateway` long-running mode.
- Channel orchestration and outbound dispatch loop.
- Agent processing loop for bus inbound queue.
- Cron scheduling and optional delivery of cron results.
- Heartbeat periodic check behavior.
- Local persistence of sessions and cron jobs.
- CLI interface for basic configuration and status monitoring.
- CLI as a channel to send/receive messages.
- Sample channel adapters (Start with ).

## Requirements
### Functional Requirements
#### FR-1: Daemon lifecycle
- Starting the daemon initializes configuration, message bus, provider, agent loop, cron service, heartbeat service, and channel manager.
- Daemon runs until interrupted or explicitly stopped.
- On shutdown:
  - stop accepting new inbound messages,
  - allow in-flight message processing to complete within a timeout,
  - cancel background tasks (channels, dispatch loop, timers),
  - flush session persistence to disk.

#### FR-2: Message routing
- Channels publish `InboundMessage` to the bus.
- `Claude Code Agent` consumes inbound messages, processes them, and emits `OutboundMessage`.
- Outbound dispatcher routes to exactly the channel named in `OutboundMessage.channel`.
- For “system” origin events (e.g., subagents), daemon must route responses back to the original channel/chat ID.

#### FR-3: Multi-channel concurrency
- Support enabling multiple channels at once via configuration.
- Each channel runs independently; failures in one channel do not stop others.
- Outbound dispatcher remains running even if a channel disconnects (it should log and continue).

#### FR-4: Scheduled execution (cron)
- Support schedules of kinds:
  - at (one-shot),
  - every (fixed interval),
  - cron expression.
- Cron jobs trigger agent execution using a deterministic session key namespace (e.g., `cron:<job_id>`).
- If a cron job is configured for delivery, it must publish an outbound message to a specified channel and destination.
- Cron state is persisted locally and survives daemon restarts.

#### FR-5: Heartbeat execution
- Heartbeat checks a workspace file (e.g., `HEARTBEAT.md`) at a fixed interval.
- If no actionable content exists, it should do nothing.
- If actionable content exists, it triggers a standard prompt to the agent.

#### FR-6: Status and introspection
- Provide CLI commands that show:
  - enabled channels and their configuration summaries,
  - whether channels are running,
  - number of scheduled cron jobs,
  - basic session info (optional).
- Provide a “health” concept:
  - daemon loop is alive,
  - agent loop is alive,
  - outbound dispatcher is alive.

### Non-Functional Requirements
#### NFR-1: Reliability
- No single failing channel can terminate the daemon.
- Transient provider/channel failures should be retried with backoff where appropriate.
- The daemon should be able to run for days without manual intervention.

#### NFR-2: Performance
- Default response latency is bounded by:
  - provider latency,
  - tool execution time,
  - queueing delay (should be minimal under typical load).
- Avoid unbounded memory growth:
  - sessions limit history passed into the model,
  - queues should be monitored for backpressure risks.

#### NFR-3: Observability
- Structured logs with clear component prefixes (agent, channels, cron, heartbeat).
- Log important lifecycle events:
  - startup configuration summary (without secrets),
  - channel start/stop and reconnect attempts,
  - cron execution start/end and failures,
  - heartbeat triggers and outcomes.

#### NFR-4: Security / Safety
- Never log API keys or secrets.
- Respect allow-lists for channels; reject messages from unknown senders.
- When `restrict_to_workspace` is enabled, filesystem and exec tools are restricted accordingly.
- Guard against prompt injection via channel metadata where possible (treat metadata as untrusted).

#### NFR-5: Portability
- Support local execution (Python) and Docker execution.
- WhatsApp functionality requires Node 20+ and bridge build; daemon should function without WhatsApp enabled.

## System Design (Conceptual)
### Components
- **Config**: loads user configuration (`~/.claudebot/config.json`).
- **MessageBus**: async inbound/outbound queues.
- **Claude Code Agent(s)**: consumes inbound, builds context, calls provider, executes tools, publishes outbound.
- **Provider**: LiteLLM-backed multi-provider client.
- **ToolRegistry + Tools**: filesystem, exec, web search/fetch, message, spawn, cron.
- **ChannelManager + Channels**: starts channel listeners, dispatches outbound messages.
- **CronService**: loads job store, schedules execution, calls agent via callback.
- **HeartbeatService**: periodic workspace check, calls agent via callback.

### Core Flow
1. Channel receives inbound message.
2. Channel publishes `InboundMessage` to the bus.
3. `Claude Code Agent` consumes inbound, runs an agent “turn”:
   - build context (history + memory + skills summary + user message),
   - call provider with tool schema,
   - execute tool calls until completion.
4. `Claude Code Agent` publishes `OutboundMessage`.
5. Outbound dispatcher sends via the channel named in the outbound message.

### Failure Handling
- Channel failure:
  - channel attempts reconnect internally or is restarted by the manager,
  - outbound dispatcher logs send failures and continues.
- Provider failure:
  - agent returns an error response message instead of crashing the daemon.
- Tool failure:
  - tool execution error returned as tool result string; agent can decide how to proceed.
- Cron failure:
  - mark job run status as error and persist it; continue scheduling future jobs as appropriate.

## Configuration
### Required
- Config file: `~/.claudebot/config.json` (user-level) and/or `./claudebot/config.json` (instance-level).

### Optional
- Enable channels:
  - `channels.telegram.enabled`
  - `channels.discord.enabled`
  - `channels.feishu.enabled`
  - `channels.whatsapp.enabled`
- `tools.restrict_to_workspace`: constrain file/exec access.
- `tools.exec.timeout`: max exec runtime.
- `tools.web.search.api_key`: Brave search key.

## CLI UX
- `claudebot gateway`: starts daemon.
  - `--port`: gateway port (reserved for future; current runtime is event-loop based).
  - `--verbose`: enable debug logging.
- `claudebot status`: show current config and readiness (if implemented).
- `bot channels status`: show enabled channels and key config.
- `claudebot cron add/list/remove`: manage schedules.

## Acceptance Criteria
- With Telegram enabled and configured, `claudebot gateway` accepts inbound Telegram messages and replies.
- With WhatsApp enabled:
  - if bridge is reachable, it connects and processes messages,
  - if bridge is unreachable, daemon keeps running and logs reconnect attempts.
- Cron job with `deliver=true` sends output to target channel and destination.
- Heartbeat does not spam; it only triggers when `HEARTBEAT.md` contains actionable content.
- Ctrl+C initiates graceful shutdown:
  - no unhandled exceptions,
  - channels stop,
  - agent loop stops,
  - cron/heartbeat stop.

## Metrics (Optional)
- Time to first response after startup.
- Average end-to-end message latency.
- Provider error rate and tool execution failure rate.
- Channel reconnect frequency.
- Queue sizes over time (inbound/outbound).

## Risks / Open Questions
- Backpressure policy: what to do if inbound queue grows (rate limiting, dropping, or scaling)?
- How to guarantee fairness across chats (avoid one chat starving others)?
- Delivery semantics for cron when a channel is temporarily down (retry vs drop)?
- Future gateway “port” usage: is an HTTP health endpoint desired, or keep CLI-only?
