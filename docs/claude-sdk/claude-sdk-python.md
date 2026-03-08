Agent SDK

Complete API reference for the Python Agent SDK, including all functions, types, and classes.

## 

Choosing between `query()` and `ClaudeSDKClient`

The Python SDK provides two ways to interact with Claude Code:

|     Feature     |            `query()`            |          `ClaudeSDKClient`           |
|-----------------|-------------------------------|------------------------------------|
|     **Session**     | Creates new session each time |        Reuses same session         |
|  **Conversation**   |        Single exchange        | Multiple exchanges in same context |
|   **Connection**    |     Managed automatically     |           Manual control           |
| **Streaming Input** |          ✅ Supported          |            ✅ Supported             |
|   **Interrupts**    |        ❌ Not supported        |            ✅ Supported             |
|      **Hooks**      |          ✅ Supported          |            ✅ Supported             |
|  **Custom Tools**   |          ✅ Supported          |            ✅ Supported             |
|  **Continue Chat**  |    ❌ New session each time    |      ✅ Maintains conversation      |
|    **Use Case**     |         One-off tasks         |      Continuous conversations      |

### 

When to use `query()` (new session each time)

**Best for:**

-   One-off questions where you don't need conversation history
-   Independent tasks that don't require context from previous exchanges
-   Simple automation scripts
-   When you want a fresh start each time

### 

When to use `ClaudeSDKClient` (continuous conversation)

**Best for:**

-   **Continuing conversations** - When you need Claude to remember context
-   **Follow-up questions** - Building on previous responses
-   **Interactive applications** - Chat interfaces, REPLs
-   **Response-driven logic** - When next action depends on Claude's response
-   **Session control** - Managing conversation lifecycle explicitly

Creates a new session for each interaction with Claude Code. Returns an async iterator that yields messages as they arrive. Each call to `query()` starts fresh with no memory of previous interactions.

| Parameter |           Type            |                               Description                                |
|-----------|---------------------------|--------------------------------------------------------------------------|
|  `prompt`   | `str | AsyncIterable[dict]` |    The input prompt as a string or async iterable for streaming mode     |
|  `options`  | `ClaudeAgentOptions | None` | Optional configuration object (defaults to `ClaudeAgentOptions()` if None) |
| `transport` |     `Transport | None`      |     Optional custom transport for communicating with the CLI process     |

Returns an `AsyncIterator[Message]` that yields messages from the conversation.

Decorator for defining MCP tools with type safety.

|  Parameter   |          Type          |                                                 Description                                                 |
|--------------|------------------------|-------------------------------------------------------------------------------------------------------------|
|     `name`     |          `str`           |                                       Unique identifier for the tool                                        |
| `description`  |          `str`           |                              Human-readable description of what the tool does                               |
| `input_schema` | `type | dict[str, Any]`  |                           Schema defining the tool's input parameters (see below)                           |
| `annotations`  | `ToolAnnotations | None` | Optional MCP tool annotations (e.g., `readOnlyHint`, `destructiveHint`, `openWorldHint`). Imported from `mcp.types` |

1.  **Simple type mapping** (recommended):
    
2.  **JSON Schema format** (for complex validation):
    

A decorator function that wraps the tool implementation and returns an `SdkMcpTool` instance.

Create an in-process MCP server that runs within your Python application.

| Parameter |             Type             | Default |                     Description                     |
|-----------|------------------------------|---------|-----------------------------------------------------|
|   `name`    |             `str`              |   \-    |          Unique identifier for the server           |
|  `version`  |             `str`              | `"1.0.0"` |                Server version string                |
|   `tools`   | `list[SdkMcpTool[Any]] | None` |  `None`   | List of tool functions created with `@tool` decorator |

Returns an `McpSdkServerConfig` object that can be passed to `ClaudeAgentOptions.mcp_servers`.

**Maintains a conversation session across multiple exchanges.** This is the Python equivalent of how the TypeScript SDK's `query()` function works internally - it creates a client object that can continue conversations.

-   **Session continuity**: Maintains conversation context across multiple `query()` calls
-   **Same conversation**: The session retains previous messages
-   **Interrupt support**: Can stop execution mid-task
-   **Explicit lifecycle**: You control when the session starts and ends
-   **Response-driven flow**: Can react to responses and send follow-ups
-   **Custom tools and hooks**: Supports custom tools (created with `@tool` decorator) and hooks

