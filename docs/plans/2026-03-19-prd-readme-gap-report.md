# PRD + README Gap Report (2026-03-19)

## Scope and Method

- Baseline requirements:
  - `docs/PRD_GATEWAY_DAEMON.md`
  - `README.md` (Future Implementation roadmap section)
- Implementation evidence reviewed:
  - `src/claudebot_gateway/**/*.py`
  - `tests/**/*.py`
  - `AGENTS.md`
- Classification:
  - **Missing**: no implementation path exists.
  - **Partial**: some implementation exists but requirement is not fully met.
  - **Divergent**: implementation/doc contract differs from baseline intent.

## Gap Findings

### G1 — Additional production channels are not implemented

- Requirement evidence:
  - PRD channel scope includes Telegram/Discord/Feishu/WhatsApp/Slack bridge: `docs/PRD_GATEWAY_DAEMON.md` L4, L165-L170.
  - README roadmap requires production adapters for Discord/Feishu/WhatsApp/Slack: `README.md` L86-L89.
- Implementation evidence:
  - Config exposes only `cli` and `telegram`: `src/claudebot_gateway/config.py` L38-L40.
  - Runtime wires only `CliChannel` and `TelegramChannel`: `src/claudebot_gateway/runtime.py` L113-L120.
- Classification: **Missing**
- Impact: Cannot satisfy planned multi-channel coverage beyond CLI/Telegram.

### G2 — Telegram adapter remains scaffold-level

- Requirement evidence:
  - README explicitly calls for improving Telegram to robust integration: `README.md` L88-L89.
- Implementation evidence:
  - Telegram channel contains only stub poll/send behavior: `src/claudebot_gateway/channels/telegram.py` L1-L6.
- Classification: **Missing**
- Impact: Telegram production acceptance criteria are not met.

### G3 — Cron schedule model lacks `at` and `cron expression`

- Requirement evidence:
  - PRD requires schedule kinds `at`, `every`, `cron expression`: `docs/PRD_GATEWAY_DAEMON.md` L70-L75.
  - README roadmap repeats same schedule expansion: `README.md` L100-L105.
- Implementation evidence:
  - Cron API and persistence are interval-based (`interval_seconds`, `next_run_epoch_seconds`): `src/claudebot_gateway/cron_service.py` L61-L103, `src/claudebot_gateway/persistence/sqlite_store.py` L68-L77 and L226-L243.
- Classification: **Missing**
- Impact: Planned scheduling modes are unavailable.

### G4 — Cron and heartbeat workers do not execute the runtime-backed agent path

- Requirement evidence:
  - PRD requires cron/heartbeat to trigger agent execution: `docs/PRD_GATEWAY_DAEMON.md` L75-L83.
  - README roadmap indicates richer agent orchestration semantics: `README.md` L92-L94.
- Implementation evidence:
  - Runtime worker loops invoke `_noop_agent` for cron and heartbeat: `src/claudebot_gateway/runtime.py` L196-L219.
- Classification: **Partial**
- Impact: Daemon background automations are not using the same runtime execution contract as inbound message handling.

### G5 — Cron channel-down delivery retry strategy is absent

- Requirement evidence:
  - README requires stronger retry/handling for channel-down delivery: `README.md` L105.
  - PRD open risk highlights retry vs drop semantics: `docs/PRD_GATEWAY_DAEMON.md` L205.
- Implementation evidence:
  - Cron delivery marks failure as dropped/error without retry loop: `src/claudebot_gateway/cron_service.py` L33-L59.
  - Outbound dispatcher sends once and returns: `src/claudebot_gateway/outbound_dispatcher.py` L10-L17.
- Classification: **Missing**
- Impact: Transient channel outages can permanently drop scheduled deliveries.

### G6 — HTTP health/readiness endpoint is not implemented

- Requirement evidence:
  - README roadmap calls out optional HTTP health/readiness endpoint: `README.md` L115.
- Implementation evidence:
  - Health service toggles `http_started` but does not run an HTTP server: `src/claudebot_gateway/health.py` L22-L27.
