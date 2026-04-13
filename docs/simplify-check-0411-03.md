Simplify: Full Codebase Cleanup (Round 2)

Context

A previous simplify pass (documented in docs/simplify-check-0411-02.md) already addressed 11 issues: dead code removal, full-table scan fixes,
type alias deduplication, double-call elimination, polling timeout tuning, and SQL column deduplication. Those changes are staged but uncommitted.

This second pass reviews the remaining full codebase for reuse, quality, and efficiency issues not already addressed.

Changes

1. Extract _TEXT_KEYS constant in claude_adapter.py

The tuple ("result", "final_response", "response", "text", "output_text") appears identically on lines 134 and 148. Extract as _TEXT_KEYS module
constant and reference in both branches.

File: src/claudebot_gateway/agent_runtime/claude_adapter.py
- Add _TEXT_KEYS = ("result", "final_response", "response", "text", "output_text") near top
- Replace inline tuples on lines 134 and 148 with _TEXT_KEYS

2. Fix inconsistent f-string logging (4 calls)

All other loggers in the codebase use %s-style structured logging. These 4 use f-strings:

- src/claudebot_gateway/channel_manager.py:47 — f"Starting channel {name}..." → _LOGGER.info("channel_starting name=%s", name)
- channel_manager.py:53 — f"Error starting channel {name}: {exc}" → _LOGGER.error("channel_start_failed name=%s error=%s", name, exc)
- channel_manager.py:76 — f"Error polling channel {name}: {exc}" → _LOGGER.error("channel_poll_failed name=%s error=%s", name, exc)
- src/claudebot_gateway/channels/feishu.py:181 — f"Received msg {data}" → _LOGGER.info("feishu_msg_received data=%s", data)

3. Simplify _increment_reconnect_attempts in channel_manager.py

The isinstance(current, int) guard on line 34 is unnecessary — the value is always initialized as int(0) (line 15) and only modified by this
method. Simplify to a direct increment.

File: src/claudebot_gateway/channel_manager.py:33-36
# Before:
current = self._status[name].get("reconnect_attempts")
attempts = current if isinstance(current, int) else 0
self._status[name]["reconnect_attempts"] = attempts + 1

# After:
self._status[name]["reconnect_attempts"] += 1

4. Fix CLI cron commands to use CronService consistently

_handle_cron_remove correctly uses CronService, but _handle_cron_add and _handle_cron_list bypass it by creating SqliteStore directly. This leaks
the persistence abstraction and duplicates normalization logic.

File: src/claudebot_gateway/cli.py

_handle_cron_list (lines 248-256) — simple replacement:
# Before:
store = SqliteStore(db_path=config.sqlite_path)
jobs = store.list_all_cron_jobs()

# After:
service = CronService(db_path=config.sqlite_path, workspace_root=config.workspace_root)
for job in service.list_jobs():

_handle_cron_add (lines 187-245) — route through CronService.schedule_job():
- Make the function async
- Replace raw SqliteStore usage with CronService
- Call await service.schedule_job(...) for each schedule type
- Wrap call site with asyncio.run(...) (matches existing CLI pattern on lines 402, 405, 429)
- Move schedule-count validation before the service call (presentation-layer concern)
- Let schedule_job() handle domain validation (missing interval_seconds, etc.) — catch ValueError for user-facing errors

5. Add Literal type aliases for stringly-typed enums

Add type aliases in the modules that define the values, annotate all parameters:

src/claudebot_gateway/cron_service.py — add near top:
from typing import Literal

ScheduleKind = Literal["every", "at", "cron"]
RunStatus = Literal["ok", "error"]
DeliveryStatus = Literal["ok", "dropped"]
- Annotate schedule_job(schedule_kind: str) → schedule_kind: ScheduleKind
- Annotate run_job_once local variables run_status, delivery_status

src/claudebot_gateway/channel_manager.py — add near top:
from typing import Literal

ChannelState = Literal["stopped", "running", "degraded"]
- Annotate _status dict values: dict[str, dict[str, ChannelState | int | None]]

