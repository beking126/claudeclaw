import fnmatch
import logging
from collections.abc import AsyncIterator, Callable
from dataclasses import asdict
from importlib import import_module
from pathlib import Path
from typing import Any

from claudebot_gateway.agent_runtime.types import AgentExecutionRequest, AgentExecutionResult
from claudebot_gateway.config import ClaudeRuntimeOptions, ToolPermissionConfig

_LOGGER = logging.getLogger("claudebot_gateway.agent_runtime.claude")

QueryCallable = Callable[..., AsyncIterator[Any]]

_TEXT_KEYS = ("result", "final_response", "response", "text", "output_text")
_FS_PATH_KEYS = ("file_path", "path")
_FS_TOOLS = frozenset({"Read", "Write", "Edit", "Glob", "Grep", "NotebookEdit"})
_SHELL_TOOLS = frozenset({"Bash"})


def _get(message: Any, key: str, default: Any = None) -> Any:
    if isinstance(message, dict):
        return message.get(key, default)
    return getattr(message, key, default)


class AgentRuntimeExecutionError(RuntimeError):
    pass


def _make_workspace_guard(
    workspace: Path,
    tool_permissions: ToolPermissionConfig | None = None,
) -> Callable[..., Any]:
    workspace_root = workspace.resolve()
    perms = tool_permissions or ToolPermissionConfig()

    async def can_use_tool(tool_name: str, input: dict[str, Any], context: Any) -> dict[str, Any]:
        # 1. Explicit deny list takes highest priority
        if tool_name in perms.denied_tools:
            return {"behavior": "deny", "message": f"Tool '{tool_name}' is denied by configuration", "interrupt": False}

        # 2. Explicit allow list (if non-empty, only listed tools pass)
        if perms.allowed_tools and tool_name not in perms.allowed_tools:
            return {"behavior": "deny", "message": f"Tool '{tool_name}' is not in the allowed list", "interrupt": False}

        # 3. Shell tool handling
        if tool_name in _SHELL_TOOLS:
            command = str(input.get("command", "")).strip()
            if perms.allowed_shell_patterns and command:
                for pattern in perms.allowed_shell_patterns:
                    if fnmatch.fnmatch(command, pattern):
                        return {"behavior": "allow", "updated_input": None, "updated_permissions": None}
            return {"behavior": "deny", "message": "Shell access denied: restrict_to_workspace is enabled", "interrupt": False}

        # 4. Filesystem tool path restriction
        if tool_name in _FS_TOOLS:
            for key in _FS_PATH_KEYS:
                raw = input.get(key)
                if isinstance(raw, str) and raw.strip():
                    target = (workspace_root / raw).resolve() if not Path(raw).is_absolute() else Path(raw).resolve()
                    if not target.is_relative_to(workspace_root):
                        return {"behavior": "deny", "message": "Path denied: escapes workspace root", "interrupt": False}
        return {"behavior": "allow", "updated_input": None, "updated_permissions": None}

    return can_use_tool


