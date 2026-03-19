import logging
from collections.abc import AsyncIterator, Callable
from dataclasses import asdict
from importlib import import_module
from typing import Any

from claudebot_gateway.agent_runtime.types import AgentExecutionRequest, AgentExecutionResult
from claudebot_gateway.config import ClaudeRuntimeOptions

_LOGGER = logging.getLogger("claudebot_gateway.agent_runtime.claude")

QueryCallable = Callable[..., AsyncIterator[Any]]


class AgentRuntimeExecutionError(RuntimeError):
    pass


class ClaudeSdkAdapter:
    def __init__(self, options: ClaudeRuntimeOptions, query_callable: QueryCallable | None = None):
        self._options = options
        self._query_callable = query_callable

    async def execute(self, request: AgentExecutionRequest) -> AgentExecutionResult:
        query_callable = self._query_callable or self._resolve_query_callable()
        options = self._build_sdk_options(request.workspace)
        _LOGGER.info(
            "agent_runtime_execute provider=claude workspace=%s continue_conversation=%s resume_set=%s",
            request.workspace.resolve(),
            self._options.continue_conversation,
            bool(self._options.resume),
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
        try:
            sdk_module = import_module("claude_agent_sdk")
        except ImportError as exc:
            raise AgentRuntimeExecutionError(
                "Claude runtime requires claude-agent-sdk. Install it and retry."
            ) from exc
        query_callable = getattr(sdk_module, "query", None)
        if not callable(query_callable):
            raise AgentRuntimeExecutionError("claude-agent-sdk.query is not available.")
        return query_callable

    def _build_sdk_options(self, workspace: Any) -> Any:
        options_payload = asdict(self._options)
        options_payload["cwd"] = workspace
        options_payload["agents"] = options_payload.pop("sub_agents")
        if not options_payload["tools"]:
            options_payload["tools"] = None
        if not options_payload["hooks"]:
            options_payload["hooks"] = None
        if not options_payload["mcp_servers"]:
            options_payload["mcp_servers"] = {}
        # Remove `skills` from options_payload as it's not supported by claude-agent-sdk
        options_payload.pop("skills", None)
        try:
            sdk_module = import_module("claude_agent_sdk")
        except ImportError:
            return options_payload
        claude_options = getattr(sdk_module, "ClaudeAgentOptions", None)
        if claude_options is None:
            return options_payload
        return claude_options(**options_payload)

    def _extract_text(self, message: Any) -> str:
        if isinstance(message, dict):
            for key in ("result", "final_response", "response", "text", "output_text"):
                value = message.get(key)
                if isinstance(value, str):
                    return value
            content = message.get("content")
            if isinstance(content, list):
                blocks: list[str] = []
                for block in content:
                    if isinstance(block, dict):
                        block_text = block.get("text")
                        if isinstance(block_text, str):
                            blocks.append(block_text)
                return "".join(blocks)
            return ""
        for attr in ("result", "final_response", "response", "text", "output_text"):
            value = getattr(message, attr, None)
            if isinstance(value, str):
                return value
        content = getattr(message, "content", None)
        if isinstance(content, list):
            content_blocks: list[str] = []
            for block in content:
                block_text = getattr(block, "text", None)
                if isinstance(block_text, str):
                    content_blocks.append(block_text)
            return "".join(content_blocks)
        return ""

    def _extract_result_metadata(self, message: Any) -> dict[str, Any]:
        if isinstance(message, dict):
            metadata: dict[str, Any] = {}
            for key in ("usage", "session_id", "stop_reason", "duration_ms", "cost_usd"):
                if key in message:
                    metadata[key] = message[key]
            return metadata
        metadata = {}
        for key in ("usage", "session_id", "stop_reason", "duration_ms", "cost_usd"):
            value = getattr(message, key, None)
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