src/claudebot_gateway/persistence/sqlite_store.py — import ScheduleKind from cron_service and annotate upsert_cron_job(schedule_kind: str) →
schedule_kind: ScheduleKind (or just use str since the store is the persistence boundary —Literal can stay in the service layer).

Actually, for sqlite_store.py, the schedule_kind is just a string that gets persisted. The Literal type should live in the service layer
(cron_service.py) only. No change to sqlite_store.py for this item.

Intentionally NOT fixing

┌──────────────────────────────────────────────────────────────┬──────────────────────────────────────────────────────────────────────────────┐
│                            Issue                             │                                    Reason                                    │
├──────────────────────────────────────────────────────────────┼──────────────────────────────────────────────────────────────────────────────┤
│ Retry logic "duplication" between BaseChannel and            │ Different backoff strategies (exponential vs linear), different error        │
│ CronService                                                  │ semantics                                                                    │
├──────────────────────────────────────────────────────────────┼──────────────────────────────────────────────────────────────────────────────┤
│ _load_sdk() similarity in telegram/feishu                    │ Different SDKs with different APIs, not worth abstracting                    │
├──────────────────────────────────────────────────────────────┼──────────────────────────────────────────────────────────────────────────────┤
│ _extract_text() dual dict/object branches                    │ SDK returns both types; branches are necessary                               │
├──────────────────────────────────────────────────────────────┼──────────────────────────────────────────────────────────────────────────────┤
│ _http_started as derived property                            │ Minimal gain, snapshot contract stays the same                               │
├──────────────────────────────────────────────────────────────┼──────────────────────────────────────────────────────────────────────────────┤
│ Bus passed per-call to process_once/dispatch_once            │ Deliberate design for testability, all tests use this pattern                │
├──────────────────────────────────────────────────────────────┼──────────────────────────────────────────────────────────────────────────────┤
│ Three booleans → single enum in GatewayRuntime               │ Clear enough as-is, low value for the churn                                  │
├──────────────────────────────────────────────────────────────┼──────────────────────────────────────────────────────────────────────────────┤
│ upsert_cron_job → CronJob dataclass                          │ Many call sites, low value for this size codebase                            │
├──────────────────────────────────────────────────────────────┼──────────────────────────────────────────────────────────────────────────────┤
│ FeishuChannel dual dedup dicts                               │ Different dedup scopes (HTTP webhook vs WebSocket), low value                │
├──────────────────────────────────────────────────────────────┼──────────────────────────────────────────────────────────────────────────────┤
│ Docstring/comment removals                                   │ Subjective, not harmful                                                      │
├──────────────────────────────────────────────────────────────┼──────────────────────────────────────────────────────────────────────────────┤
│ asdict() per execution in claude_adapter                     │ Options dict gets mutated per-request, can't cache                           │
├──────────────────────────────────────────────────────────────┼──────────────────────────────────────────────────────────────────────────────┤
│ load_workspace_prompt_files() per execution                  │ Files may change on disk between calls                                       │
└──────────────────────────────────────────────────────────────┴──────────────────────────────────────────────────────────────────────────────┘

Files to modify

1. src/claudebot_gateway/agent_runtime/claude_adapter.py — extract _TEXT_KEYS
2. src/claudebot_gateway/channel_manager.py — fix logging, simplify reconnect, add ChannelState
3. src/claudebot_gateway/channels/feishu.py — fix logging
4. src/claudebot_gateway/cli.py — cron add/list use CronService
5. src/claudebot_gateway/cron_service.py — add ScheduleKind, RunStatus, DeliveryStatus

Verification

uv run pytest -q
uv run ruff check .
uv run mypy src tests

All three must pass after changes. Key test files to watch:
- tests/test_cron_service.py — schedule_job, list_jobs, remove_job
- tests/test_channel_manager.py — status_snapshot, reconnect tracking
- tests/test_agent_runtime.py — _extract_text, _TEXT_KEYS
- tests/test_e2e_gateway.py — end-to-end flow