|           Method            |                                                        Description                                                        |
|-----------------------------|---------------------------------------------------------------------------------------------------------------------------|
|       `__init__(options)`        |                                     Initialize the client with optional configuration                                     |
|       `connect(prompt)`       |                            Connect to Claude with an optional initial prompt or message stream                            |
|  `query(prompt, session_id)`  |                                           Send a new request in streaming mode                                            |
|     `receive_messages()`      |                                   Receive all messages from Claude as an async iterator                                   |
|     `receive_response()`      |                                   Receive messages until and including a ResultMessage                                    |
|         `interrupt()`         |                                   Send interrupt signal (only works in streaming mode)                                    |
|   `set_permission_mode(mode)`   |                                    Change the permission mode for the current session                                     |
|      `set_model(model)`       |                          Change the model for the current session. Pass `None` to reset to default                          |
| `rewind_files(user_message_id)` | Restore files to their state at the specified user message. Requires `enable_file_checkpointing=True`. See File checkpointing |
|       `get_mcp_status()`        |                                       Get the status of all configured MCP servers                                        |
|       `get_server_info()`       |                               Get server information including session ID and capabilities                                |
|        `disconnect()`         |                                                  Disconnect from Claude                                                   |

The client can be used as an async context manager for automatic connection management:

> **Important:** When iterating over messages, avoid using `break` to exit early as this can cause asyncio cleanup issues. Instead, let the iteration complete naturally or use flags to track when you've found what you need.

#### 

Example - Continuing a conversation

#### 

Example - Streaming input with ClaudeSDKClient

#### 

Example - Using interrupts

#### 

Example - Advanced permission control

Definition for an SDK MCP tool created with the `@tool` decorator.

|   Property   |                   Type                   |                                            Description                                             |
|--------------|------------------------------------------|----------------------------------------------------------------------------------------------------|
|     `name`     |                   `str`                    |                                   Unique identifier for the tool                                   |
| `description`  |                   `str`                    |                                     Human-readable description                                     |
| `input_schema` |         `type[T] | dict[str, Any]`         |                                    Schema for input validation                                     |
|   `handler`    | `Callable[[T], Awaitable[dict[str, Any]]]` |                             Async function that handles tool execution                             |
| `annotations`  |          `ToolAnnotations | None`          | Optional MCP tool annotations (e.g., `readOnlyHint`, `destructiveHint`, `openWorldHint`). From `mcp.types` |

Abstract base class for custom transport implementations. Use this to communicate with the Claude process over a custom channel (for example, a remote connection instead of a local subprocess).

This is a low-level internal API. The interface may change in future releases. Custom implementations must be updated to match any interface changes.

|     Method      |                                 Description                                 |
|-----------------|-----------------------------------------------------------------------------|
|    `connect()`    |             Connect the transport and prepare for communication             |
|   `write(data)`   |              Write raw data (JSON + newline) to the transport               |
| `read_messages()` |               Async iterator that yields parsed JSON messages               |
|     `close()`     |                 Close the connection and clean up resources                 |
|   `is_ready()`    |             Returns `True` if the transport can send and receive              |
|   `end_input()`   | Close the input stream (for example, close stdin for subprocess transports) |

Import: `from claude_agent_sdk import Transport`

Configuration dataclass for Claude Code queries.

