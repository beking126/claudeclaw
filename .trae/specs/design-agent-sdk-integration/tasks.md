# Tasks

- [x] Task 1: Define agent runtime abstraction and factory
  - [x] SubTask 1.1: Define provider-agnostic runtime protocol/interfaces for one-off and message-driven execution
  - [x] SubTask 1.2: Add runtime provider factory and config-driven selection
  - [x] SubTask 1.3: Add validation/error path for unsupported providers

- [x] Task 2: Implement Claude Agent SDK adapter
  - [x] SubTask 2.1: Create Claude runtime adapter module wired to SDK options model
  - [x] SubTask 2.2: Implement prompt execution flow returning final response and execution metadata
  - [x] SubTask 2.3: Map tools, skills, sub-agents, MCP/context/session settings from config to SDK options
  - [x] SubTask 2.4: Add adapter-level logging and safe error mapping (no secret leakage)

- [x] Task 3: Integrate runtime abstraction into gateway processing
  - [x] SubTask 3.1: Update agent worker/runner to invoke runtime interface instead of placeholder handling
  - [x] SubTask 3.2: Preserve channel/destination routing contracts on outbound publishing
  - [x] SubTask 3.3: Keep graceful lifecycle behavior intact under runtime execution failures

- [x] Task 4: Add `agent` CLI command
  - [x] SubTask 4.1: Add CLI parser command `agent` with `--prompt` and workspace options
  - [x] SubTask 4.2: Default execution workspace to `workspaces/main`
  - [x] SubTask 4.3: Print final response and return stable exit codes
  - [x] SubTask 4.4: Emit key-path and provider logs without secrets

- [x] Task 5: Add tests and verification coverage
  - [x] SubTask 5.1: Unit tests for runtime factory selection and unsupported provider errors
  - [x] SubTask 5.2: Unit tests for Claude adapter option propagation and response extraction
  - [x] SubTask 5.3: Integration tests for gateway message flow using runtime abstraction
  - [x] SubTask 5.4: CLI tests for `agent` command defaults and output behavior
  - [x] SubTask 5.5: Run full test/lint/type suite and record results

# Task Dependencies
- Task 2 depends on Task 1.
- Task 3 depends on Tasks 1 and 2.
- Task 4 depends on Tasks 1 and 2.
- Task 5 depends on Tasks 2, 3, and 4.