- Classification: **Missing**
- Impact: No machine-readable liveness/readiness integration surface for process supervisors.

### G7 — CLI management commands for channels and cron are missing

- Requirement evidence:
  - PRD CLI UX includes `bot channels status` and `claudebot cron add/list/remove`: `docs/PRD_GATEWAY_DAEMON.md` L179-L181.
- Implementation evidence:
  - CLI supports only `gateway`, `status`, `agent`: `src/claudebot_gateway/cli.py` L52-L67.
- Classification: **Missing**
- Impact: Planned operational control workflows are unavailable from CLI.

### G8 — Security hardening requirements are not wired

- Requirement evidence:
  - PRD NFR-4 requires sender allow-lists, workspace restriction policy, prompt-injection hardening: `docs/PRD_GATEWAY_DAEMON.md` L119-L123.
  - README roadmap repeats allow-lists/workspace restriction/hardening: `README.md` L107-L110.
- Implementation evidence:
  - No allow-list or metadata hardening fields in gateway config model: `src/claudebot_gateway/config.py` L5-L64.
  - Inbound payload is passed through as metadata to runtime request without filtering policy: `src/claudebot_gateway/agent_runner.py` L22-L28.
- Classification: **Missing**
- Impact: Planned safety guardrails are not enforced.

### G9 — Docker portability artifact is not present

- Requirement evidence:
  - PRD portability requires Python and Docker execution support: `docs/PRD_GATEWAY_DAEMON.md` L124-L126.
- Implementation evidence:
  - No Dockerfile found in repository.
- Classification: **Missing**
- Impact: Containerized runtime path is not currently defined.

### G10 — Session management roadmap items remain unimplemented

- Requirement evidence:
  - README roadmap requires session persistence per-channel/workspace, channel-specific session context, and workspace prompt files (`SOUL.md`/`USER.md`/`TOOLS.md`): `README.md` L95-L99.
- Implementation evidence:
  - No session persistence structure in config/runtime beyond runtime options and workspace selection: `src/claudebot_gateway/config.py` L5-L24, `src/claudebot_gateway/runtime.py` L221-L232.
  - No loader path for `SOUL.md`/`USER.md`/`TOOLS.md` in runtime/adapter flow: `src/claudebot_gateway/runtime.py` L221-L232, `src/claudebot_gateway/agent_runtime/claude_adapter.py` L24-L55.
- Classification: **Missing**
- Impact: Planned session continuity and workspace prompt composition are absent.

### G11 — Status/introspection output is narrower than planned

- Requirement evidence:
  - PRD status output should include enabled channels/config summaries and running state: `docs/PRD_GATEWAY_DAEMON.md` L85-L89.
- Implementation evidence:
  - Status text includes runtime worker/errors and queue depths, but no channel configuration/running summary: `src/claudebot_gateway/cli.py` L12-L35.
  - Health snapshot signals include queue and cron/heartbeat signals only: `src/claudebot_gateway/runtime.py` L167-L173.
- Classification: **Partial**
- Impact: Operational introspection is weaker than planned for multi-channel operations.

## Contract Drift (AGENTS vs PRD + README baseline)

- **D1 — Source-of-truth scope mismatch**
  - AGENTS declares PRD as primary feature contract and omits README roadmap as contract input: `AGENTS.md` L5.
  - This is a planning drift from the selected baseline used in this audit (PRD + README).

- **D2 — README roadmap lag on agent integration**
  - README roadmap still states “replace placeholder/default turn handling”: `README.md` L92-L93.
  - Current implementation already uses runtime-backed execution in agent runner and CLI one-shot execution path: `src/claudebot_gateway/agent_runner.py` L21-L31, `src/claudebot_gateway/runtime.py` L221-L232.
  - This is documentation drift (implemented behavior not reflected as completed).

## Coverage Check

- All items above are directly grounded in PRD/README requirement lines and concrete source evidence.
- No additional technologies or requirements were introduced beyond baseline docs and in-repo implementation.