|         Property          |                      Type                      |      Default       |                                                                                                  Description                                                                                                  |
|---------------------------|------------------------------------------------|--------------------|---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
|           `tools`           |         `list[str] | ToolsPreset | None`         |        `None`        |                                                     Tools configuration. Use `{"type": "preset", "preset": "claude_code"}` for Claude Code's default tools                                                      |
|       `allowed_tools`       |                   `list[str]`                    |         `[]`         | Tools to auto-approve without prompting. This does not restrict Claude to only these tools; unlisted tools fall through to `permission_mode` and `can_use_tool`. Use `disallowed_tools` to block tools. See Permissions |
|       `system_prompt`       |        `str | SystemPromptPreset | None`         |        `None`        |              System prompt configuration. Pass a string for custom prompt, or use `{"type": "preset", "preset": "claude_code"}` for Claude Code's system prompt. Add `"append"` to extend the preset              |
|        `mcp_servers`        |    `dict[str, McpServerConfig] | str | Path`     |         `{}`         |                                                                               MCP server configurations or path to config file                                                                                |
|      `permission_mode`      |             `PermissionMode | None`              |        `None`        |                                                                                        Permission mode for tool usage                                                                                         |
|   `continue_conversation`   |                      `bool`                      |       `False`        |                                                                                     Continue the most recent conversation                                                                                     |
|          `resume`           |                   `str | None`                   |        `None`        |                                                                                             Session ID to resume                                                                                              |
|         `max_turns`         |                   `int | None`                   |        `None`        |                                                                                          Maximum conversation turns                                                                                           |
|       `max_budget_usd`        |                  `float | None`                  |        `None`        |                                                                                     Maximum budget in USD for the session                                                                                     |
|     `disallowed_tools`      |                   `list[str]`                    |         `[]`         |                                         Tools to always deny. Deny rules are checked first and override `allowed_tools` and `permission_mode` (including `bypassPermissions`)                                         |
|  `enable_file_checkpointing`  |                      `bool`                      |       `False`        |                                                                       Enable file change tracking for rewinding. See File checkpointing                                                                       |
|           `model`           |                   `str | None`                   |        `None`        |                                                                                              Claude model to use                                                                                              |
|      `fallback_model`       |                   `str | None`                   |        `None`        |                                                                               Fallback model to use if the primary model fails                                                                                |
|           `betas`           |                 `list[SdkBeta]`                  |         `[]`         |                                                                          Beta features to enable. See `SdkBeta` for available options                                                                           |
|       `output_format`       |             `dict[str, Any] | None`              |        `None`        |                                          Output format for structured responses (e.g., `{"type": "json_schema", "schema": {...}}`). See Structured outputs for details                                          |
| `permission_prompt_tool_name` |                   `str | None`                   |        `None`        |                                                                                     MCP tool name for permission prompts                                                                                      |
|            `cwd`            |               `str | Path | None`                |        `None`        |                                                                                           Current working directory                                                                                           |
|         `cli_path`          |               `str | Path | None`                |        `None`        |                                                                                 Custom path to the Claude Code CLI executable                                                                                 |
|         `settings`          |                   `str | None`                   |        `None`        |                                                                                             Path to settings file                                                                                             |
|         `add_dirs`          |                `list[str | Path]`                |         `[]`         |                                                                                   Additional directories Claude can access                                                                                    |
|            `env`            |                 `dict[str, str]`                 |         `{}`         |                                                                                             Environment variables                                                                                             |
|        `extra_args`         |             `dict[str, str | None]`              |         `{}`         |                                                                             Additional CLI arguments to pass directly to the CLI                                                                              |
|       `max_buffer_size`       |                   `int | None`                   |        `None`        |                                                                                    Maximum bytes when buffering CLI stdout                                                                                    |
|       `debug_stderr`        |                      `Any`                       |     `sys.stderr`     |                                                                  _Deprecated_ - File-like object for debug output. Use `stderr` callback instead                                                                  |
|          `stderr`           |          `Callable[[str], None] | None`          |        `None`        |                                                                                 Callback function for stderr output from CLI                                                                                  |
|        `can_use_tool`         |               `CanUseTool` `| None`                |        `None`        |                                                                      Tool permission callback function. See Permission types for details                                                                      |
|           `hooks`           |   `dict[HookEvent, list[HookMatcher]] | None`    |        `None`        |                                                                                  Hook configurations for intercepting events                                                                                  |
|           `user`            |                   `str | None`                   |        `None`        |                                                                                                User identifier                                                                                                |
|  `include_partial_messages`   |                      `bool`                      |       `False`        |                                                           Include partial message streaming events. When enabled, `StreamEvent` messages are yielded                                                            |
|       `fork_session`        |                      `bool`                      |       `False`        |                                                        When resuming with `resume`, fork to a new session ID instead of continuing the original session                                                         |
|          `agents`           |       `dict[str, AgentDefinition] | None`        |        `None`        |                                                                                      Programmatically defined subagents                                                                                       |
|          `plugins`          |             `list[SdkPluginConfig]`              |         `[]`         |                                                                         Load custom plugins from local paths. See Plugins for details                                                                         |
|          `sandbox`          |             `SandboxSettings` `| None`             |        `None`        |                                                                 Configure sandbox behavior programmatically. See Sandbox settings for details                                                                 |
|      `setting_sources`      |           `list[SettingSource] | None`           | `None` (no settings) |                                     Control which filesystem settings to load. When omitted, no settings are loaded. **Note:** Must include `"project"` to load CLAUDE.md files                                     |
|     `max_thinking_tokens`     |                   `int | None`                   |        `None`        |                                                                     _Deprecated_ - Maximum tokens for thinking blocks. Use `thinking` instead                                                                     |
|         `thinking`          |             `ThinkingConfig` `| None`              |        `None`        |                                                                 Controls extended thinking behavior. Takes precedence over `max_thinking_tokens`                                                                  |
|          `effort`           | `Literal["low", "medium", "high", "max"] | None` |        `None`        |                                                                                        Effort level for thinking depth                                                                                        |

