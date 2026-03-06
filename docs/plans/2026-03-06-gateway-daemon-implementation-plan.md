# Gateway Daemon Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a Python-first `uv`-managed gateway daemon around Claude Agent SDK with CLI+Telegram channels, cron, heartbeat, isolated workspaces, bounded backpressure, and local persistence.

**Architecture:** A single asyncio supervisor process coordinates channel adapters, message bus, agent execution, scheduler, heartbeat, and outbound dispatch. Workspace/session state is partitioned by source under deterministic sanitized paths. Metadata and operational history are persisted in local SQLite; workspace artifacts live on filesystem.

**Tech Stack:** Python 3.12+, uv, Claude Agent SDK (Python), asyncio, sqlite3, pytest, ruff, mypy (or pyright), optional aiohttp/fastapi for feature-flagged health endpoint.

---

## Preconditions

- Repository root: `d:\Works\dev\vibe\claudeclaw`
- Existing PRD: `docs/PRD_GATEWAY_DAEMON.md`
- Design doc: `docs/plans/2026-03-06-gateway-daemon-design.md`
- Use `uv` for env/dependency management and command execution.

## Proposed File Layout

Planned paths for implementation:

- `pyproject.toml`
- `src/claudebot_gateway/__init__.py`
- `src/claudebot_gateway/runtime.py`
- `src/claudebot_gateway/config.py`
- `src/claudebot_gateway/models.py`
- `src/claudebot_gateway/workspaces.py`
- `src/claudebot_gateway/identity_registry.py`
- `src/claudebot_gateway/message_bus.py`
- `src/claudebot_gateway/agent_runner.py`
- `src/claudebot_gateway/outbound_dispatcher.py`
- `src/claudebot_gateway/channel_manager.py`
- `src/claudebot_gateway/channels/cli.py`
- `src/claudebot_gateway/channels/telegram.py`
- `src/claudebot_gateway/cron_service.py`
- `src/claudebot_gateway/heartbeat_service.py`
- `src/claudebot_gateway/persistence/sqlite_store.py`
- `src/claudebot_gateway/health.py`
- `src/claudebot_gateway/cli.py`
- `tests/...` mirrored by module

## Task 1: Bootstrap Python Project with uv

**Files:**
- Create: `pyproject.toml`
- Create: `src/claudebot_gateway/__init__.py`
- Create: `src/claudebot_gateway/cli.py`
- Create: `tests/test_smoke.py`

**Step 1: Write the failing test**

```python
def test_package_imports():
    import claudebot_gateway  # noqa: F401
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_smoke.py -v`  
Expected: FAIL with `ModuleNotFoundError` or missing package path.

**Step 3: Write minimal implementation**

- Add package init file.
- Add minimal CLI entrypoint callable.
- Configure `pyproject.toml` with scripts and test/lint/typecheck commands.

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_smoke.py -v`  
Expected: PASS.

**Step 5: Commit**

```bash
git add pyproject.toml src/claudebot_gateway/__init__.py src/claudebot_gateway/cli.py tests/test_smoke.py
git commit -m "chore: bootstrap gateway package with uv"
```

## Task 2: Define Core Models and Config Contracts

**Files:**
- Create: `src/claudebot_gateway/models.py`
- Create: `src/claudebot_gateway/config.py`
- Create: `tests/test_models_config.py`

**Step 1: Write the failing test**

```python
def test_workspace_layout_constants():
    from claudebot_gateway.models import WorkspaceKind
    assert WorkspaceKind.MAIN.value == "main"
    assert WorkspaceKind.HEARTBEAT.value == "heartbeat"
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_models_config.py -v`  
Expected: FAIL due to missing model/config definitions.

**Step 3: Write minimal implementation**

- Add dataclasses/Pydantic models for inbound/outbound, health, cron definitions.
- Add config schema supporting:
  - channels (CLI/Telegram enable flags)
  - queue limits
  - workspace root
  - heartbeat interval
  - health HTTP feature flag
  - persistence path

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_models_config.py -v`  
Expected: PASS.

