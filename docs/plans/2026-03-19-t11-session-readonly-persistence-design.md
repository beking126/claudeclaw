# T11 Design — Session Read-Only Persistence and Workspace Prompt-File Loading

## Goal

Implement T11 with a design that treats Claude Agent SDK as the source of truth for active session behavior, while Gateway persists conversation/session records in read-only form for observability, audit, and replay-friendly inspection.

## Context and SDK Findings

- Claude Agent SDK returns `session_id` on result messages and supports `resume=<session_id>`.
- SDK session continuation is project-directory aware through `cwd` and SDK-native session listing APIs.
- Current gateway already passes `cwd` per workspace and extracts result metadata (`session_id`, `usage`, duration fields), but does not persist those records.
- Current gateway does not load `SOUL.md`, `USER.md`, `TOOLS.md` into prompt composition.

Design implication:
- Do not re-implement conversational state machine in Gateway.
- Persist session artifacts as append-only records.
- Reuse SDK `session_id` for continuity and keep gateway persistence read-only to runtime behavior.

## Design Principles

1. SDK owns active session continuity.
2. Gateway stores immutable session facts for read/query only.
3. Workspace prompt files are deterministic and composable.
4. Missing prompt files never fail request execution.
5. Existing request/response behavior remains backward compatible.

## Scope

### In scope
- Persist session run metadata and turn records in SQLite (append-only).
- Resolve resume ID from persisted mapping when policy requires.
- Load and compose workspace prompt files (`SOUL.md`, `USER.md`, `TOOLS.md`) before runtime execution.
- Add tests for persistence flow and prompt-file composition.

### Out of scope
- Custom conversation memory engine replacing SDK behavior.
- Editing/deleting persisted records via runtime path.
- Cross-provider session abstraction beyond the Claude provider path.

## Proposed Architecture

## 1) Session Persistence Model (Read-Only)

Add two tables in `sqlite_store.py`:

- `agent_sessions`
  - `id` (pk)
  - `provider` (text)
  - `workspace_path` (text)
  - `channel` (text nullable)
  - `destination` (text nullable)
  - `session_id` (text)
  - `created_at` (timestamp)
  - unique key on `(provider, workspace_path, channel, destination)` for “latest session pointer”

- `agent_turns`
  - `id` (pk)
  - `session_id` (text index)
  - `workspace_path` (text)
  - `channel` (text nullable)
  - `destination` (text nullable)
  - `prompt_text` (text)
  - `response_text` (text)
  - `metadata_json` (text)
  - `created_at` (timestamp)

Behavior:
- On every successful runtime execution, append one `agent_turns` row.
- If result metadata includes `session_id`, upsert the latest pointer in `agent_sessions`.
- No update/delete to historical `agent_turns`.

## 2) Resume Policy (SDK-First)

Add lightweight resume resolver in runtime path:

- Scope key:
  - recommended default: `(provider, workspace_path, channel, destination)`
  - fallback for no channel/destination: `(provider, workspace_path, null, null)`
- For each request:
  - if config explicitly sets `resume`, keep existing behavior.
  - else if new T11 policy flag is enabled, fetch last persisted `session_id` by scope and set it as request-level resume override.
  - adapter sends this resume value to SDK `ClaudeAgentOptions`.

Important:
- Gateway does not synthesize turns; it only supplies last known `session_id`.
- If resume fails, run as one-off and continue appending records.

## 3) Workspace Prompt-File Loading

Add prompt loader in `workspaces.py`:

- `load_prompt_files(workspace: Path) -> dict[str, str]`
  - reads `SOUL.md`, `USER.md`, `TOOLS.md` if present (UTF-8)
  - returns empty strings for missing files

Add prompt composer in runtime/agent flow:

- Build final prompt:
  - header blocks in fixed order: `SOUL`, `USER`, `TOOLS`
  - delimiter lines between blocks
  - then inbound user prompt
- Keep agent request metadata including which files were loaded.

Determinism:
- stable order: `SOUL.md` -> `USER.md` -> `TOOLS.md`
- no globbing, no implicit directory traversal.

## 4) Integration Points

- `src/claudebot_gateway/runtime.py`
  - compose prompt via loader before `AgentRunner` execution
  - persist turn after each successful execute
  - resolve optional resume ID from store

- `src/claudebot_gateway/agent_runtime/claude_adapter.py`
  - accept request-level resume override while preserving config defaults
  - continue extracting `session_id` and usage metadata from result

- `src/claudebot_gateway/persistence/sqlite_store.py`
  - schema + methods:
    - `save_agent_turn(...)`
    - `upsert_latest_session(...)`
    - `get_latest_session(...)`

- `src/claudebot_gateway/workspaces.py`
  - prompt-file read helpers

## 5) Config Additions

Extend gateway config with minimal toggles:

- `agent_runtime.claude.session_persistence_enabled: bool = True`
- `agent_runtime.claude.session_scope: str = "workspace_channel_destination"`

Interpretation:
- Enabled means persist turn/session records and try implicit resume when explicit resume not set.
- Scope enum can remain single-value for now to keep YAGNI.

## Error Handling

- Prompt files unreadable:
  - log warning and continue with available content.
- SQLite persistence write failure:
  - log error but do not fail user request path.
- Resume ID invalid:
  - allow SDK/runtime to proceed without terminating gateway loop.

## Testing Strategy

Primary test files:
- `tests/test_agent_runtime.py`
- `tests/test_e2e_gateway.py`
- `tests/test_models_config.py`
- new workspace prompt loading tests

Core cases:
1. Prompt-file composition order and missing-file tolerance.
2. Turn persistence appends immutable records.
3. Latest session pointer upserts by scope key.
4. Next request in same scope applies persisted `resume`.
5. Different workspace/channel does not reuse unrelated session.
6. Explicit config `resume` overrides persisted session.

## Rollout Plan

1. Add SQLite schema + persistence methods.
2. Add prompt-file loader/composer and unit tests.
3. Add runtime integration for persistence + resume resolution.
4. Add adapter support for request-level resume override.
5. Run full regression and verify no behavior drift in existing channels.

## Acceptance Criteria for T11

- Gateway persists session/turn records in read-only append form.
- Resume uses SDK session IDs with workspace-aware scope.
- Workspace prompt files (`SOUL.md`, `USER.md`, `TOOLS.md`) are loaded and composed deterministically.
- Existing runtime behavior remains stable when files are absent.
- Tests cover persistence, scope isolation, and prompt loading end-to-end.