Configuration for structured output validation. Pass this as a `dict` to the `output_format` field on `ClaudeAgentOptions`:

| Field  | Required |                   Description                    |
|--------|----------|--------------------------------------------------|
|  `type`  |   Yes    | Must be `"json_schema"` for JSON Schema validation |
| `schema` |   Yes    |   JSON Schema definition for output validation   |

Configuration for using Claude Code's preset system prompt with optional additions.

| Field  | Required |                          Description                          |
|--------|----------|---------------------------------------------------------------|
|  `type`  |   Yes    |        Must be `"preset"` to use a preset system prompt         |
| `preset` |   Yes    |   Must be `"claude_code"` to use Claude Code's system prompt    |
| `append` |    No    | Additional instructions to append to the preset system prompt |

Controls which filesystem-based configuration sources the SDK loads settings from.

|   Value   |                 Description                  |          Location           |
|-----------|----------------------------------------------|-----------------------------|
|  `"user"`   |             Global user settings             |   `~/.claude/settings.json`    |
| `"project"` | Shared project settings (version controlled) |    `.claude/settings.json`    |
|  `"local"`  |     Local project settings (gitignored)      | `.claude/settings.local.json` |

When `setting_sources` is **omitted** or **`None`**, the SDK does **not** load any filesystem settings. This provides isolation for SDK applications.

**Load all filesystem settings (legacy behavior):**

**Load only specific setting sources:**

**Testing and CI environments:**

**SDK-only applications:**

**Loading CLAUDE.md project instructions:**

When multiple sources are loaded, settings are merged with this precedence (highest to lowest):

1.  Local settings (`.claude/settings.local.json`)
2.  Project settings (`.claude/settings.json`)
3.  User settings (`~/.claude/settings.json`)

Programmatic options (like `agents`, `allowed_tools`) always override filesystem settings.

Configuration for a subagent defined programmatically.

|    Field    | Required |                          Description                           |
|-------------|----------|----------------------------------------------------------------|
| `description` |   Yes    |     Natural language description of when to use this agent     |
|    `tools`    |    No    |  Array of allowed tool names. If omitted, inherits all tools   |
|   `prompt`    |   Yes    |                   The agent's system prompt                    |
|    `model`    |    No    | Model override for this agent. If omitted, uses the main model |

Permission modes for controlling tool execution.

Type alias for tool permission callback functions.

The callback receives:

-   `tool_name`: Name of the tool being called
-   `input_data`: The tool's input parameters
-   `context`: A `ToolPermissionContext` with additional information

Returns a `PermissionResult` (either `PermissionResultAllow` or `PermissionResultDeny`).

Context information passed to tool permission callbacks.

|    Field    |          Type          |                Description                 |
|-------------|------------------------|--------------------------------------------|
|   `signal`    |       `Any | None`       |  Reserved for future abort signal support  |
| `suggestions` | `list[PermissionUpdate]` | Permission update suggestions from the CLI |

Union type for permission callback results.

Result indicating the tool call should be allowed.

|        Field        |             Type              | Default |                Description                |
|---------------------|-------------------------------|---------|-------------------------------------------|
|      `behavior`       |       `Literal["allow"]`        | `"allow"` |              Must be "allow"              |
|    `updated_input`    |     `dict[str, Any] | None`     |  `None`   | Modified input to use instead of original |
| `updated_permissions` | `list[PermissionUpdate] | None` |  `None`   |        Permission updates to apply        |

Result indicating the tool call should be denied.

|   Field   |      Type       | Default |                Description                 |
|-----------|-----------------|---------|--------------------------------------------|
| `behavior`  | `Literal["deny"]` | `"deny"`  |               Must be "deny"               |
|  `message`  |       `str`       |   `""`    | Message explaining why the tool was denied |
| `interrupt` |      `bool`       |  `False`  | Whether to interrupt the current execution |

Configuration for updating permissions programmatically.

