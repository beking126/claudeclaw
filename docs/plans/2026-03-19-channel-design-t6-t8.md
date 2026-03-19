# Channel Design Rework for T6, T7, T8 (2026-03-19)

## Summary

This document redefines channel architecture for:
- T6: additional production adapters (Discord, Feishu, WhatsApp bridge, Slack bridge)
- T7: robust Telegram integration with reconnect/backoff
- T8: CLI channel-status and cron operations aligned with operational needs

T5 is intentionally deferred in this iteration.  
Design is grounded on current gateway runtime and external channel examples under `examples/channels/`.

## Current State and Gaps

## Current implementation shape
- Runtime creates channel instances and repeatedly calls `poll_once()` via `ChannelManager`.
- `ChannelManager` isolates poll errors per channel by returning per-channel booleans.
- `TelegramChannel` and `CliChannel` are scaffolds.
- Outbound routing uses adapter `send(message)` through `OutboundDispatcher`.

## Key limitations against T6-T8
- Poll-only adapter contract is too thin for production channels needing persistent connections.
- No unified channel lifecycle (`start/stop/health`) for long-running transports.
- No standardized reconnect/backoff policy surface.
- No channel status model for CLI introspection.
- Cron CLI operations are not integrated with channel-aware delivery/operator flows.

## External Example Insights (Applied, Not Copied)

From `examples/channels/base.py`, `telegram.py`, `feishu.py`:
- A base channel abstraction with explicit lifecycle methods is practical for real adapters.
- Channel-level allow-list checks and inbound normalization reduce risk early.
- Long-running channels commonly need:
  - persistent connections (polling/websocket/bridge session),
  - deduplication of inbound events,
  - graceful shutdown handling,
  - retry/backoff behavior for reconnect/send.

These patterns should be adapted to current gateway architecture without coupling to external packages or event classes.

## Proposed Architecture

## 1) New Channel Adapter Contract

Introduce a stronger internal protocol for adapters used by runtime/manager:
- `start() -> None` (async): initialize client and begin receive loop.
- `stop() -> None` (async): terminate connections and background tasks safely.
- `send(message: dict[str, str]) -> None` (async): outbound delivery.
- `health() -> dict[str, object]`: runtime-ready channel signals.
- `name` property: stable channel identifier.

Inbound publishing remains through `MessageBus`, but each adapter owns platform-specific receive loop and pushes normalized inbound envelopes to bus.

## 2) ChannelManager Rework

Replace single `poll_once_all()` orchestration with lifecycle supervision:
- `start_all()` launches each channel adapter and tracks task handles.
- `stop_all()` stops channels in bounded graceful order.
- Per-channel failure isolation:
  - one channel failure does not stop others,
  - failed channel enters reconnect workflow,
  - manager records status (`running`, `degraded`, `stopped`, `last_error`, `reconnect_attempts`).
- `status_snapshot()` returns structured summary for CLI and health/status reporting.

Backward compatibility path:
- keep existing poll-compatible behavior during transition with a small compatibility shim for adapters that still expose `poll_once`.

## 3) Standardized Inbound Envelope

Normalize channel inbound payloads before enqueue:
- required: `channel`, `destination`, `text`
- optional: `sender`, `workspace`, `metadata`

Metadata hardening remains in `AgentRunner` before runtime execution.  
Channel adapters should only include low-risk primitives in metadata and avoid secret-bearing headers/tokens.

## 4) Reconnect/Backoff Policy

Define shared policy used by production adapters (Telegram/Feishu/Discord/Slack/WhatsApp bridge):
- initial backoff, max backoff, jitter toggle
- reset backoff after sustained healthy period
- bounded retries per cycle with continuous service mode

Policy should be adapter-agnostic and reusable via a small utility module (for T6/T7).

## Channel-Specific Design Notes

## Telegram (T7)
- Move from scaffold to persistent polling adapter.
- Implement reconnect loop with shared backoff policy.
- Ensure outbound send path handles transient errors and reports metrics/status.
- Maintain message-to-destination mapping consistency for replies.

## Feishu (T6)
- Adopt websocket-style long connection pattern (as seen in external example) with thread-safe or async-safe bridging to bus.
- Add dedup strategy for message IDs to avoid duplicate processing on reconnect.

## Discord / Slack bridge / WhatsApp bridge (T6)
- Implement as separate adapters with same manager contract.
- WhatsApp remains bridge-driven; gateway must degrade gracefully when bridge unavailable.
- Keep platform-specific payload handling inside adapters; publish normalized inbound envelopes only.

## CLI Design for T8

## Channel status commands
- Add `channels status` style command under existing CLI namespace conventions.
- Output should include:
  - enabled channels,
  - running/degraded/stopped state,
  - last error (sanitized),
  - reconnect attempt counters.

## Cron management commands
- Add cron add/list/remove commands integrated with current `CronService` schedule model (`at`, `every`, `cron`).
- Validate channel/destination presence at command boundary.
- Keep command outputs deterministic and testable (stable text and exit codes).

## Data Flow

1. Adapter receives platform event.
2. Adapter normalizes inbound envelope and publishes to bus.
3. Agent runner processes inbound and publishes outbound.
4. Outbound dispatcher routes to adapter by `channel`.
5. Adapter sends outbound with its own transport retry/reconnect semantics.
6. Channel manager maintains lifecycle and status telemetry.

## Error Handling and Safety

- Channel receive failures: isolated per adapter, trigger reconnect workflow.
- Channel send failures: surfaced to logs/status and follow adapter retry policy.
- Unknown/unconfigured channels: outbound dispatcher continues without crashing runtime.
- All logs remain secret-safe.
- Inbound sender restrictions remain enforced in `AgentRunner` (already implemented in T4).

## Testing Strategy

## Unit tests
- `tests/test_channel_manager.py`
  - lifecycle start/stop orchestration,
  - failure isolation and reconnect state transitions,
  - status snapshot correctness.
- new adapter-specific tests under `tests/` for Telegram + each added adapter:
  - inbound normalization,
  - send behavior,
  - reconnect/backoff behavior,
  - dedup where relevant.

## Integration tests
- `tests/test_e2e_gateway.py`
  - multi-channel enabled runtime,
  - one channel failure does not break others,
  - status output reflects channel state.
- `tests/test_cli_gateway.py`
  - channel status commands,
  - cron add/list/remove commands and validation behavior.

## Migration Plan (Execution Order)

1. Introduce new adapter protocol + ChannelManager lifecycle/status internals.
2. Add compatibility shim for existing poll-only adapters.
3. Implement robust Telegram adapter with reconnect/backoff.
4. Add Feishu/Discord/Slack/WhatsApp bridge adapters behind config toggles.
5. Add CLI channel-status and cron management commands.
6. Remove deprecated poll-only manager path after adapter migration is complete.

## Non-Goals for This Design Slice

- No change to agent runtime provider abstraction.
- No change to message bus bounded queue policy.
- No change to T5 workspace-restriction scope (explicitly deferred).

## Implementation Targets (T6-T8)

- `src/claudebot_gateway/channels/` (new adapters + shared helper utilities)
- `src/claudebot_gateway/channel_manager.py` (lifecycle supervision and status)
- `src/claudebot_gateway/runtime.py` (adapter wiring and status integration)
- `src/claudebot_gateway/cli.py` (channels status + cron add/list/remove)
- `tests/test_channel_manager.py`
- adapter-specific test modules
- `tests/test_cli_gateway.py`
- `tests/test_e2e_gateway.py`
