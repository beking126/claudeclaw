# Code Simplification Specification (Initial Deployment Baseline)

## Context

This repository already has a deployable initial gateway runtime with working CLI, runtime orchestration, channel adapters, persistence, cron, heartbeat, and tests.

The goal of this spec is to simplify code structure and reduce maintenance complexity while preserving current behavior and contracts.

## Scope

- In scope:
  - Structural simplification and deduplication in existing modules.
  - Clarity-oriented refactors that keep runtime behavior unchanged.
  - Test simplification that preserves current coverage intent.
- Out of scope:
  - Feature upgrades.
  - Provider/channel capability expansion.
  - Migration or backward-compatibility upgrade work.
  - Changes to required runtime invariants defined in `AGENTS.md`.

## Constraints and Invariants

- Keep runtime abstraction boundary intact (`AgentRuntime` protocol + factory).
- Keep supported provider set unchanged (`claude` only).
- Preserve bounded message bus behavior and shutdown ordering semantics.
- Preserve routing correctness (`channel` and `destination` continuity).
- Preserve CLI contract and stable exit codes.
- Never expose secrets in logs/errors.

## Current Complexity Baseline

### 1) Composition Concentration in `runtime.py`

- `GatewayApp.__init__` currently handles:
  - Runtime/persistence/workspace setup.
  - Channel construction and registration.
  - Sender allow-list extraction.
  - Worker/service composition.
- Result: high constructor surface area and elevated change risk.

### 2) Channel and Config Duplication

- Channel construction repeats per-channel conditional blocks.
- Allowed-sender extraction repeats near-identical set-building logic.
- Channel config parsing (Telegram/Feishu) duplicates parsing patterns.

### 3) Lifecycle and Mapping Repetition

- `ChannelManager` repeats similar error/status lifecycle patterns in `start_all`, `stop_all`, `poll_once_all`.
- `SqliteStore` uses repeated row-to-dict transformation patterns across retrieval methods.

### 4) Test Boilerplate

- Repeated fake runtime/app setup code across runtime/CLI tests.
- Exception assertion style can be standardized and simplified.

## Simplification Objectives

- Reduce duplicate logic without changing behavior.
- Make composition boundaries explicit and testable.
- Standardize parsing and lifecycle execution helpers.
- Shrink test boilerplate while preserving scenario coverage.
- Keep refactors incremental and reversible.

## Target Design

### A) Runtime Composition Decomposition

Introduce internal builder helpers in `runtime.py`:

- `_build_channels(...) -> tuple[dict[str, Any], dict[str, Any]]`
- `_build_allowed_senders(...) -> dict[str, set[str]]`
- `_build_services(...) -> tuple[AgentRunner, OutboundDispatcher, CronService, HeartbeatService, GatewayRuntime, HealthService]`

Requirements:

- No change in enabled-channel behavior.
- No change in worker list ordering.
- No change in health signal composition.

### B) Channel/Config Parsing Normalization

In `config.py`, introduce generic update helpers:

- `_read_int`, `_read_float`, `_read_str` typed extractors.
- `_apply_retry_backoff_fields(...)` shared handler.
- Optional channel-specific patch callbacks for unique credentials.

Requirements:

- Retain current defaults exactly.
- Ignore unknown/malformed fields as today.
- Preserve toggle and allow-list semantics.

### C) Channel Manager Lifecycle Consolidation

In `channel_manager.py`, centralize operation execution:

- `_run_op(name, channel, method_name, on_success_state, count_reconnect_on_error)` internal helper.
- `start_all`, `stop_all`, `poll_once_all` delegate to one execution path.

Requirements:

- Preserve status transitions (`running`, `stopped`, `degraded`).
- Preserve reconnect attempt increments for start/poll errors.

### D) Persistence Mapping Cleanup

In `persistence/sqlite_store.py`, add focused row mapping helpers:

- `_row_to_delivery(...)`
- `_row_to_cron_job(...)`
- `_row_to_heartbeat_run(...)`
- `_row_to_agent_session(...)`
- `_row_to_agent_turn(...)`

Requirements:

- Keep query SQL and schema unchanged.
- Keep returned key names unchanged.

### E) Test Suite Simplification

Refactor tests with shared fixtures/utilities:

- Shared fake runtime/adapter fixture factory.
- Shared app bootstrap helper for CLI/runtime tests.
- Replace manual exception assertion patterns with `pytest.raises` where equivalent.

Requirements:

- Maintain existing behavioral assertions.
- No reduction in covered scenarios from current baseline.

## Implementation Plan (No Feature Upgrades)

### Phase 1: Low-Risk Internal Deduplication

- `channel_manager.py`: operation helper extraction.
- `config.py`: typed reader and retry/backoff parser helpers.
- `tests/`: exception style cleanup and fixture introduction.

Acceptance:

- Existing tests pass without expected-output changes.
- No public interface changes.

### Phase 2: Runtime Composition Refactor

- `runtime.py`: constructor decomposition into focused builders.
- Keep existing constructor call path and object graph identical.

Acceptance:

- Runtime lifecycle tests pass unchanged.
- Status and routing behavior remain identical.

### Phase 3: Persistence Mapper Consolidation

- `sqlite_store.py`: row mapping helper extraction.

Acceptance:

- Persistence tests and runtime integration tests remain green.
- Returned data shape remains stable.

## Verification Strategy

Mandatory verification commands after each phase:

- `uv run pytest -q`
- `uv run ruff check .`
- `uv run mypy src tests`

Focused regression checks:

- Runtime factory selection + unknown provider rejection.
- Claude adapter option propagation and sanitized error mapping.
- Gateway routing through runtime abstraction.
- `agent` CLI default and override workspace behavior.

## Risks and Mitigations

- Risk: behavior drift during deduplication.
  - Mitigation: phase-gated refactors with mandatory baseline checks each phase.
- Risk: accidental contract drift in returned persistence shapes.
  - Mitigation: preserve key names and add targeted assertions where missing.
- Risk: hidden coupling in runtime constructor.
  - Mitigation: builder extraction without changing call order or side effects.

## Definition of Done

- All simplification phases completed with no feature additions.
- Baseline verification commands pass.
- Runtime/channel/CLI/persistence contracts remain unchanged.
- Code complexity is reduced in identified hotspots with measurable duplication removal.