|    Field    |                  Type                  |                   Description                   |
|-------------|----------------------------------------|-------------------------------------------------|
|    `type`     |              `Literal[...]`              |     The type of permission update operation     |
|    `rules`    |    `list[PermissionRuleValue] | None`    |     Rules for add/replace/remove operations     |
|  `behavior`   | `Literal["allow", "deny", "ask"] | None` |       Behavior for rule-based operations        |
|    `mode`     |         `PermissionMode | None`          |           Mode for setMode operation            |
| `directories` |            `list[str] | None`            | Directories for add/remove directory operations |
| `destination` |          `Literal[...] | None`           |      Where to apply the permission update       |

A rule to add, replace, or remove in a permission update.

Preset tools configuration for using Claude Code's default tool set.

Controls extended thinking behavior. A union of three configurations:

| Variant  |       Fields        |                 Description                  |
|----------|---------------------|----------------------------------------------|
| `adaptive` |        `type`         |   Claude adaptively decides when to think    |
| `enabled`  | `type`, `budget_tokens` | Enable thinking with a specific token budget |
| `disabled` |        `type`         |               Disable thinking               |

Literal type for SDK beta features.

Use with the `betas` field in `ClaudeAgentOptions` to enable beta features.

Configuration for SDK MCP servers created with `create_sdk_mcp_server()`.

Union type for MCP server configurations.

Configuration for loading plugins in the SDK.

| Field |       Type       |                       Description                        |
|-------|------------------|----------------------------------------------------------|
| `type`  | `Literal["local"]` | Must be `"local"` (only local plugins currently supported) |
| `path`  |       `str`        |    Absolute or relative path to the plugin directory     |

**Example:**

