# Simplify: Codebase Cleanup Plan - 0412

## Context

Full codebase review via three parallel agents (reuse, quality, efficiency) identified redundant code, duplicated patterns, unbounded data
structures, and per-request overhead. This plan captures the fixes worth doing — skipping false positives and overly invasive refactors.

---
### Tier 1 — Remove dead/redundant code

1.1 Remove dead method _channel_allowed_senders

- File: src/claudebot_gateway/runtime.py:305-306
- One-liner delegation to _build_allowed_senders, never called anywhere. Delete it.

1.2 Remove redundant _running = False in channel subclasses

- Files:
- src/claudebot_gateway/channels/telegram.py:34
- src/claudebot_gateway/channels/feishu.py:41
- Both reinitialize self._running = False after super().__init__() already sets it. Remove the redundant lines.

---
### Tier 2 — Extract shared helpers (reduce duplication)

2.1 Extract _load_config_from_args in cli.py

- File: src/claudebot_gateway/cli.py (8 call sites at lines ~168, 192, 249, 263, 287, 391, 400, 424)
- The identical load_gateway_config(workspace_root=..., sqlite_path=...) block appears 8 times. Extract a single helper that takes args and
returns GatewayConfig.

2.2 Define channel name constants

- Files: config.py, runtime.py, cli.py, channel_manager.py
- Define CHANNEL_NAMES = ("cli", "telegram", "discord", "feishu", "whatsapp", "slack") in config.py. Replace raw string literals in:
- runtime.py:_build_channels and _build_allowed_senders
- cli.py:_channels_status_text and _handle_validate
- This also simplifies _build_channels from 6 copy-paste blocks into a loop (see 2.3).

2.3 Unify _build_channels with registry/loop pattern

- File: src/claudebot_gateway/runtime.py:204-246
- Replace the 6 manually-unrolled blocks with a registry mapping channel name to (config_getter, constructor_fn), then loop. Also eliminates the
duplicate adapters/channels dicts — return a single dict since both contain the same objects.

2.4 Extract retry-with-backoff into base class

- Files:
- src/claudebot_gateway/channels/base.py
- src/claudebot_gateway/channels/telegram.py:101-138
- src/claudebot_gateway/channels/feishu.py:164-190, 282-284
- Move the retry loop (send + _next_backoff_seconds) into BaseChannel. Subclasses only implement _send_message().

2.5 Extract _bus_draining_worker for agent/dispatch workers

- File: src/claudebot_gateway/runtime.py:363-387
- Both _agent_worker and _dispatch_worker share identical loop structure (check empty, wait on stop_event, call processor). Extract a single
_bus_draining_worker(queue, processor, error_label) method.

2.6 Extract coerce_to_str_dict helper

- Files:
- src/claudebot_gateway/heartbeat_service.py:56
- src/claudebot_gateway/cron_service.py:171
- Both have {k: "" if v is None else str(v) for k, v in data.items()}. Extract into a small function in a shared location (e.g.,
persistence/sqlite_store.py or a new utils.py).

---
### Tier 3 — Fix efficiency issues

3.1 Replace deepcopy with dict() copy on metadata

- File: src/claudebot_gateway/runtime.py:114
- Metadata is already sanitized to flat primitives by AgentRunner._sanitize_metadata. deepcopy is overkill. Replace with dict(request.metadata).

3.2 Fix TOCTOU in load_workspace_prompt_files

- File: src/claudebot_gateway/workspaces.py:27-39
- Remove the file_path.exists() check before read_text(). The try/except already handles FileNotFoundError.

3.3 Fix unbounded _seen_event_ids in FeishuChannel

- File: src/claudebot_gateway/channels/feishu.py:44
- Replace set[str] with the same OrderedDict eviction pattern already used for _processed_message_ids (capped at 1000 entries, line 224).

3.4 Fix unbounded _buckets in RateLimiter

- File: src/claudebot_gateway/rate_limiter.py:5
- Add eviction of expired buckets. On each is_allowed call, prune entries whose window has expired. Keeps the dict bounded to only active senders.

3.5 Add created_at index to agent_turns table

- File: src/claudebot_gateway/persistence/sqlite_store.py
- Add CREATE INDEX IF NOT EXISTS idx_agent_turns_created_at ON agent_turns(created_at) to _ensure_schema. This makes the periodic purge_old_turns
efficient.

3.6 Cache SDK refs after first load (claude_adapter)

- File: src/claudebot_gateway/agent_runtime/claude_adapter.py:87, 116
- Resolve import_module("claude_agent_sdk"), ClaudeAgentOptions, and the query callable once in __init__ (or on first use), instead of on every
execution.

3.7 Cache SDK refs after first load (feishu)

- File: src/claudebot_gateway/channels/feishu.py:286-324
- Cache the SDK dict from _load_sdk after first call. Reuse in subsequent _send_message calls instead of re-importing and re-resolving attributes.

---
### Items that are explicitly skipped

┌───────────────────────────────────────────────┬───────────────────────────────────────────────────────┐
│                    Finding                    │                      Why skipped                      │
├───────────────────────────────────────────────┼───────────────────────────────────────────────────────┤
│ Schedule kind enum ("every"/"at"/"cron")      │ Low impact — only 2 files, unlikely to typo           │
├───────────────────────────────────────────────┼───────────────────────────────────────────────────────┤
│ _cron_agent/_heartbeat_agent unification      │ Small methods with different semantics                │
├───────────────────────────────────────────────┼───────────────────────────────────────────────────────┤
│ _build_services raw 6-tuple return            │ Architectural change, out of scope for cleanup        │
├───────────────────────────────────────────────┼───────────────────────────────────────────────────────┤
│ Docstring test assertions                     │ Tests intentionally assert on docs; changing is churn │
├───────────────────────────────────────────────┼───────────────────────────────────────────────────────┤
│ SQLite commit batching                        │ Durability trade-off, not a simple cleanup            │
├───────────────────────────────────────────────┼───────────────────────────────────────────────────────┤
│ Worker loop async rewrite (eliminate polling) │ Bigger refactor, risk of regression                   │
├───────────────────────────────────────────────┼───────────────────────────────────────────────────────┤
│ CronService query optimizations (count/exist) │ Low-traffic path, optimization is premature           │
└───────────────────────────────────────────────┴───────────────────────────────────────────────────────┘

---
### Verification

After all changes:
uv run pytest -q
uv run ruff check .
uv run mypy src tests

All three must pass with no regressions.