**Step 5: Commit**

```bash
git add src/claudebot_gateway/models.py src/claudebot_gateway/config.py tests/test_models_config.py
git commit -m "feat: add core models and config contracts"
```

## Task 3: Implement Workspace Resolver and Sanitization

**Files:**
- Create: `src/claudebot_gateway/workspaces.py`
- Create: `tests/test_workspaces.py`

**Step 1: Write the failing test**

```python
def test_sanitizes_channel_workspace_key():
    from claudebot_gateway.workspaces import make_channel_workspace_key
    assert make_channel_workspace_key("TeleGram", "Chat:123/ABC") == "telegram_chat_123_abc"
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_workspaces.py::test_sanitizes_channel_workspace_key -v`  
Expected: FAIL, function missing or wrong result.

**Step 3: Write minimal implementation**

- Implement sanitization rules:
  - lowercase
  - `a-z0-9_-` allow-list
  - replace others with `_`
  - collapse and trim underscores
- Implement path resolvers for:
  - `main`
  - `heartbeat`
  - `<channel_name>_<channel_id>`
  - `cron_<job_id>`

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_workspaces.py -v`  
Expected: PASS.

**Step 5: Commit**

```bash
git add src/claudebot_gateway/workspaces.py tests/test_workspaces.py
git commit -m "feat: add deterministic workspace resolver and sanitization"
```

## Task 4: Implement Identity Registry with Persistence

**Files:**
- Create: `src/claudebot_gateway/identity_registry.py`
- Create: `src/claudebot_gateway/persistence/sqlite_store.py`
- Create: `tests/test_identity_registry.py`

**Step 1: Write the failing test**

```python
def test_round_trip_identity_mapping(tmp_path):
    from claudebot_gateway.identity_registry import IdentityRegistry
    reg = IdentityRegistry(db_path=tmp_path / "gateway.db")
    key = reg.register("telegram", {"chat_id": "12345"})
    loaded = reg.resolve(key)
    assert loaded["channel_type"] == "telegram"
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_identity_registry.py -v`  
Expected: FAIL due to missing DB/registry.

**Step 3: Write minimal implementation**

- Create SQLite schema for `channel_identity`.
- Implement idempotent register/resolve APIs.
- Persist raw and sanitized identifiers and workspace key.

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_identity_registry.py -v`  
Expected: PASS.

**Step 5: Commit**

```bash
git add src/claudebot_gateway/identity_registry.py src/claudebot_gateway/persistence/sqlite_store.py tests/test_identity_registry.py
git commit -m "feat: add identity registry with sqlite persistence"
```

## Task 5: Implement Message Bus and Backpressure Policy

**Files:**
- Create: `src/claudebot_gateway/message_bus.py`
- Create: `tests/test_message_bus.py`

**Step 1: Write the failing test**

```python
import pytest

@pytest.mark.asyncio
async def test_rejects_newest_when_inbound_queue_full():
    from claudebot_gateway.message_bus import MessageBus
    bus = MessageBus(inbound_maxsize=1)
    await bus.publish_inbound({"id": "1"})
    accepted = await bus.try_publish_inbound({"id": "2"})
    assert accepted is False
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_message_bus.py -v`  
Expected: FAIL due to missing policy behavior.

**Step 3: Write minimal implementation**

- Add bounded inbound queue.
- Implement non-blocking `try_publish_inbound`.
- Add helper event for busy rejection response path.

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_message_bus.py -v`  
Expected: PASS.

**Step 5: Commit**

```bash
git add src/claudebot_gateway/message_bus.py tests/test_message_bus.py
git commit -m "feat: add bounded message bus with reject-newest backpressure"
```

## Task 6: Build Agent Runner and Outbound Dispatcher

**Files:**
- Create: `src/claudebot_gateway/agent_runner.py`
- Create: `src/claudebot_gateway/outbound_dispatcher.py`
- Create: `tests/test_agent_dispatch_flow.py`

**Step 1: Write the failing test**

```python
import pytest

