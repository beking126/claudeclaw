# PRD + README Remaining Tasks Backlog (2026-03-19)

This backlog is derived directly from `docs/plans/2026-03-19-prd-readme-gap-report.md`.  
Each task maps to one or more gap IDs and represents remaining implementation work only.

## Priority and Dependency Order

1. T1, T2, T3, T4, T5 (P0)
2. T6, T7, T8, T9, T11, T12 (P1)
3. T10 (P2)

## Task List

## T1 — Replace cron/heartbeat noop path with runtime-backed execution

- Gap mapping: G4
- Priority: P0
- Goal: Ensure cron and heartbeat execute through the same agent runtime contract used by inbound message processing.
- Primary files to modify:
  - `src/claudebot_gateway/runtime.py`
  - `src/claudebot_gateway/cron_service.py`
  - `src/claudebot_gateway/heartbeat_service.py`
- Required tests:
  - `tests/test_e2e_gateway.py`
  - `tests/test_cron_service.py`
  - `tests/test_heartbeat_service.py`
  - `tests/test_runtime_lifecycle.py`
- Acceptance criteria:
  - Cron and heartbeat callbacks execute runtime-based agent requests, not `_noop_agent`.
  - Existing lifecycle semantics remain intact.
- Dependencies: none

## T2 — Extend cron model to support `at`, `every`, and cron expression schedules

- Gap mapping: G3
- Priority: P0
- Goal: Implement all required schedule kinds in service and persistence.
- Primary files to modify:
  - `src/claudebot_gateway/cron_service.py`
  - `src/claudebot_gateway/persistence/sqlite_store.py`
  - `src/claudebot_gateway/models.py` (if schedule typing is introduced)
- Required tests:
  - `tests/test_cron_service.py`
  - add/update persistence tests for schedule storage/query behavior
- Acceptance criteria:
  - One-shot, fixed-interval, and cron-expression jobs are supported and due-selection works correctly.
  - Backward compatibility for existing interval jobs is preserved.
- Dependencies: T1 recommended before final integration validation

## T3 — Add cron delivery retry strategy for transient channel-down failures

- Gap mapping: G5
- Priority: P0
- Goal: Prevent permanent delivery loss for transient send failures.
- Primary files to modify:
  - `src/claudebot_gateway/cron_service.py`
  - `src/claudebot_gateway/outbound_dispatcher.py` (if retry routing is centralized)
  - `src/claudebot_gateway/persistence/sqlite_store.py` (if retry metadata is persisted)
- Required tests:
  - `tests/test_cron_service.py`
  - `tests/test_e2e_gateway.py`
- Acceptance criteria:
  - Failed delivery attempts are retried under a defined policy.
  - Final run/delivery status is persisted with retry outcome.
- Dependencies: T2 if retry state is tied to extended schedule metadata

## T4 — Implement sender allow-lists and metadata hardening entry points

- Gap mapping: G8
- Priority: P0
- Goal: Enforce baseline inbound safety controls from PRD/README.
- Primary files to modify:
  - `src/claudebot_gateway/config.py`
  - `src/claudebot_gateway/agent_runner.py`
  - channel adapter modules under `src/claudebot_gateway/channels/`
- Required tests:
  - `tests/test_agent_dispatch_flow.py`
  - channel-focused tests (existing or new)
- Acceptance criteria:
  - Unknown senders are rejected when allow-list is configured.
  - Untrusted channel metadata is filtered/validated before prompt/runtime handoff.
- Dependencies: none

## [SKIP] T5 — Implement workspace restriction policy wiring for runtime/tool surfaces

- Gap mapping: G8
- Priority: P0
- Goal: Add enforceable workspace restriction behavior from configuration into runtime execution options.
- Primary files to modify:
  - `src/claudebot_gateway/config.py`
  - `src/claudebot_gateway/agent_runtime/claude_adapter.py`
  - `src/claudebot_gateway/runtime.py`
- Required tests:
  - `tests/test_agent_runtime.py`
  - `tests/test_cli_gateway.py`
- Acceptance criteria:
  - Restriction policy can be enabled/configured and is applied to runtime options.
  - Behavior is visible in tests without exposing secrets.
- Dependencies: none

## T6 — Add production adapters for Discord, Feishu, WhatsApp bridge, Slack bridge

- Gap mapping: G1
- Priority: P1
- Goal: Expand supported channels to match PRD/README planned set.
- Primary files to modify:
  - `src/claudebot_gateway/config.py`
  - `src/claudebot_gateway/runtime.py`
  - `src/claudebot_gateway/channels/` (new adapter modules)
  - `src/claudebot_gateway/channel_manager.py`
