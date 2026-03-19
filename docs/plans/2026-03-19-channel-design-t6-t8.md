# Channel Design Rework for T6, T7, T8 (2026-03-19)

## Summary

This document redefines channel architecture for:
- T6: additional production adapters (Discord, WhatsApp bridge, Slack bridge)
- T7: robust Telegram integration with reconnect/backoff
- T8: Feishu production channel implementation (webhook/event path, outbound delivery, resilience)

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

## Feishu (T8)
- Implement Feishu as a first-class production channel using explicit adapter lifecycle (`start/stop/send/process_raw_message`).
- Prefer a webhook/event callback model for inbound communication and bridge validated events into `MessageBus`.
- Add event verification and replay-safe dedup strategy for message IDs.
- Add outbound send behavior with retry/backoff and health signals.

## Discord / Slack bridge / WhatsApp bridge (T6)
- Implement as separate adapters with same manager contract.
- WhatsApp remains bridge-driven; gateway must degrade gracefully when bridge unavailable.
- Keep platform-specific payload handling inside adapters; publish normalized inbound envelopes only.

## CLI Scope Adjustment

- `cli` channel is treated as a local/dev shim and not a production transport milestone target.
- T8 does not prioritize new CLI transport behavior.
- CLI may later gain a dedicated endpoint-backed transport mode, but this is outside current T8 scope.

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
  - config/runtime startup behavior remains stable.
- new Feishu-focused integration tests:
  - verified inbound event normalization into bus,
  - outbound delivery behavior with retry/backoff,
  - dedup behavior for repeated event IDs.

## Migration Plan (Execution Order)

1. Introduce new adapter protocol + ChannelManager lifecycle/status internals.
2. Add compatibility shim for existing poll-only adapters.
3. Implement robust Telegram adapter with reconnect/backoff.
4. Add Discord/Slack/WhatsApp bridge adapters behind config toggles.
5. Implement Feishu production channel (config surface, verification, inbound/outbound, resilience).
6. Remove deprecated poll-only manager path after adapter migration is complete.

## Non-Goals for This Design Slice

- No change to agent runtime provider abstraction.
- No change to message bus bounded queue policy.
- No change to T5 workspace-restriction scope (explicitly deferred).

## Implementation Targets (T6-T8)

- `src/claudebot_gateway/channels/` (new adapters + shared helper utilities)
- `src/claudebot_gateway/channel_manager.py` (lifecycle supervision and status)
- `src/claudebot_gateway/runtime.py` (adapter wiring and status integration)
- `src/claudebot_gateway/channels/feishu.py` (T8 production implementation)
- `src/claudebot_gateway/config.py` (Feishu config surface)
- `src/claudebot_gateway/runtime.py` (Feishu wiring and lifecycle integration)
- `src/claudebot_gateway/cli.py` (retain orchestration and config-loading support)
- `tests/test_channel_manager.py`
- adapter-specific test modules
- `tests/test_feishu_channel.py`
- `tests/test_cli_gateway.py`
- `tests/test_e2e_gateway.py`

## T8 Detailed Execution Plan (Feishu First)

### Task 1: Add Feishu config surface

**Files**
- Modify: `src/claudebot_gateway/config.py`
- Test: `tests/test_models_config.py`

**Steps**
1. Write failing test for `channels.feishu` config fields (`app_id`, `app_secret`, `verify_token`, `encrypt_key`, retry/backoff knobs).
2. Run targeted test and confirm failure due to missing fields.
3. Implement minimal `FeishuChannelConfig` dataclass and wire into `ChannelConfig`.
4. Run targeted test and confirm pass.

### Task 2: Wire runtime construction from config

**Files**
- Modify: `src/claudebot_gateway/runtime.py`
- Test: `tests/test_runtime_lifecycle.py`

**Steps**
1. Write failing test asserting Feishu adapter receives config values from `GatewayConfig`.
2. Run targeted test and confirm failure.
3. Update runtime Feishu adapter construction to pass explicit config values.
4. Run targeted test and confirm pass.

### Task 3: Implement Feishu adapter lifecycle and inbound normalization

**Files**
- Modify: `src/claudebot_gateway/channels/feishu.py`
- Create/Modify: `tests/test_feishu_channel.py`

**Steps**
1. Write failing tests for:
   - `start/stop/health` lifecycle state,
   - inbound webhook/event verification path,
   - inbound normalization to bus envelope (`channel`, `destination`, `text`, optional sender/metadata),
   - replay dedup by event/message id.
2. Run targeted tests and confirm failures.
3. Implement minimal adapter with:
   - lifecycle state tracking,
   - verification helpers,
   - `process_raw_message` normalization,
   - dedup cache strategy.
4. Re-run targeted tests and confirm pass.

### Task 4: Implement outbound send with resilience

**Files**
- Modify: `src/claudebot_gateway/channels/feishu.py`
- Modify: `tests/test_feishu_channel.py`

**Steps**
1. Write failing tests for outbound send success, retry/backoff behavior, and failure signaling (`last_error`, reconnect/send attempts).
2. Run targeted tests and confirm failures.
3. Implement outbound sender + retry/backoff loop using existing adapter conventions.
4. Re-run targeted tests and confirm pass.

### Task 5: Integrate with manager/status and regression suite

**Files**
- Modify: `tests/test_channel_manager.py`
- Modify: `tests/test_e2e_gateway.py`
- Modify: `tests/test_cli_gateway.py` (only if status output expectations change)

**Steps**
1. Add failing tests for Feishu enabled runtime path and degraded-state behavior isolation.
2. Run targeted tests and confirm failures.
3. Implement minimal integration glue (if any gaps remain after adapter/runtime changes).
4. Re-run targeted tests and confirm pass.

### Task 6: Final validation gate

**Steps**
1. Run focused test commands:
   - `uv run pytest -q tests/test_feishu_channel.py`
   - `uv run pytest -q tests/test_runtime_lifecycle.py tests/test_channel_manager.py`
2. Run regression command:
   - `uv run pytest -q tests/test_cli_gateway.py tests/test_models_config.py tests/test_agent_dispatch_flow.py tests/test_telegram_channel.py tests/test_e2e_gateway.py`
3. Run quality gates:
   - `uv run ruff check src tests`
   - `uv run mypy src tests`
4. Confirm diagnostics are clean before closing T8.

## T8 Acceptance Criteria (Updated)

- Feishu can be enabled and configured through `./claudebot/config.json` via `GatewayConfig`.
- Feishu adapter implements `start/stop/send/process_raw_message/health` and integrates with `ChannelManager`.
- Inbound Feishu events are verified, deduplicated, normalized, and published to `MessageBus`.
- Outbound Feishu sends retry transient failures with bounded backoff and expose clear health/error state.
- One Feishu channel failure does not crash runtime or other channels.
- Tests, lint, typecheck, and diagnostics are all green.
