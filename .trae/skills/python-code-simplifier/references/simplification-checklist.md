# Simplification Checklist

Use this checklist during the "Audit complexity" phase.

## Overengineering Patterns

- One-use abstraction:
  Wrapper function/class used once and adds no meaningful name or boundary.
- Pass-through layer:
  Function/class forwards arguments unchanged to another call.
- Premature generalization:
  Plugin systems, factories, registries, strategy objects with one implementation.
- Configuration inflation:
  Many knobs/flags without real runtime variation.
- Defensive noise:
  Try/except blocks for impossible or unsupported states.
- Deep call chains:
  4+ layers to perform simple operations.
- Boolean-driven behavior:
  Single function with many `if flag` branches for distinct workflows.
- Generic naming:
  `BaseManager`, `ProcessorFactory`, `HandlerService` without domain signal.
- Clever typing:
  Advanced type-level patterns that obscure straightforward code.
- Non-local control flow:
  Hidden side effects via decorators/global registries when direct calls are sufficient.

## Simplify Moves

- Inline one-use helpers and wrappers.
- Merge thin layers.
- Replace abstract bases with concrete functions/classes.
- Split flag-heavy functions into explicit functions.
- Narrow exceptions to known failure modes.
- Remove dead branches and unused parameters.
- Replace custom utilities with standard library alternatives.
- Rename toward domain terms and direct intent.

## Verification Minimum

- Run targeted tests for touched behavior.
- Run lint and type checks if present.
- If checks are absent, run a smoke command and clearly mark confidence as partial.