For complete information on creating and using plugins, see [Plugins](https://platform.claude.com/docs/en/agent-sdk/plugins).

Union type of all possible messages.

User input message.

|      Field       |           Type           |                      Description                      |
|------------------|--------------------------|-------------------------------------------------------|
|     `content`      | `str | list[ContentBlock]` |       Message content as text or content blocks       |
|       `uuid`       |        `str | None`        |               Unique message identifier               |
| `parent_tool_use_id` |        `str | None`        | Tool use ID if this message is a tool result response |
|  `tool_use_result`   |  `dict[str, Any] | None`   |            Tool result data if applicable             |

Assistant response message with content blocks.

|      Field       |             Type             |                   Description                   |
|------------------|------------------------------|-------------------------------------------------|
|     `content`      |      `list[ContentBlock]`      |     List of content blocks in the response      |
|      `model`       |             `str`              |        Model that generated the response        |
| `parent_tool_use_id` |          `str | None`          |    Tool use ID if this is a nested response     |
|      `error`       | `AssistantMessageError` `| None` | Error type if the response encountered an error |

Possible error types for assistant messages.

System message with metadata.

Final result message with cost and usage information.

The `usage` dict contains the following keys when present:

|            Key            | Type |               Description                |
|---------------------------|------|------------------------------------------|
|       `input_tokens`        | `int`  |       Total input tokens consumed.       |
|       `output_tokens`       | `int`  |      Total output tokens generated.      |
| `cache_creation_input_tokens` | `int`  | Tokens used to create new cache entries. |
|   `cache_read_input_tokens`   | `int`  | Tokens read from existing cache entries. |

Stream event for partial message updates during streaming. Only received when `include_partial_messages=True` in `ClaudeAgentOptions`. Import via `from claude_agent_sdk.types import StreamEvent`.

|      Field       |      Type      |                     Description                     |
|------------------|----------------|-----------------------------------------------------|
|       `uuid`       |      `str`       |          Unique identifier for this event           |
|    `session_id`    |      `str`       |                 Session identifier                  |
|      `event`       | `dict[str, Any]` |        The raw Claude API stream event data         |
| `parent_tool_use_id` |   `str | None`   | Parent tool use ID if this event is from a subagent |

Union type of all content blocks.

Text content block.

Thinking content block (for models with thinking capability).

Tool use request block.

Tool execution result block.

Base exception class for all SDK errors.

Raised when Claude Code CLI is not installed or not found.

Raised when connection to Claude Code fails.

Raised when the Claude Code process fails.

Raised when JSON parsing fails.

For a comprehensive guide on using hooks with examples and common patterns, see the [Hooks guide](https://platform.claude.com/docs/en/agent-sdk/hooks).

Supported hook event types.

Type definition for hook callback functions.

Parameters:

-   `input`: Strongly-typed hook input with discriminated unions based on `hook_event_name` (see [`HookInput`](https://platform.claude.com/docs/en/agent-sdk/python#hook-input))
-   `tool_use_id`: Optional tool use identifier (for tool-related hooks)
-   `context`: Hook context with additional information

Returns a [`HookJSONOutput`](https://platform.claude.com/docs/en/agent-sdk/python#hookjsonoutput) that may contain:

-   `decision`: `"block"` to block the action
-   `systemMessage`: System message to add to the transcript
-   `hookSpecificOutput`: Hook-specific output data

Context information passed to hook callbacks.

Configuration for matching hooks to specific events or tools.

Union type of all hook input types. The actual type depends on the `hook_event_name` field.

Base fields present in all hook input types.

|      Field      |      Type      |             Description             |
|-----------------|----------------|-------------------------------------|
|   `session_id`    |      `str`       |     Current session identifier      |
| `transcript_path` |      `str`       | Path to the session transcript file |
|       `cwd`       |      `str`       |      Current working directory      |
| `permission_mode` | `str` (optional) |       Current permission mode       |

Input data for `PreToolUse` hook events.

|     Field     |         Type          |              Description              |
|---------------|-----------------------|---------------------------------------|
| `hook_event_name` | `Literal["PreToolUse"]` |          Always "PreToolUse"          |
|   `tool_name`   |          `str`          | Name of the tool about to be executed |
|  `tool_input`   |    `dict[str, Any]`     |     Input parameters for the tool     |
|   `tool_use_id`   |          `str`          |  Unique identifier for this tool use  |

Input data for `PostToolUse` hook events.

|     Field     |          Type          |             Description             |
|---------------|------------------------|-------------------------------------|
| `hook_event_name` | `Literal["PostToolUse"]` |        Always "PostToolUse"         |
|   `tool_name`   |          `str`           | Name of the tool that was executed  |
|  `tool_input`   |     `dict[str, Any]`     |   Input parameters that were used   |
| `tool_response` |          `Any`           |  Response from the tool execution   |
|   `tool_use_id`   |          `str`           | Unique identifier for this tool use |

### 

`PostToolUseFailureHookInput`

Input data for `PostToolUseFailure` hook events. Called when a tool execution fails.

|     Field     |             Type              |                  Description                   |
|---------------|-------------------------------|------------------------------------------------|
| `hook_event_name` | `Literal["PostToolUseFailure"]` |          Always "PostToolUseFailure"           |
|   `tool_name`   |              `str`              |          Name of the tool that failed          |
|  `tool_input`   |        `dict[str, Any]`         |        Input parameters that were used         |
|   `tool_use_id`   |              `str`              |      Unique identifier for this tool use       |
|     `error`     |              `str`              |    Error message from the failed execution     |
| `is_interrupt`  |        `bool` (optional)        | Whether the failure was caused by an interrupt |

### 

`UserPromptSubmitHookInput`

Input data for `UserPromptSubmit` hook events.

|     Field     |            Type             |         Description         |
|---------------|-----------------------------|-----------------------------|
| `hook_event_name` | `Literal["UserPromptSubmit"]` |  Always "UserPromptSubmit"  |
|    `prompt`     |             `str`             | The user's submitted prompt |

Input data for `Stop` hook events.

|     Field      |      Type       |           Description           |
|----------------|-----------------|---------------------------------|
| `hook_event_name`  | `Literal["Stop"]` |          Always "Stop"          |
| `stop_hook_active` |      `bool`       | Whether the stop hook is active |

Input data for `SubagentStop` hook events.

|        Field        |          Type           |              Description               |
|---------------------|-------------------------|----------------------------------------|
|    `hook_event_name`    | `Literal["SubagentStop"]` |         Always "SubagentStop"          |
|   `stop_hook_active`    |          `bool`           |    Whether the stop hook is active     |
|      `agent_id`       |           `str`           |   Unique identifier for the subagent   |
| `agent_transcript_path` |           `str`           | Path to the subagent's transcript file |
|     `agent_type`      |           `str`           |          Type of the subagent          |

Input data for `PreCompact` hook events.

|        Field        |           Type            |            Description             |
|---------------------|---------------------------|------------------------------------|
|    `hook_event_name`    |   `Literal["PreCompact"]`   |        Always "PreCompact"         |
|       `trigger`       | `Literal["manual", "auto"]` |   What triggered the compaction    |
| `custom_instructions` |        `str | None`         | Custom instructions for compaction |

Input data for `Notification` hook events.

|       Field       |          Type           |         Description          |
|-------------------|-------------------------|------------------------------|
|   `hook_event_name`   | `Literal["Notification"]` |    Always "Notification"     |
|      `message`      |           `str`           | Notification message content |
|       `title`       |     `str` (optional)      |      Notification title      |
| `notification_type` |           `str`           |     Type of notification     |

Input data for `SubagentStart` hook events.

|     Field     |           Type           |            Description             |
|---------------|--------------------------|------------------------------------|
| `hook_event_name` | `Literal["SubagentStart"]` |       Always "SubagentStart"       |
|   `agent_id`    |           `str`            | Unique identifier for the subagent |
|  `agent_type`   |           `str`            |        Type of the subagent        |

### 

`PermissionRequestHookInput`

Input data for `PermissionRequest` hook events. Allows hooks to handle permission decisions programmatically.

|         Field          |             Type             |                Description                |
|------------------------|------------------------------|-------------------------------------------|
|     `hook_event_name`      | `Literal["PermissionRequest"]` |        Always "PermissionRequest"         |
|       `tool_name`        |             `str`              |  Name of the tool requesting permission   |
|       `tool_input`       |        `dict[str, Any]`        |       Input parameters for the tool       |
| `permission_suggestions` |     `list[Any]` (optional)     | Suggested permission updates from the CLI |

Union type for hook callback return values.

Synchronous hook output with control and decision fields.

Use `continue_` (with underscore) in Python code. It is automatically converted to `continue` when sent to the CLI.

A `TypedDict` containing the hook event name and event-specific fields. The shape depends on the `hookEventName` value. For full details on available fields per hook event, see [Control execution with hooks](https://platform.claude.com/docs/en/agent-sdk/hooks#outputs).

A discriminated union of event-specific output types. The `hookEventName` field determines which fields are valid.

Async hook output that defers hook execution.

Use `async_` (with underscore) in Python code. It is automatically converted to `async` when sent to the CLI.

This example registers two hooks: one that blocks dangerous bash commands like `rm -rf /`, and another that logs all tool usage for auditing. The security hook only runs on Bash commands (via the `matcher`), while the logging hook runs on all tools.

Documentation of input/output schemas for all built-in Claude Code tools. While the Python SDK doesn't export these as types, they represent the structure of tool inputs and outputs in messages.

**Tool name:** `Task`

**Input:**

**Output:**

**Tool name:** `AskUserQuestion`

Asks the user clarifying questions during execution. See [Handle approvals and user input](https://platform.claude.com/docs/en/agent-sdk/user-input#handle-clarifying-questions) for usage details.

**Input:**

**Output:**

**Tool name:** `Bash`

**Input:**

**Output:**

**Tool name:** `Edit`

**Input:**

**Output:**

**Tool name:** `Read`

**Input:**

**Output (Text files):**

**Output (Images):**

**Tool name:** `Write`

**Input:**

**Output:**

**Tool name:** `Glob`

**Input:**

**Output:**

**Tool name:** `Grep`

**Input:**

**Output (content mode):**

**Output (files\_with\_matches mode):**

**Tool name:** `NotebookEdit`

**Input:**

**Output:**

**Tool name:** `WebFetch`

**Input:**

**Output:**

**Tool name:** `WebSearch`

**Input:**

**Output:**

**Tool name:** `TodoWrite`

**Input:**

**Output:**

**Tool name:** `BashOutput`

**Input:**

**Output:**

**Tool name:** `KillBash`

**Input:**

**Output:**

**Tool name:** `ExitPlanMode`

**Input:**

**Output:**

**Tool name:** `ListMcpResources`

**Input:**

**Output:**

**Tool name:** `ReadMcpResource`

**Input:**

**Output:**

## 

Advanced Features with ClaudeSDKClient

### 

Building a Continuous Conversation Interface

### 

Using Hooks for Behavior Modification

### 

Real-time Progress Monitoring

### 

Basic file operations (using query)

### 

Streaming mode with client

Configuration for sandbox behavior. Use this to enable command sandboxing and configure network restrictions programmatically.

|         Property          |          Type           | Default |                                                                                    Description                                                                                    |
|---------------------------|-------------------------|---------|-----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
|          `enabled`          |          `bool`           |  `False`  |                                                                     Enable sandbox mode for command execution                                                                     |
| `autoAllowBashIfSandboxed`  |          `bool`           |  `True`   |                                                                Auto-approve bash commands when sandbox is enabled                                                                 |
|     `excludedCommands`      |        `list[str]`        |   `[]`    |                        Commands that always bypass sandbox restrictions (e.g., `["docker"]`). These run unsandboxed automatically without model involvement                         |
| `allowUnsandboxedCommands`  |          `bool`           |  `True`   | Allow the model to request running commands outside the sandbox. When `True`, the model can set `dangerouslyDisableSandbox` in tool input, which falls back to the permissions system |
|          `network`          |  `SandboxNetworkConfig`   |  `None`   |                                                                      Network-specific sandbox configuration                                                                       |
|     `ignoreViolations`      | `SandboxIgnoreViolations` |  `None`   |                                                                   Configure which sandbox violations to ignore                                                                    |
| `enableWeakerNestedSandbox` |          `bool`           |  `False`  |                                                                 Enable a weaker nested sandbox for compatibility                                                                  |

**Filesystem and network access restrictions** are NOT configured via sandbox settings. Instead, they are derived from [permission rules](https://code.claude.com/docs/en/settings#permission-settings):

-   **Filesystem read restrictions**: Read deny rules
-   **Filesystem write restrictions**: Edit allow/deny rules
-   **Network restrictions**: WebFetch allow/deny rules

Use sandbox settings for command execution sandboxing, and permission rules for filesystem and network access control.

**Unix socket security**: The `allowUnixSockets` option can grant access to powerful system services. For example, allowing `/var/run/docker.sock` effectively grants full host system access through the Docker API, bypassing sandbox isolation. Only allow Unix sockets that are strictly necessary and understand the security implications of each.

Network-specific configuration for sandbox mode.

|      Property       |   Type    | Default |                            Description                            |
|---------------------|-----------|---------|-------------------------------------------------------------------|
|  `allowLocalBinding`  |   `bool`    |  `False`  |  Allow processes to bind to local ports (e.g., for dev servers)   |
|  `allowUnixSockets`   | `list[str]` |   `[]`    | Unix socket paths that processes can access (e.g., Docker socket) |
| `allowAllUnixSockets` |   `bool`    |  `False`  |                 Allow access to all Unix sockets                  |
|    `httpProxyPort`    |    `int`    |  `None`   |               HTTP proxy port for network requests                |
|   `socksProxyPort`    |    `int`    |  `None`   |               SOCKS proxy port for network requests               |

Configuration for ignoring specific sandbox violations.

| Property |   Type    | Default |                 Description                 |
|----------|-----------|---------|---------------------------------------------|
|   `file`   | `list[str]` |   `[]`    | File path patterns to ignore violations for |
| `network`  | `list[str]` |   `[]`    |  Network patterns to ignore violations for  |

### 

Permissions Fallback for Unsandboxed Commands

When `allowUnsandboxedCommands` is enabled, the model can request to run commands outside the sandbox by setting `dangerouslyDisableSandbox: True` in the tool input. These requests fall back to the existing permissions system, meaning your `can_use_tool` handler will be invoked, allowing you to implement custom authorization logic.

**`excludedCommands` vs `allowUnsandboxedCommands`:**

-   `excludedCommands`: A static list of commands that always bypass the sandbox automatically (e.g., `["docker"]`). The model has no control over this.
-   `allowUnsandboxedCommands`: Lets the model decide at runtime whether to request unsandboxed execution by setting `dangerouslyDisableSandbox: True` in the tool input.

This pattern enables you to:

-   **Audit model requests**: Log when the model requests unsandboxed execution
-   **Implement allowlists**: Only permit specific commands to run unsandboxed
-   **Add approval workflows**: Require explicit authorization for privileged operations

Commands running with `dangerouslyDisableSandbox: True` have full system access. Ensure your `can_use_tool` handler validates these requests carefully.

If `permission_mode` is set to `bypassPermissions` and `allow_unsandboxed_commands` is enabled, the model can autonomously execute commands outside the sandbox without any approval prompts. This combination effectively allows the model to escape sandbox isolation silently.

-   [SDK overview](https://platform.claude.com/docs/en/agent-sdk/overview) - General SDK concepts
-   [TypeScript SDK reference](https://platform.claude.com/docs/en/agent-sdk/typescript) - TypeScript SDK documentation
-   [CLI reference](https://code.claude.com/docs/en/cli-reference) - Command-line interface
-   [Common workflows](https://code.claude.com/docs/en/common-workflows) - Step-by-step guides