@pytest.mark.asyncio
async def test_inbound_generates_outbound_with_target_channel():
    # mock agent sdk turn and assert outbound channel routing fields exist
    ...
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_agent_dispatch_flow.py -v`  
Expected: FAIL due to missing runner/dispatcher integration.

**Step 3: Write minimal implementation**

- Wrap Claude Agent SDK turn invocation.
- Emit normalized outbound model.
- Dispatch outbound strictly by channel adapter name.
- Ensure failures are logged/recorded and do not crash runtime.

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_agent_dispatch_flow.py -v`  
Expected: PASS.

**Step 5: Commit**

```bash
git add src/claudebot_gateway/agent_runner.py src/claudebot_gateway/outbound_dispatcher.py tests/test_agent_dispatch_flow.py
git commit -m "feat: add agent runner and outbound dispatcher"
```

## Task 7: Add Channel Manager with CLI and Telegram Adapters

**Files:**
- Create: `src/claudebot_gateway/channel_manager.py`
- Create: `src/claudebot_gateway/channels/cli.py`
- Create: `src/claudebot_gateway/channels/telegram.py`
- Create: `tests/test_channel_manager.py`

**Step 1: Write the failing test**

```python
import pytest

@pytest.mark.asyncio
async def test_channel_failure_does_not_stop_manager():
    # start two fake channels, one crashes, manager stays alive for other
    ...
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_channel_manager.py -v`  
Expected: FAIL due to manager/adapters not implemented.

**Step 3: Write minimal implementation**

- Build adapter interface and supervised run loops.
- Implement CLI adapter.
- Implement Telegram adapter scaffold + reconnection policy hooks.
- Isolate channel failures.

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_channel_manager.py -v`  
Expected: PASS.

**Step 5: Commit**

```bash
git add src/claudebot_gateway/channel_manager.py src/claudebot_gateway/channels/cli.py src/claudebot_gateway/channels/telegram.py tests/test_channel_manager.py
git commit -m "feat: add channel manager with cli and telegram adapters"
```

## Task 8: Implement Cron Service and Delivery Failure Policy

**Files:**
- Create: `src/claudebot_gateway/cron_service.py`
- Modify: `src/claudebot_gateway/persistence/sqlite_store.py`
- Create: `tests/test_cron_service.py`

**Step 1: Write the failing test**

```python
import pytest

@pytest.mark.asyncio
async def test_cron_delivery_failure_is_recorded_and_dropped():
    # simulate target channel down, expect run error persisted and no retry
    ...
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_cron_service.py -v`  
Expected: FAIL because delivery semantics not present.

**Step 3: Write minimal implementation**

- Add job create/list/remove/load.
- Execute runs in `cron_<job_id>` workspace.
- Persist run records and delivery outcomes.
- Enforce delivery policy: immediate drop on send failure.

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_cron_service.py -v`  
Expected: PASS.

**Step 5: Commit**

```bash
git add src/claudebot_gateway/cron_service.py src/claudebot_gateway/persistence/sqlite_store.py tests/test_cron_service.py
git commit -m "feat: add cron service with persisted runs and drop-on-failure delivery"
```

## Task 9: Implement Heartbeat Service with Isolated Workspace

**Files:**
- Create: `src/claudebot_gateway/heartbeat_service.py`
- Modify: `src/claudebot_gateway/persistence/sqlite_store.py`
- Create: `tests/test_heartbeat_service.py`

**Step 1: Write the failing test**

```python
import pytest

@pytest.mark.asyncio
async def test_heartbeat_triggers_only_when_actionable():
    # no-op for empty content, execute turn when actionable text appears
    ...
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_heartbeat_service.py -v`  
Expected: FAIL due to missing heartbeat behavior.

**Step 3: Write minimal implementation**

