# Initial Deployment Baseline Code Simplification Spec (2026-03-20)

## Goal

Define a safe, staged simplification plan for the current Python gateway codebase that reduces unnecessary indirection and duplication without changing externally visible behavior.

## Baseline and Constraints

- Source-of-truth baseline remains:
  - `docs/PRD_GATEWAY_DAEMON.md`
  - `README.md` roadmap section
- Runtime abstraction is preserved:
  - consumers depend on `AgentRuntime` protocol
  - provider selection remains config-driven
  - unknown provider remains fail-fast
- Gateway architecture invariants are preserved:
  - bounded inbound/outbound queues
  - worker-based orchestration model
  - graceful shutdown sequence (close inbound, stop event, drain/cancel)
- CLI contract is preserved:
  - commands: `gateway`, `status`, `agent`
  - stable exit codes and workspace behavior
- This spec is scoped as Initial Deployment Baseline hardening and simplification only, not feature expansion.

## Scope

In scope:
- Simplify pass-through wrappers and duplicate scaffolding.
- Consolidate repeated orchestration/config parsing patterns.
- Remove dead or near-dead complexity where behavior is provably unchanged.
- Keep tests/lint/type gates green throughout each simplification task.

Out of scope:
- New channels/providers/scheduling models.
- Message bus policy changes.
- Runtime-provider API contract changes.
- Architectural rewrites across unrelated modules.

## Complexity Findings

### High Priority

1) Outbound dispatcher pass-through layer
- File: `src/claudebot_gateway/outbound_dispatcher.py`
- Observation: logic is a thin loop around adapter `send`, and runtime wraps this again.
- Simplification: inline dispatch loop into runtime worker path and remove extra layer.
- Risk: Low if outbound routing and unknown-channel handling tests stay unchanged.

2) Session runtime reconstructed repeatedly
- File: `src/claudebot_gateway/runtime.py`
- Observation: `SessionContextRuntime` is created at app init and then recreated in execute paths.
- Simplification: reuse single instance where no mutable per-call state exists.
- Risk: Low/Medium; verify session persistence and resume behavior remains identical.

3) Duplicate no-op channel adapters
- Files: `channels/cli.py`, `channels/discord.py`, `channels/slack.py`, `channels/whatsapp.py`
- Observation: multiple identical no-op classes.
- Simplification: one shared no-op adapter class with lightweight aliases/import surface.
- Risk: Low; ensure runtime/channel wiring tests still pass.

### Medium Priority

4) Repeated channel config loading blocks
- File: `src/claudebot_gateway/config.py`
- Observation: repetitive manual field mapping per channel.
- Simplification: table-driven loading for repeated patterns while preserving defaults.
- Risk: Medium; verify default values and parsing behavior.

5) Repeated sender allow-list extraction
- File: `src/claudebot_gateway/runtime.py`
- Observation: repeated channel-specific blocks that differ only by field path.
- Simplification: iterate over declarative channel descriptors.
- Risk: Low.

6) CLI command branch duplication
- File: `src/claudebot_gateway/cli.py`
- Observation: repeated app bootstrap/config-load/logging logic.
- Simplification: extract shared command bootstrap helper(s).
- Risk: Low.

### Low Priority

7) Typed message model drift
- File: `src/claudebot_gateway/models.py`
- Observation: typed models appear weakly used compared with dict-based runtime flow.
- Simplification: either remove unused model types or make their usage explicit.
- Risk: Medium; verify no latent imports/use.

8) Small duplicated row-normalization helpers
- Files: `cron_service.py`, `heartbeat_service.py`
- Observation: duplicate conversions from DB rows.
- Simplification: shared local utility.
- Risk: Low.

## Simplification Principles

- Prefer deletion over abstraction expansion.
- Keep behavior unchanged unless a test-backed bug requires correction.
- Preserve boundaries that encode domain constraints or security.
- Apply Rule of Three before introducing generic extension points.
- Keep control flow explicit and linear in worker orchestration.

## Execution Plan (Staged)

### Stage 1: Low-risk structural cleanup

1. Consolidate duplicate no-op channel adapters.
2. De-duplicate row-normalization helper logic.
3. Extract shared CLI bootstrap utilities without command behavior change.

Gate:
- Targeted tests for channels, CLI, and e2e route baseline.

### Stage 2: Runtime simplification with contract preservation

1. Reuse `SessionContextRuntime` instance.
2. Simplify sender allow-list extraction through descriptor iteration.
3. Inline or collapse outbound dispatch wrapper.

Gate:
- Runtime lifecycle, session persistence, agent dispatch flow tests.

### Stage 3: Config surface simplification

1. Replace repetitive channel config parsing with table-driven mapping.
2. Preserve exact defaults and optionality.

Gate:
- Config model tests and CLI startup tests.

### Stage 4: Optional dead-code reduction

1. Verify usage of `models.py` typed message structures.
2. Remove only if no runtime/test dependency exists.

Gate:
- Full test suite + static checks.

## Verification Requirements

Mandatory validation commands after each completed stage:

- `uv run pytest -q`
- `uv run ruff check .`
- `uv run mypy src tests`

Additional targeted checks per stage:
- Dispatch/routing: `tests/test_agent_dispatch_flow.py`
- Runtime lifecycle/session: `tests/test_runtime_lifecycle.py`, `tests/test_session_persistence.py`
- Config/CLI: `tests/test_models_config.py`, `tests/test_cli_gateway.py`
- Channels/e2e: `tests/test_channel_manager.py`, `tests/test_e2e_gateway.py`

## Acceptance Criteria

- All simplification changes preserve current external contracts and runtime invariants.
- Test, lint, and type-check suites remain green.
- No new providers/channels/queue/shutdown model changes introduced.
- Codebase has measurably fewer pass-through layers and duplicated scaffolding in targeted areas.

## Deliverables

- This baseline simplification spec document.
- Follow-up task plan document (optional) can decompose each stage into TDD-ready steps.
