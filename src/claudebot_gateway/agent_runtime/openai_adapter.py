"""OpenAI-compatible runtime adapter.

Provides a thin wrapper around the ``openai`` SDK so the gateway can
route prompts to any OpenAI-compatible endpoint (OpenAI, Azure OpenAI,
local models via compatible APIs) when the provider is set to ``openai``
in configuration.
"""

import logging
from importlib import import_module
from typing import Any

from claudebot_gateway.agent_runtime.claude_adapter import AgentRuntimeExecutionError
from claudebot_gateway.agent_runtime.types import AgentExecutionRequest, AgentExecutionResult

_LOGGER = logging.getLogger("claudebot_gateway.agent_runtime.openai")


class OpenAIRuntimeOptions:
    """Configuration for the OpenAI runtime adapter."""

    __slots__ = ("model", "base_url", "api_key", "max_tokens", "temperature", "system_prompt")

    def __init__(
        self,
        *,
        model: str = "gpt-4o",
        base_url: str | None = None,
        api_key: str | None = None,
        max_tokens: int | None = None,
        temperature: float | None = None,
        system_prompt: str | None = None,
    ) -> None:
        self.model = model
        self.base_url = base_url
        self.api_key = api_key
        self.max_tokens = max_tokens
        self.temperature = temperature
        self.system_prompt = system_prompt


class OpenAIAdapter:
    """Agent runtime backed by the OpenAI chat completions API."""

    def __init__(self, options: OpenAIRuntimeOptions, *, client: Any = None) -> None:
        self._options = options
        self._client = client
        self._client_resolved = client is not None

    async def execute(self, request: AgentExecutionRequest) -> AgentExecutionResult:
        client = self._resolve_client()
        messages: list[dict[str, str]] = []
        if self._options.system_prompt:
            messages.append({"role": "system", "content": self._options.system_prompt})
        messages.append({"role": "user", "content": request.prompt})

        kwargs: dict[str, Any] = {
            "model": self._options.model,
            "messages": messages,
        }
        if self._options.max_tokens is not None:
            kwargs["max_tokens"] = self._options.max_tokens
        if self._options.temperature is not None:
            kwargs["temperature"] = self._options.temperature

        _LOGGER.info(
            "agent_runtime_execute provider=openai workspace=%s model=%s",
            request.workspace.resolve(),
            self._options.model,
        )
        try:
            response = await client.chat.completions.create(**kwargs)
            text = ""
            choice = response.choices[0] if response.choices else None
            if choice and choice.message and choice.message.content:
                text = choice.message.content
            usage = None
            if response.usage:
                usage = {
                    "prompt_tokens": response.usage.prompt_tokens,
                    "completion_tokens": response.usage.completion_tokens,
                    "total_tokens": response.usage.total_tokens,
                }
            return AgentExecutionResult(
                text=text,
                provider="openai",
                metadata={
                    "model": response.model,
                    "finish_reason": choice.finish_reason if choice else None,
                    "usage": usage,
                },
            )
        except Exception as exc:
            _LOGGER.exception("agent_runtime_execute_failed provider=openai error_type=%s", type(exc).__name__)
            raise AgentRuntimeExecutionError("OpenAI runtime execution failed. Check runtime logs for details.") from exc

    def _resolve_client(self) -> Any:
        if self._client_resolved:
            return self._client
        try:
            openai_module = import_module("openai")
        except ImportError as exc:
            raise AgentRuntimeExecutionError(
                "OpenAI runtime requires the openai package. Install it with: pip install openai"
            ) from exc
        client_kwargs: dict[str, Any] = {}
        if self._options.api_key:
            client_kwargs["api_key"] = self._options.api_key
        if self._options.base_url:
            client_kwargs["base_url"] = self._options.base_url
        self._client = openai_module.AsyncOpenAI(**client_kwargs)
        self._client_resolved = True
        return self._client
