import asyncio
from pathlib import Path
from typing import Any


def test_factory_selects_claude_provider(tmp_path: Path):
    from claudebot_gateway.agent_runtime import ClaudeSdkAdapter, create_agent_runtime
    from claudebot_gateway.config import GatewayConfig

    runtime = create_agent_runtime(GatewayConfig(workspace_root=tmp_path / "workspaces"))
    assert isinstance(runtime, ClaudeSdkAdapter)


def test_factory_rejects_unknown_provider(tmp_path: Path):
    from claudebot_gateway.agent_runtime import UnsupportedRuntimeProviderError, create_agent_runtime
    from claudebot_gateway.config import AgentRuntimeConfig, GatewayConfig

    config = GatewayConfig(workspace_root=tmp_path / "workspaces", agent_runtime=AgentRuntimeConfig(provider="unknown"))
    try:
        create_agent_runtime(config)
        assert False
    except UnsupportedRuntimeProviderError as exc:
        assert "Unsupported agent runtime provider 'unknown'" in str(exc)


def test_claude_adapter_executes_and_propagates_sdk_options(tmp_path: Path):
    from claudebot_gateway.agent_runtime import AgentExecutionRequest, ClaudeSdkAdapter
    from claudebot_gateway.config import ClaudeRuntimeOptions

    captured: dict[str, Any] = {}

    async def fake_query(prompt: str, options: Any):
        captured["prompt"] = prompt
        captured["options"] = options
        yield {"type": "assistant", "content": [{"text": "draft"}]}
        yield {"type": "result", "result": "final response", "session_id": "s-1", "usage": {"input_tokens": 10}}

    async def run() -> tuple[dict[str, Any], Any]:
        workspace = tmp_path / "workspaces" / "main"
        workspace.mkdir(parents=True, exist_ok=True)
        adapter = ClaudeSdkAdapter(
            options=ClaudeRuntimeOptions(
                tools=["Read", "Write"],
                mcp_servers={"context7": {"type": "stdio", "command": "context7"}},
                continue_conversation=True,
                sub_agents={
                    "reviewer": {
                        "description": "reviews code",
                        "prompt": "review the patch",
                    }
                },
                setting_sources=["project"],
            ),
            query_callable=fake_query,
        )
        result = await adapter.execute(AgentExecutionRequest(prompt="hello", workspace=workspace))
        return captured, result

    call, result = asyncio.run(run())
    assert call["prompt"] == "hello"
    assert result.text == "final response"
    assert result.provider == "claude"
    assert result.metadata["session_mode"] == "continue"
    assert result.metadata["session_id"] == "s-1"
    assert result.metadata["usage"]["input_tokens"] == 10
    options = call["options"]
    tools = options["tools"] if isinstance(options, dict) else getattr(options, "tools")
    mcp_servers = options["mcp_servers"] if isinstance(options, dict) else getattr(options, "mcp_servers")
    agents = options["agents"] if isinstance(options, dict) else getattr(options, "agents")
    setting_sources = options["setting_sources"] if isinstance(options, dict) else getattr(options, "setting_sources")
    cwd = options["cwd"] if isinstance(options, dict) else getattr(options, "cwd")
    assert tools == ["Read", "Write"]
    assert mcp_servers["context7"]["command"] == "context7"
    assert agents["reviewer"]["description"] == "reviews code"
    assert setting_sources == ["project"]
    assert cwd == tmp_path / "workspaces" / "main"


def test_claude_adapter_maps_runtime_errors_without_secret_leaks(tmp_path: Path):
    from claudebot_gateway.agent_runtime import AgentExecutionRequest, AgentRuntimeExecutionError, ClaudeSdkAdapter
    from claudebot_gateway.config import ClaudeRuntimeOptions

    async def failing_query(prompt: str, options: Any):
        _ = (prompt, options)
        raise RuntimeError("secret-token-123")
        yield

    async def run() -> None:
        adapter = ClaudeSdkAdapter(options=ClaudeRuntimeOptions(), query_callable=failing_query)
        await adapter.execute(AgentExecutionRequest(prompt="hello", workspace=tmp_path))

    try:
        asyncio.run(run())
        assert False
    except AgentRuntimeExecutionError as exc:
        assert "secret-token-123" not in str(exc)
        assert "Claude runtime execution failed" in str(exc)


def test_claude_adapter_supports_keyword_only_query_signature(tmp_path: Path):
    from claudebot_gateway.agent_runtime import AgentExecutionRequest, ClaudeSdkAdapter
    from claudebot_gateway.config import ClaudeRuntimeOptions

    async def keyword_only_query(*, prompt: str, options: Any):
        _ = options
        yield {"type": "result", "result": f"echo:{prompt}"}

    async def run() -> str:
        adapter = ClaudeSdkAdapter(options=ClaudeRuntimeOptions(), query_callable=keyword_only_query)
        result = await adapter.execute(AgentExecutionRequest(prompt="hello", workspace=tmp_path))
        return result.text

    text = asyncio.run(run())
    assert text == "echo:hello"


def test_claude_adapter_applies_request_resume_override(tmp_path: Path):
    from claudebot_gateway.agent_runtime import AgentExecutionRequest, ClaudeSdkAdapter
    from claudebot_gateway.config import ClaudeRuntimeOptions

    captured: dict[str, Any] = {}

    async def fake_query(prompt: str, options: Any):
        captured["prompt"] = prompt
        captured["options"] = options
        yield {"type": "result", "result": "ok", "session_id": "s-2"}

    async def run() -> Any:
        adapter = ClaudeSdkAdapter(
            options=ClaudeRuntimeOptions(resume="configured-resume", session_persistence_enabled=True),
            query_callable=fake_query,
        )
        await adapter.execute(
            AgentExecutionRequest(
                prompt="hello",
                workspace=tmp_path,
                metadata={"resume_session_id": "persisted-resume"},
            )
        )
        return captured["options"]

    options = asyncio.run(run())
    resume_value = options["resume"] if isinstance(options, dict) else getattr(options, "resume")
    assert resume_value == "persisted-resume"
