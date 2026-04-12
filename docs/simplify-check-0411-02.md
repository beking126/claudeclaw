Simplify: Whole Codebase Cleanup

Context

Full codebase review of src/claudebot_gateway/ (~3400 lines) for reuse, quality, and efficiency issues. Two review agents identified 14 reuse
issues and 18 efficiency issues. After filtering false positives and low-value changes, the items below are actionable.

Changes

1. Remove dead code: make_busy_rejection() — message_bus.py:28-33

Never called anywhere. AgentRunner builds rejection dicts inline.
- Action: Delete make_busy_rejection() method.

2. Remove dead code: _chat_ids — telegram.py:36,139

Written to in _on_message() but never read. _send_message() uses int(destination) directly.
- Action: Remove _chat_ids dict declaration and the write line (self._chat_ids[sender] = ...).

3. Remove dead state: _reconnect_attempts in channels — telegram.py:34, feishu.py:43

Initialized to 0, returned in health(), but never incremented. ChannelManager tracks its own reconnect counter. The channel-level counter always
reports 0 — misleading.
- Action: Remove _reconnect_attempts from both channels and their health() output.

4. Fix remove_job() full-table scan — cron_service.py:160-165

Loads ALL cron jobs into Python dicts just to check if one ID exists.
- Action: Replace with self._store.delete_cron_job(job_id=job_id) + check cursor.rowcount via new delete_cron_job_returning_count() method, or
simply call delete then check existence via a lightweight SELECT 1 before delete.

Actually simplest: have SqliteStore.delete_cron_job() return rowcount, then check that.

5. Fix due_job_count() full row materialization — cron_service.py:153-155

Calls list_due_cron_jobs() which fetches all matching rows as dicts, then takes len().
- Action: Add count_due_cron_jobs() to SqliteStore using SELECT COUNT(*), call that instead.

6. Deduplicate QueryCallable type alias — claude_adapter.py:13, factory.py:8

Identical type alias defined in two files.
- Action: Define once in claude_adapter.py, import in factory.py.

7. Fix double _extract_sender() call — agent_runner.py:53-68

When both allowed-senders and rate-limiting are active, _extract_sender() runs twice on the same inbound message.
- Action: Extract sender once before the checks, pass into _is_sender_allowed().

8. Fix double health_snapshot() on /ready — health.py:87,107

_is_ready() calls health_snapshot() internally, then the /ready handler calls it again for the response.
- Action: Compute snapshot once in _handle_http_client(), pass to _is_ready() and inline into response.

9. Reduce _bus_draining_worker wake frequency — runtime.py:341-358

Workers wake 20x/sec via 0.05s timeout when idle. Unnecessary CPU for idle daemon.
- Action: Increase timeout from 0.05s to 0.5s. Still responsive for shutdown (0.5s max delay), 10x less polling overhead.

10. Deduplicate SQL column list — sqlite_store.py:347-367

list_all_cron_jobs() and list_due_cron_jobs() duplicate the same 8-column SELECT list.
- Action: Extract _CRON_JOB_COLUMNS constant, reference in both queries.

11. Remove redundant status_snapshot() deep-copy — channel_manager.py:30-38

Creates new nested dicts on every call. Since _status values are simple string/int types that get replaced (not mutated), callers can safely
reference the original.
- Action: Return self._status directly, or at minimum remove the inner dict comprehension since values are immutable scalars.

Files to modify

- src/claudebot_gateway/message_bus.py — remove make_busy_rejection
- src/claudebot_gateway/channels/telegram.py — remove _chat_ids, _reconnect_attempts
- src/claudebot_gateway/channels/feishu.py — remove _reconnect_attempts
- src/claudebot_gateway/cron_service.py — fix remove_job(), fix due_job_count()
- src/claudebot_gateway/persistence/sqlite_store.py — add count_due_cron_jobs(), update delete_cron_job() return, extract column constant
- src/claudebot_gateway/agent_runtime/factory.py — import QueryCallable from adapter
- src/claudebot_gateway/agent_runner.py — extract sender once
- src/claudebot_gateway/health.py — compute snapshot once per request
- src/claudebot_gateway/runtime.py — increase drain timeout
- src/claudebot_gateway/channel_manager.py — simplify status_snapshot()

Intentionally NOT fixing (false positives / not worth churn)

- Retry logic "duplication" between BaseChannel.send() and CronService._send_with_retry() — different backoff strategies, different error
semantics
- _load_sdk() duplication — different SDKs with different APIs, not worth abstracting
- _extract_text() dual dict/object branches — SDK returns both types, branches are necessary
- asdict() per execution — options dict gets mutated per-request (resume, workspace guard), can't cache
- load_workspace_prompt_files() per execution — files may change on disk between calls
- _ensure_schema() on init — fast idempotent DDL, not a real cost
- _read_str/int/float helpers — serve a type-safety purpose in config loading
- run_due_jobs() sequential execution — safer with shared DB state, parallelization adds complexity
- _health_signals() DB queries — health endpoints need fresh data by design
- purge_old_turns() unconditional — cheap DELETE with empty result set
- _heartbeat_agent()/_cron_agent() similarity — trivial 2-line methods, unification adds indirection for no gain

Verification

uv run pytest -q
uv run ruff check .
uv run mypy src tests
All three must pass after changes.