- Required tests:
  - `tests/test_channel_manager.py`
  - add adapter-specific tests
  - `tests/test_e2e_gateway.py`
- Acceptance criteria:
  - New channels can be enabled via config and participate in inbound/outbound flow.
  - Failure in one channel does not stop others.
- Dependencies: none

## T7 — Upgrade Telegram adapter to robust integration with reconnect/backoff signals

- Gap mapping: G2
- Priority: P1
- Goal: Replace scaffold behavior with resilient Telegram runtime behavior.
- Primary files to modify:
  - `src/claudebot_gateway/channels/telegram.py`
  - `src/claudebot_gateway/channel_manager.py`
  - logging points in runtime/channel modules
- Required tests:
  - telegram adapter tests (new)
  - `tests/test_channel_manager.py`
  - `tests/test_e2e_gateway.py`
- Acceptance criteria:
  - Telegram poll/send behavior is real (non-stub), with reconnect/backoff handling and observable logs.
- Dependencies: T6 recommended for shared adapter patterns

## T8 — Add CLI channel-status and cron management commands

- Gap mapping: G7
- Priority: P1
- Goal: Implement planned operational CLI workflows for channels and schedules.
- Primary files to modify:
  - `src/claudebot_gateway/cli.py`
  - `src/claudebot_gateway/cron_service.py`
  - supporting persistence/runtime modules as needed
- Required tests:
  - `tests/test_cli_gateway.py`
  - `tests/test_cron_service.py`
- Acceptance criteria:
  - CLI includes channel status and cron add/list/remove flows aligned with PRD UX.
  - Command output and exit behavior are test-covered.
- Dependencies: T2 for full schedule-kind support

## T9 — Add HTTP health/readiness serving mode

- Gap mapping: G6
- Priority: P1
- Goal: Expose machine-readable health/readiness endpoint when enabled.
- Primary files to modify:
  - `src/claudebot_gateway/health.py`
  - `src/claudebot_gateway/runtime.py`
  - config wiring in `src/claudebot_gateway/config.py` (if needed)
- Required tests:
  - `tests/test_health.py`
  - `tests/test_runtime_lifecycle.py`
- Acceptance criteria:
  - Enabling health HTTP starts a real server endpoint and returns runtime/worker signal status.
- Dependencies: none

## [SKIP] T10 — Add Docker runtime support artifacts

- Gap mapping: G9
- Priority: P2
- Goal: Provide a containerized execution path consistent with PRD portability.
- Primary files to modify/create:
  - `Dockerfile`
  - optional compose/run docs in `README.md`
- Required tests:
  - smoke validation script or CI check for container build/start
- Acceptance criteria:
  - Project can build and run gateway in Docker with documented command path.
- Dependencies: none

## T11 — Implement session persistence/context and workspace prompt-file loading

- Gap mapping: G10
- Priority: P1
- Goal: Add planned session-management capabilities across runtime and workspace context loading.
- Primary files to modify:
  - `src/claudebot_gateway/runtime.py`
  - `src/claudebot_gateway/agent_runtime/claude_adapter.py`
  - `src/claudebot_gateway/persistence/sqlite_store.py` (if session persistence schema is introduced)
  - `src/claudebot_gateway/workspaces.py`
- Required tests:
  - `tests/test_agent_runtime.py`
  - `tests/test_e2e_gateway.py`
  - new tests for workspace prompt-file loading behavior
- Acceptance criteria:
  - Session behavior is persisted and/or resumed according to configured scope.
  - Workspace prompt files (`SOUL.md`, `USER.md`, `TOOLS.md`) are discovered and applied in runtime prompt composition.
- Dependencies: T1 recommended

## T12 — Expand status introspection to include channel summaries and running state

- Gap mapping: G11
- Priority: P1
- Goal: Align status output with planned operational introspection scope.
- Primary files to modify:
  - `src/claudebot_gateway/runtime.py`
  - `src/claudebot_gateway/channel_manager.py`
  - `src/claudebot_gateway/cli.py`
  - `src/claudebot_gateway/health.py`
- Required tests:
  - `tests/test_cli_gateway.py`
  - `tests/test_health.py`
- Acceptance criteria:
  - Status output includes enabled channels/config summaries and runtime channel-running indicators.
  - Existing status fields remain available.
- Dependencies: T6 recommended for full multi-channel visibility

## Documentation Maintenance Tasks (derived from drift, non-feature)

- D-Task1 (from D1): Align `AGENTS.md` source-of-truth wording with chosen planning baseline (PRD + README) to prevent future planning drift.
- D-Task2 (from D2): Update README roadmap to reflect completed agent-runtime integration items and keep remaining roadmap items explicit.