class ClaudeSdkAdapter:
    def __init__(self, options: ClaudeRuntimeOptions, query_callable: QueryCallable | None = None):
        self._options = options
        self._base_options_dict = asdict(options)
        self._query_callable = query_callable
        self._cached_query_callable: QueryCallable | None = None
        self._cached_claude_options_cls: Any = None
        self._sdk_resolved = False

    async def execute(self, request: AgentExecutionRequest) -> AgentExecutionResult:
        query_callable = self._query_callable or self._resolve_query_callable()
        resume_override = request.metadata.get("resume_session_id")
        resolved_resume = str(resume_override) if isinstance(resume_override, str) and resume_override else None
        options = self._build_sdk_options(request.workspace, resume_override=resolved_resume)
        _LOGGER.info(
            "agent_runtime_execute provider=claude workspace=%s continue_conversation=%s resume_set=%s",
            request.workspace.resolve(),
            self._options.continue_conversation,
            bool(resolved_resume or self._options.resume),
        )
        message_count = 0
        last_text = ""
        final_text = ""
        final_metadata: dict[str, Any] = {}
        try:
            async for message in query_callable(prompt=request.prompt, options=options):
                message_count += 1
                message_text = self._extract_text(message)
                if message_text:
                    last_text = message_text
                if self._is_result_message(message):
                    final_text = message_text or last_text
                    final_metadata = self._extract_result_metadata(message)
            resolved_text = final_text or last_text
            return AgentExecutionResult(
                text=resolved_text,
                provider="claude",
                metadata={
                    "message_count": message_count,
                    "session_mode": self._session_mode(),
                    **final_metadata,
                },
            )
        except Exception as exc:
            _LOGGER.exception("agent_runtime_execute_failed provider=claude error_type=%s", type(exc).__name__)
            raise AgentRuntimeExecutionError("Claude runtime execution failed. Check runtime logs for details.") from exc

    def _resolve_query_callable(self) -> QueryCallable:
        if self._cached_query_callable is not None:
            return self._cached_query_callable
        try:
            sdk_module = import_module("claude_agent_sdk")
        except ImportError as exc:
            raise AgentRuntimeExecutionError(
                "Claude runtime requires claude-agent-sdk. Install it and retry."
            ) from exc
        query_callable = getattr(sdk_module, "query", None)
        if not callable(query_callable):
            raise AgentRuntimeExecutionError("claude-agent-sdk.query is not available.")
        self._cached_query_callable = query_callable
        return query_callable

    def _build_sdk_options(self, workspace: Any, *, resume_override: str | None = None) -> Any:
        options_payload = dict(self._base_options_dict)
        options_payload["cwd"] = workspace
        options_payload["agents"] = options_payload.pop("sub_agents")
        if resume_override:
            options_payload["resume"] = resume_override
        if not options_payload["tools"]:
            options_payload["tools"] = None
        if not options_payload["hooks"]:
            options_payload["hooks"] = None
        if not options_payload["mcp_servers"]:
            options_payload["mcp_servers"] = {}
        # Remove `skills` from options_payload as it's not supported by claude-agent-sdk
        options_payload.pop("skills", None)
        options_payload.pop("session_persistence_enabled", None)
        options_payload.pop("session_scope", None)
        tool_perms = options_payload.pop("tool_permissions", None)
        if options_payload.pop("restrict_to_workspace", False):
            options_payload["can_use_tool"] = _make_workspace_guard(
                workspace,
                tool_permissions=tool_perms if isinstance(tool_perms, ToolPermissionConfig) else None,
            )
        if not self._sdk_resolved:
            try:
                sdk_module = import_module("claude_agent_sdk")
                self._cached_claude_options_cls = getattr(sdk_module, "ClaudeAgentOptions", None)
            except ImportError:
                self._cached_claude_options_cls = None
            self._sdk_resolved = True
        if self._cached_claude_options_cls is None:
            return options_payload
        return self._cached_claude_options_cls(**options_payload)

    def _extract_text(self, message: Any) -> str:
        for key in _TEXT_KEYS:
            value = _get(message, key)
            if isinstance(value, str):
                return value
        content = _get(message, "content")
        if isinstance(content, list):
            blocks: list[str] = []
            for block in content:
                block_text = _get(block, "text")
                if isinstance(block_text, str):
                    blocks.append(block_text)
            return "".join(blocks)
        return ""

    def _extract_result_metadata(self, message: Any) -> dict[str, Any]:
        metadata: dict[str, Any] = {}
        for key in ("usage", "session_id", "stop_reason", "duration_ms", "cost_usd"):
            value = _get(message, key)
            if value is not None:
                metadata[key] = value
        return metadata

    def _is_result_message(self, message: Any) -> bool:
        if isinstance(message, dict):
            message_type = message.get("type") or message.get("message_type")
            return isinstance(message_type, str) and message_type.lower() == "result"
        return type(message).__name__.lower().endswith("resultmessage")

    def _session_mode(self) -> str:
        if self._options.resume:
            return "resume"
        if self._options.continue_conversation:
            return "continue"
        return "one_off"
