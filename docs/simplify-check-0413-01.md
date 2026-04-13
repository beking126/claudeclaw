Simplify: Full Codebase Cleanup

Context

A full codebase review (reuse, quality, efficiency) identified several concrete improvements. The codebase is well-structured overall. This plan
focuses on clear wins — removing duplicated logic, fixing TOCTOU anti-patterns, and small efficiency improvements — without changing behavior or
adding unnecessary abstractions.

---
Changes

1. Extract _get() helper in claude_adapter.py

File: src/claudebot_gateway/agent_runtime/claude_adapter.py

_extract_text, _extract_result_metadata, and _is_result_message each branch on isinstance(message, dict) with near-identical .get() vs getattr()
logic. Extract a single _get(message, key, default=None) helper and collapse each method to one code path.

2. Extract _escape_html() in telegram.py

File: src/claudebot_gateway/channels/telegram.py

Three identical .replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;") chains at lines 186, 194, 197. Extract a _escape_html(text: str)
-> str function and call it in all three places.

3. Extract _format_epoch_utc() in cli.py

File: src/claudebot_gateway/cli.py

Two identical epoch-to-formatted-UTC blocks at lines 111-112 and 140-141:
dt = datetime.fromtimestamp(ts, tz=timezone.utc)
dt.strftime('%Y-%m-%d %H:%M UTC')
Extract _format_epoch_utc(epoch: float) -> str.

4. Fix TOCTOU: heartbeat_service.py

File: src/claudebot_gateway/heartbeat_service.py lines 47-49

Replace:
if not file_path.exists():
    return ""
return file_path.read_text(encoding="utf-8")
With try/except FileNotFoundError.

5. Fix TOCTOU: config.py

File: src/claudebot_gateway/config.py lines 109-112

Replace if effective_config_path.exists(): + read_text() with try/except FileNotFoundError.

6. Fix TOCTOU: cli.py _handle_validate

File: src/claudebot_gateway/cli.py lines 267-269

Replace if config_path.exists(): + read_text() with try/except FileNotFoundError.

7. Extract _track_seen() in feishu.py

File: src/claudebot_gateway/channels/feishu.py

The bounded OrderedDict insert+evict pattern appears 3 times (lines 130-132, 195-197, 198-200):
store[key] = None
while len(store) > 1000:
    store.popitem(last=False)
Extract a _track_seen(key, store, max_size=1000) method and use it at all three sites.

8. Cache asdict(self._options) in claude_adapter.py

File: src/claudebot_gateway/agent_runtime/claude_adapter.py line 105

Compute asdict(self._options) once in __init__, store as self._base_options_dict. In _build_sdk_options, shallow-copy it: options_payload =
dict(self._base_options_dict).

9. Move coerce_to_str_dict out of sqlite_store.py

Files:
- src/claudebot_gateway/persistence/sqlite_store.py (remove function)
- src/claudebot_gateway/persistence/__init__.py (add function)
- src/claudebot_gateway/cron_service.py (update import)
- src/claudebot_gateway/heartbeat_service.py (update import)

coerce_to_str_dict is a general utility with no SQLite dependency. Move it to persistence/__init__.py and update the two callers.

10. Skip heartbeat DB write when skipped

File: src/claudebot_gateway/heartbeat_service.py lines 37-42

When actionable is False (no source text), skip record_heartbeat_run. This avoids inserting a no-op row every 300 seconds.

11. Remove redundant failure_reason init in cron_service.py

File: src/claudebot_gateway/cron_service.py line 59

failure_reason: str | None = None is immediately reassigned on line 67. Remove the initialization; the variable is always assigned before use.

---
Verification

Run the mandatory baseline checks from AGENTS.md:
uv run pytest -q
uv run ruff check .
uv run mypy src tests