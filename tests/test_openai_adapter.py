import asyncio
from pathlib import Path
from typing import Any

import pytest


def test_factory_selects_openai_provider(tmp_path: Path):
    from claudebot_gateway.agent_runtime import create_agent_runtime
    from claudebot_gateway.agent_runtime.openai_adapter import OpenAIAdapter
    from claudebot_gateway.config import AgentRuntimeConfig, GatewayConfig

    config = GatewayConfig(
        workspace_root=tmp_path / "workspaces",
        agent_runtime=AgentRuntimeConfig(provider="openai"),
    )
    runtime = create_agent_runtime(config)
    assert isinstance(runtime, OpenAIAdapter)


def test_factory_rejects_unknown_provider(tmp_path: Path):
    from claudebot_gateway.agent_runtime import UnsupportedRuntimeProviderError, create_agent_runtime
    from claudebot_gateway.config import AgentRuntimeConfig, GatewayConfig

    config = GatewayConfig(
        workspace_root=tmp_path / "workspaces",
        agent_runtime=AgentRuntimeConfig(provider="unknown"),
    )
    with pytest.raises(UnsupportedRuntimeProviderError) as exc_info:
        create_agent_runtime(config)
    assert "Unsupported agent runtime provider 'unknown'" in str(exc_info.value)


def test_openai_adapter_executes_with_mock_client(tmp_path: Path):
    from claudebot_gateway.agent_runtime import AgentExecutionRequest
    from claudebot_gateway.agent_runtime.openai_adapter import OpenAIAdapter, OpenAIRuntimeOptions

    class _FakeMessage:
        def __init__(self, content: str):
            self.content = content
            self.role = "assistant"

    class _FakeChoice:
        def __init__(self, message: _FakeMessage):
            self.message = message
            self.finish_reason = "stop"

    class _FakeUsage:
        prompt_tokens = 10
        completion_tokens = 20
        total_tokens = 30

    class _FakeResponse:
        choices = [_FakeChoice(_FakeMessage("Hello from OpenAI!"))]
        model = "gpt-4o"
        usage = _FakeUsage()

    class _FakeCompletions:
        async def create(self, **kwargs: Any) -> _FakeResponse:
            return _FakeResponse()

    class _FakeChat:
        completions = _FakeCompletions()

    class _FakeClient:
        chat = _FakeChat()

    async def _run() -> Any:
        options = OpenAIRuntimeOptions(model="gpt-4o", system_prompt="You are helpful.")
        adapter = OpenAIAdapter(options=options, client=_FakeClient())
        result = await adapter.execute(
            AgentExecutionRequest(prompt="hello", workspace=tmp_path)
        )
        return result

    result = asyncio.run(_run())
    assert result.text == "Hello from OpenAI!"
    assert result.provider == "openai"
    assert result.metadata["model"] == "gpt-4o"
    assert result.metadata["finish_reason"] == "stop"
    assert result.metadata["usage"]["total_tokens"] == 30


def test_openai_adapter_sanitizes_errors(tmp_path: Path):
    from claudebot_gateway.agent_runtime import AgentExecutionRequest
    from claudebot_gateway.agent_runtime.claude_adapter import AgentRuntimeExecutionError
    from claudebot_gateway.agent_runtime.openai_adapter import OpenAIAdapter, OpenAIRuntimeOptions

    class _FakeCompletions:
        async def create(self, **kwargs: Any) -> None:
            raise RuntimeError("secret-api-key-123")

    class _FakeChat:
        completions = _FakeCompletions()

    class _FakeClient:
        chat = _FakeChat()

    async def _run() -> None:
        options = OpenAIRuntimeOptions()
        adapter = OpenAIAdapter(options=options, client=_FakeClient())
        await adapter.execute(AgentExecutionRequest(prompt="hello", workspace=tmp_path))

    with pytest.raises(AgentRuntimeExecutionError) as exc_info:
        asyncio.run(_run())
    assert "secret-api-key-123" not in str(exc_info.value)
    assert "OpenAI runtime execution failed" in str(exc_info.value)


def test_openai_config_parsing(tmp_path: Path, monkeypatch):
    from claudebot_gateway.config import load_gateway_config

    config_dir = tmp_path / ".claudebot"
    config_dir.mkdir(parents=True, exist_ok=True)
    (config_dir / "config.json").write_text(
        '{"agent_runtime":{"provider":"openai","claude":{"model":"gpt-4o-mini"}}}',
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
    config = load_gateway_config()
    assert config.agent_runtime.provider == "openai"
