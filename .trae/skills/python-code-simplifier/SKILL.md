---
name: python-code-simplifier
description: Review and simplify final Python files, especially LLM-generated code that is overengineered, verbose, or hard to read. Use when the user asks to simplify/refactor/clean up Python code, when abstractions feel premature, or before finalizing a PR to reduce complexity while preserving behavior.
---

# Python Code Simplifier

Produce the simplest correct Python code for current requirements. Preserve behavior. Avoid speculative architecture.

## Workflow

1. Set scope and safety
- Identify target files and non-negotiable behavior.
- Identify available checks: tests, type checks, linters, runnable examples.
- If checks are missing, state reduced confidence before edits.

2. Audit complexity
- Find unnecessary abstractions and indirection.
- Prioritize findings by impact on readability and risk.
- Use the checklist in `references/simplification-checklist.md`.

3. Plan minimal edits
- Prefer removal over replacement.
- Keep changes surgical and local to the request.
- Avoid broad rewrites unless a narrow edit cannot solve the issue.
- Preserve abstractions that enforce domain invariants, security controls, or external API boundaries.

4. Simplify implementation
- Inline single-use wrappers/helpers.
- Collapse pass-through layers.
- Replace speculative generic code with concrete code for current use.
- Convert state-less classes to functions when appropriate.
- Replace custom utility code with standard library primitives when clearer.
- Tighten exception handling to expected failures only.

5. Verify and report
- Run available tests/checks.
- If a check cannot run, say so explicitly.
- Report residual risks when verification is incomplete.

## Non-Negotiable Rules

- Do not add features.
- Do not change public behavior intentionally unless asked.
- Do not collapse correctness, security, or boundary-protection abstractions.
- Do not claim performance or security improvements without evidence.
- Do not claim behavioral equivalence without verification.
- Do not invent requirements, constraints, or benchmarks.

## Simplification Heuristics

- If an abstraction is used once, inline it unless it materially improves clarity.
- If a class only groups functions and has no meaningful state, use module functions.
- If a function has too many optional flags, split into explicit call paths.
- If code uses "future-proof" extension points without current callers, remove them.
- Apply Rule of Three: delay generalization until repeated need exists.
- Prefer explicit, linear control flow over framework-like indirection.
- Keep abstractions that encode real business rules or integration boundaries.

## Severity Scale

- `high`: likely behavior risk or major maintainability cost.
- `medium`: clear unnecessary complexity with moderate impact.
- `low`: minor readability or local simplification opportunity.

## Required Output Format

Use this exact structure in responses:

```markdown
### Complexity Findings
- [high|medium|low] <file:line> <issue> <why it is unnecessary now>

### Simplification Plan
1. <edit>
2. <edit>

### Changes Made
- <what changed and why>

### Verification
- Ran: <command> -> <result>
- Ran: <command> -> <result>
- Residual risk: <what is not fully verified>
```

## Python-Specific Defaults

- Prefer straightforward data structures (`dict`, `list`, `set`, `tuple`) unless a custom type improves clarity.
- Prefer `@dataclass` for simple data containers.
- Prefer `pathlib`, `collections`, and `itertools` over custom helpers when readability improves.
- Keep type hints useful and local; remove overly clever type machinery not required by current code.