# Gateway Next-Step Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Turn the current daemon into an operationally usable service by implementing durable scheduling, actionable heartbeat input, strict shutdown/drain semantics, and richer health/status output.

**Architecture:** Keep the existing `GatewayApp` composition model, but upgrade worker loops and persistence boundaries so each subsystem has explicit lifecycle and testable contracts. Drive all behavior changes through test-first iterations, then wire into runtime with small integration steps. Favor additive changes over large rewrites to preserve current passing behavior.

**Tech Stack:** Python 3.13, asyncio, pytest, mypy, ruff, SQLite persistence layer.

---

### Task 1: Heartbeat file ingestion and actionable triggering

**Files:**
- Modify: `src/claudebot_gateway/heartbeat_service.py`
- Modify: `src/claudebot_gateway/runtime.py`
- Test: `tests/test_heartbeat_service.py`
- Test: `tests/test_runtime_lifecycle.py`

**Step 1: Write failing unit tests for file-based heartbeat**
- Add tests asserting heartbeat reads from `workspace_root/heartbeat/HEARTBEAT.md`.
- Add tests asserting no outbound work when file is empty or whitespace.
- Add tests asserting actionable text triggers exactly one agent turn and persists timestamp.

**Step 2: Run targeted tests to verify RED**
- Run: `uv run pytest tests/test_heartbeat_service.py -v`
- Expected: failure showing missing file-read/actionability behavior.

**Step 3: Implement minimal heartbeat file-read behavior**
- Add helper to read heartbeat file from workspace resolver path.
- Preserve existing `run_once` contract while supporting empty/non-empty decision.
- Keep persistence writes unchanged except on actionable execution.

**Step 4: Integrate runtime heartbeat worker**
- Update runtime heartbeat worker to source text from heartbeat file each interval.
- Keep interval wait semantics; do not alter stop-event responsiveness.

**Step 5: Verify GREEN**
- Run: `uv run pytest tests/test_heartbeat_service.py tests/test_runtime_lifecycle.py -v`
- Expected: all newly added heartbeat tests pass.

---

### Task 2: Durable cron scheduler loop with persisted jobs

**Files:**
- Modify: `src/claudebot_gateway/persistence/sqlite_store.py`
- Modify: `src/claudebot_gateway/cron_service.py`
- Modify: `src/claudebot_gateway/runtime.py`
- Test: `tests/test_cron_service.py`
- Test: `tests/test_e2e_gateway.py`

**Step 1: Write failing persistence tests**
- Add tests for job definition CRUD and next-run persistence.
- Add restart-style test loading existing jobs from DB and resuming schedule state.

**Step 2: Run targeted tests to verify RED**
- Run: `uv run pytest tests/test_cron_service.py -v`
- Expected: failures on missing persisted job lifecycle.

**Step 3: Implement SQLite job metadata support**
- Add schema/table for cron job definitions and execution metadata.
- Implement minimal read/write APIs in store for scheduler consumption.

**Step 4: Implement scheduler polling loop**
- In `CronService`, add due-job detection and execution dispatch.
- Keep current `run_job_once` behavior as execution primitive.
- Ensure scheduler loop is idempotent and safe under repeated polling.

**Step 5: Wire runtime cron worker**
- Add cron worker in `GatewayApp` runtime workers.
- Ensure startup/shutdown follows same lifecycle semantics as other workers.

**Step 6: Verify GREEN**
- Run: `uv run pytest tests/test_cron_service.py tests/test_e2e_gateway.py -v`
- Expected: cron persistence and runtime integration tests pass.

---

### Task 3: Shutdown semantics for intake stop and in-flight drain

**Files:**
- Modify: `src/claudebot_gateway/message_bus.py`
- Modify: `src/claudebot_gateway/runtime.py`
- Test: `tests/test_runtime_lifecycle.py`
- Test: `tests/test_message_bus.py`

**Step 1: Write failing lifecycle tests**
- Add test proving inbound enqueue is rejected once shutdown begins.
- Add test proving already queued inbound/outbound messages are drained before stop completes.
- Add timeout-path test proving forced cancellation still yields consistent stopped state.

**Step 2: Run targeted tests to verify RED**
- Run: `uv run pytest tests/test_runtime_lifecycle.py tests/test_message_bus.py -v`
- Expected: failures around stop behavior and intake rejection.

**Step 3: Implement intake gate in message bus**
- Add shutdown gate state to block new inbound publish when closing.
- Keep queue behavior unchanged for pre-existing queued items.

**Step 4: Integrate runtime stop orchestration**
- Signal intake gate before setting stop event.
- Keep drain timeout and cancellation semantics compatible with existing tests.

**Step 5: Verify GREEN**
- Run: `uv run pytest tests/test_runtime_lifecycle.py tests/test_message_bus.py -v`
- Expected: all shutdown/drain tests pass.

---

### Task 4: Actionable health/status surface

**Files:**
- Modify: `src/claudebot_gateway/health.py`
- Modify: `src/claudebot_gateway/runtime.py`
- Modify: `src/claudebot_gateway/cli.py`
- Test: `tests/test_health.py`
- Test: `tests/test_cli_gateway.py`

**Step 1: Write failing output-contract tests**
- Add tests for health snapshot fields: loop liveness, queue depths, last heartbeat timestamp, cron due count.
- Add CLI status formatting tests for these fields.

**Step 2: Run targeted tests to verify RED**
- Run: `uv run pytest tests/test_health.py tests/test_cli_gateway.py -v`
- Expected: failures for missing fields/formatting.

**Step 3: Implement health enrichment**
- Extend runtime to expose worker/liveness counters and queue depth metrics.
- Extend health service snapshot with normalized operational fields.

**Step 4: Implement CLI status presentation**
- Update status formatter to include new health signal fields.
- Preserve backward-compatible status line prefix.

**Step 5: Verify GREEN**
- Run: `uv run pytest tests/test_health.py tests/test_cli_gateway.py -v`
- Expected: updated health/status tests pass.

---

### Task 5: Final hardening and verification gate

**Files:**
- Modify as needed from Tasks 1–4 only
- Test sweep: `tests/`

**Step 1: Run full test suite**
- Run: `uv run pytest -q`
- Expected: all tests pass.

**Step 2: Run static checks**
- Run: `uv run ruff check .`
- Run: `uv run mypy src`
- Expected: no lint/type errors.

**Step 3: Run executable smoke checks**
- Run: `uv run claudebot-gateway --verbose status`
- Run: `uv run claudebot-gateway gateway --once --demo-text "smoke"`
- Expected: command success with key-path logs and no crashes.

**Step 4: Validate no scope creep**
- Confirm no unrelated files changed beyond planned file set.
- Confirm behavior aligns with PRD priorities (heartbeat, cron, lifecycle, health).

---

## Execution Notes
- Follow strict TDD cycle per task: RED → GREEN → REFACTOR.
- Keep commits small and scoped to one task at a time.
- Do not introduce new external dependencies unless required by tests.
- Preserve existing CLI options and logging behavior (`--verbose`, key paths).
