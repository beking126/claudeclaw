# PRD + README Missing-Items Audit Plan

## Summary

Create a code-grounded gap report against `docs/PRD_GATEWAY_DAEMON.md` and `README.md`, then produce a complete, prioritized list of all remaining implementation tasks.  
This execution will be documentation-only (no feature code changes), with each missing item tied to concrete repository evidence.

## Current State Analysis

- Baseline selected by user: PRD + README roadmap.
- Existing integration spec package (`.trae/specs/design-agent-sdk-integration/*`) is fully checked, so remaining gaps are broader roadmap/PRD scope.
- Initial exploration already identified likely missing areas:
  - Additional production channels beyond CLI/Telegram scaffold.
  - Telegram robustness beyond scaffold state.
  - Schedule model expansion (`at`, `every`, cron expressions).
  - Cron/heartbeat runtime execution path alignment with PRD intent.
  - Channel-down delivery retry strategy for cron delivery.
  - Health/readiness HTTP serving behavior.
  - Session management enhancements listed in README.

## Proposed Changes

### 1) Produce a formal gap report document

**File to create**
- `docs/plans/2026-03-19-prd-readme-gap-report.md`

**What**
- Enumerate every unmet PRD/README requirement.
- For each item, include:
  - Requirement text reference (PRD/README path + line range).
  - Current implementation evidence (source/tests path + line range).
  - Gap classification (missing, partial, divergent).
  - Impact statement (operational/product risk).

**Why**
- Establish an auditable single source for “what is still missing” without ambiguity.

**How**
- Re-scan these files and map requirement-to-implementation:
  - `docs/PRD_GATEWAY_DAEMON.md`
  - `README.md`
  - `src/claudebot_gateway/**/*.py`
  - `tests/**/*.py`

### 2) Produce complete remaining-tasks backlog

**File to create**
- `docs/plans/2026-03-19-prd-readme-remaining-tasks.md`

**What**
- Convert all identified gaps into implementation-ready tasks.
- Include for each task:
  - Goal and acceptance criteria.
  - Primary files to modify.
  - Required tests to add/update.
  - Dependency ordering.
  - Priority tier (P0/P1/P2).

**Why**
- User asked for “gap report + all remaining tasks”; this creates an execution queue with no hidden work.

**How**
- Derive tasks strictly from the gap report findings (no speculative roadmap additions).
- Keep one canonical task per gap, splitting only when distinct subsystems are involved.

### 3) Cross-check AGENTS contract alignment

**File to inspect**
- `AGENTS.md`

**What**
- Verify AGENTS constraints do not contradict PRD + README baseline.
- If contradictions exist, note them in the gap report under a “Contract Drift” section.

**Why**
- Prevent future execution from following conflicting instructions.

**How**
- Compare AGENTS source-of-truth and invariants against PRD/README requirements and current code.

## Assumptions & Decisions

- Scope is audit + planning artifacts only; no runtime/CLI/channel implementation in this step.
- “Missing from planned” means unmet requirements from `docs/PRD_GATEWAY_DAEMON.md` and `README.md`.
- Existing `.trae/specs/design-agent-sdk-integration` completion remains valid for its own scope and is not treated as contradictory unless directly conflicting with PRD/README.
- Output must include all remaining tasks, not only near-term priorities.

## Verification Steps

1. Confirm every gap item has at least one requirement citation and one implementation citation.
2. Confirm every identified gap maps to at least one backlog task.
3. Confirm no backlog task exists without a corresponding documented gap.
4. Validate both new docs use consistent status/priority language and dependency ordering.
5. Run a final pass to ensure no invented technologies/requirements appear beyond PRD + README + current code evidence.
