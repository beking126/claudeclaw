# Agent Runtime Abstraction + Claude Agent SDK Integration Spec

## Why
The current gateway uses a placeholder turn handler and does not leverage Claude Agent SDK session, tool, skill, sub-agent, and context capabilities. We need a production-ready integration that is swappable so future non-Claude runtimes can be added without rewriting gateway orchestration.

## What Changes
- Add an agent runtime abstraction layer that decouples gateway orchestration from concrete agent providers.
- Implement a Claude Agent SDK runtime adapter using `docs/claude-sdk/claude-sdk-python.md` guidance.
- Add a new CLI command: `claudebot-gateway agent` for one-off agent requests.
- Default `agent` command workspace to `workspaces/main`.
- Route agent execution through Claude SDK with configured tools, skills, sub agents, and context/session settings.
- Add configuration schema for selecting runtime provider and Claude SDK runtime options.
- Add observability around agent runtime selection, session mode, and execution outcomes.
- Add tests for runtime abstraction, Claude adapter behavior, and `agent` CLI command behavior.

## Impact
- Affected specs: gateway lifecycle, message routing, CLI UX, observability, security/safety controls.
- Affected code: `src/claudebot_gateway/runtime.py`, `src/claudebot_gateway/agent_runner.py`, `src/claudebot_gateway/cli.py`, `src/claudebot_gateway/config.py`, new agent runtime modules, related tests.

## ADDED Requirements
### Requirement: Agent Runtime Abstraction
The system SHALL define a provider-agnostic agent runtime interface used by gateway workers and direct CLI invocations.

#### Scenario: Runtime selected by config
- **WHEN** the gateway starts with an agent runtime configured
- **THEN** the runtime factory resolves the configured provider
- **AND** gateway code depends only on the shared runtime interface.

#### Scenario: Unsupported runtime
- **WHEN** an unknown runtime provider is configured
- **THEN** startup fails with a clear, actionable configuration error.

### Requirement: Claude Agent SDK Runtime Adapter
The system SHALL provide an adapter implementing the shared runtime interface using Claude Agent SDK.

#### Scenario: One-off request execution
- **WHEN** a single prompt is executed through the Claude adapter
- **THEN** the adapter runs with configured cwd/workspace and SDK options
- **AND** returns final response text and execution metadata.

#### Scenario: Context/session-enabled execution
- **WHEN** SDK options enable conversation continuity/session resume
- **THEN** the adapter uses SDK session controls as configured
- **AND** preserves expected context behavior across requests.

#### Scenario: Tool/skill/sub-agent/context settings propagation
- **WHEN** runtime options specify tools, MCP servers, hooks, and programmatic sub-agents
- **THEN** the adapter passes those settings into Claude SDK options consistently.

### Requirement: `agent` CLI Command
The system SHALL expose `claudebot-gateway agent` for direct prompt execution.

#### Scenario: Default workspace
- **WHEN** the operator runs `claudebot-gateway agent --prompt "..."`
- **THEN** the command executes in the default `workspaces/main` workspace
- **AND** prints the final response to stdout.

#### Scenario: Explicit workspace override
- **WHEN** the operator provides `--workspace-root` and/or workspace selector options
- **THEN** the command executes in the resolved workspace path
- **AND** logs key paths without exposing secrets.

## MODIFIED Requirements
### Requirement: Agent Processing in Gateway Runtime
Gateway agent processing SHALL invoke the configured runtime adapter instead of fixed echo/default handlers.

#### Scenario: Inbound message processing
- **WHEN** an inbound message is consumed from the bus
- **THEN** the agent worker executes it via the selected runtime provider
- **AND** publishes outbound responses preserving channel/destination routing.

### Requirement: Configuration Contract
Gateway configuration SHALL include agent runtime selection and provider-specific options.

#### Scenario: Backward-compatible defaults
- **WHEN** no explicit runtime provider is configured
- **THEN** the system defaults to Claude runtime (or current compatible default per implementation policy)
- **AND** remains runnable with minimal required fields.

## REMOVED Requirements
### Requirement: Hardcoded Placeholder Turn Handling
**Reason**: Placeholder turn behavior blocks production integration and extensibility.
**Migration**: Replace direct/default turn handler paths with runtime interface calls and adapter-backed execution.