- Add periodic checker.
- Read actionable source from heartbeat workspace.
- Trigger agent turn in `heartbeat` workspace only when actionable.
- Persist heartbeat run status.

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_heartbeat_service.py -v`  
Expected: PASS.

**Step 5: Commit**

```bash
git add src/claudebot_gateway/heartbeat_service.py src/claudebot_gateway/persistence/sqlite_store.py tests/test_heartbeat_service.py
git commit -m "feat: add heartbeat service with isolated workspace execution"
```

## Task 10: Compose Supervisor Runtime and Graceful Shutdown

**Files:**
- Create: `src/claudebot_gateway/runtime.py`
- Create: `tests/test_runtime_lifecycle.py`

**Step 1: Write the failing test**

```python
import pytest

@pytest.mark.asyncio
async def test_runtime_graceful_shutdown_drains_and_stops_tasks():
    # start runtime, send stop signal, verify no unhandled exceptions and tasks close
    ...
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_runtime_lifecycle.py -v`  
Expected: FAIL due to missing supervisor orchestration.

**Step 3: Write minimal implementation**

- Ordered startup and shutdown.
- Intake stop + drain timeout.
- Background cancellation and persistence flush.
- Runtime health state tracking.

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_runtime_lifecycle.py -v`  
Expected: PASS.

**Step 5: Commit**

```bash
git add src/claudebot_gateway/runtime.py tests/test_runtime_lifecycle.py
git commit -m "feat: add gateway runtime supervisor and graceful shutdown"
```

## Task 11: Add Health Surfaces (CLI + Feature-Flag HTTP)

**Files:**
- Create: `src/claudebot_gateway/health.py`
- Modify: `src/claudebot_gateway/cli.py`
- Modify: `src/claudebot_gateway/runtime.py`
- Create: `tests/test_health.py`

**Step 1: Write the failing test**

```python
def test_http_health_only_available_when_feature_flag_enabled():
    # disabled -> no server; enabled -> health reports alive loops
    ...
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_health.py -v`  
Expected: FAIL due to missing health service behavior.

**Step 3: Write minimal implementation**

- Implement shared health model for runtime/agent/dispatcher.
- CLI status command reads model.
- Optional HTTP endpoint reads same model and starts only by config flag.

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_health.py -v`  
Expected: PASS.

**Step 5: Commit**

```bash
git add src/claudebot_gateway/health.py src/claudebot_gateway/cli.py src/claudebot_gateway/runtime.py tests/test_health.py
git commit -m "feat: add cli and feature-flagged http health checks"
```

## Task 12: End-to-End Verification and Hardening

**Files:**
- Modify: `tests/test_e2e_gateway.py`
- Modify: `pyproject.toml`

**Step 1: Write the failing test**

```python
import pytest

@pytest.mark.asyncio
async def test_gateway_e2e_cli_message_cron_heartbeat_flow():
    # run minimal in-memory stack, verify all key paths
    ...
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_e2e_gateway.py -v`  
Expected: FAIL before final integration fixes.

**Step 3: Write minimal implementation**

- Patch integration gaps across modules.
- Ensure persistence, routing, and lifecycle consistency.

**Step 4: Run full verification**

Run:
- `uv run pytest -v`
- `uv run ruff check .`
- `uv run mypy src`

Expected:
- all tests PASS
- lint PASS
- type checks PASS

**Step 5: Commit**

```bash
git add .
git commit -m "feat: complete gateway daemon v1 core runtime"
```

## Rollout Checklist

- Confirm Telegram credentials and allow-list behavior in non-production environment.
- Verify queue size and heartbeat interval defaults.
- Verify SQLite DB path and backup strategy.
- Verify log redaction for secrets.
- Verify that HTTP health remains disabled by default.

## Explicit Decisions Captured in This Plan

- Python-first implementation with `uv`.
- V1 channels: CLI + Telegram.
- V1 includes cron and heartbeat.
- Backpressure policy: bounded queue, reject newest.
- Workspace layout:
  - `main`
  - `heartbeat`
  - `<channel_name>_<channel_id>`
  - `cron_<job_id>`
- Sanitization rules enforced for channel workspace keys.
- Cron delivery failure policy: drop immediately, record failure.
- Health availability: CLI always; HTTP via explicit feature flag.

