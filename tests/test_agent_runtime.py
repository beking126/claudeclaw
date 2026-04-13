import asyncio
import json
from pathlib import Path
from typing import Any

import pytest


def test_factory_selects_claude_provider(tmp_path: Path):
    from claudebot_gateway.agent_runtime import ClaudeSdkAdapter, create_agent_runtime
    from claudebot_gateway.config import GatewayConfig

    runtime = create_agent_runtime(GatewayConfig(workspace_root=tmp_path / "workspaces"))
    assert isinstance(runtime, ClaudeSdkAdapter)


def test_factory_rejects_unknown_provider(tmp_path: Path):
    from claudebot_gateway.agent_runtime import UnsupportedRuntimeProviderError, create_agent_runtime
    from claudebot_gateway.config import AgentRuntimeConfig, GatewayConfig

    config = GatewayConfig(workspace_root=tmp_path / "workspaces", agent_runtime=AgentRuntimeConfig(provider="unknown"))
    with pytest.raises(UnsupportedRuntimeProviderError) as exc_info:
        create_agent_runtime(config)
    assert "Unsupported agent runtime provider 'unknown'" in str(exc_info.value)


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

    with pytest.raises(AgentRuntimeExecutionError) as exc_info:
        asyncio.run(run())
    assert "secret-token-123" not in str(exc_info.value)
    assert "Claude runtime execution failed" in str(exc_info.value)


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


def test_workspace_guard_denies_path_escape(tmp_path: Path):
    from claudebot_gateway.agent_runtime.claude_adapter import _make_workspace_guard

    workspace = tmp_path / "workspaces" / "main"
    workspace.mkdir(parents=True, exist_ok=True)
    guard = _make_workspace_guard(workspace)

    async def _check() -> tuple[dict, dict]:
        deny = await guard("Read", {"file_path": "../../etc/passwd"}, None)
        allow = await guard("Read", {"file_path": "subdir/file.txt"}, None)
        return deny, allow

    deny, allow = asyncio.run(_check())
    assert deny["behavior"] == "deny"
    assert "escapes" in deny["message"]
    assert allow["behavior"] == "allow"


def test_workspace_guard_denies_shell_tools(tmp_path: Path):
    from claudebot_gateway.agent_runtime.claude_adapter import _make_workspace_guard

    workspace = tmp_path / "workspaces" / "main"
    workspace.mkdir(parents=True, exist_ok=True)
    guard = _make_workspace_guard(workspace)

    async def _check() -> dict:
        return await guard("Bash", {"command": "ls /"}, None)

    result = asyncio.run(_check())
    assert result["behavior"] == "deny"
    assert "Shell access denied" in result["message"]


def test_workspace_guard_allows_workspace_paths(tmp_path: Path):
    from claudebot_gateway.agent_runtime.claude_adapter import _make_workspace_guard

    workspace = tmp_path / "workspaces" / "main"
    workspace.mkdir(parents=True, exist_ok=True)
    guard = _make_workspace_guard(workspace)

    async def _check() -> dict:
        return await guard("Write", {"file_path": str(workspace / "output.txt"), "content": "ok"}, None)

    result = asyncio.run(_check())
    assert result["behavior"] == "allow"


def test_restrict_to_workspace_wires_guard_to_sdk_options(tmp_path: Path):
    from claudebot_gateway.agent_runtime import AgentExecutionRequest, ClaudeSdkAdapter
    from claudebot_gateway.config import ClaudeRuntimeOptions

    captured: dict[str, Any] = {}

    async def fake_query(prompt: str, options: Any):
        captured["options"] = options
        yield {"type": "result", "result": "ok"}

    async def run() -> Any:
        workspace = tmp_path / "ws"
        workspace.mkdir(parents=True, exist_ok=True)
        adapter = ClaudeSdkAdapter(
            options=ClaudeRuntimeOptions(restrict_to_workspace=True),
            query_callable=fake_query,
        )
        await adapter.execute(AgentExecutionRequest(prompt="test", workspace=workspace))
        return captured["options"]

    options = asyncio.run(run())
    can_use_tool = options["can_use_tool"] if isinstance(options, dict) else getattr(options, "can_use_tool", None)
    assert callable(can_use_tool)


def test_restrict_to_workspace_config_parsing(tmp_path: Path, monkeypatch):
    from claudebot_gateway.config import load_gateway_config

    config_dir = tmp_path / ".claudebot"
    config_dir.mkdir(parents=True, exist_ok=True)
    (config_dir / "config.json").write_text(
        '{"agent_runtime":{"claude":{"restrict_to_workspace":true}}}',
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
    config = load_gateway_config()
    assert config.agent_runtime.claude.restrict_to_workspace is True


def test_tool_permissions_denied_tools(tmp_path: Path):
    from claudebot_gateway.agent_runtime.claude_adapter import _make_workspace_guard
    from claudebot_gateway.config import ToolPermissionConfig

    workspace = tmp_path / "ws"
    workspace.mkdir(parents=True, exist_ok=True)
    perms = ToolPermissionConfig(denied_tools=["NotebookEdit", "Write"])
    guard = _make_workspace_guard(workspace, tool_permissions=perms)

    async def _check() -> tuple[dict, dict, dict]:
        deny_write = await guard("Write", {"file_path": "ok.txt"}, None)
        deny_nb = await guard("NotebookEdit", {"notebook_path": "a.ipynb"}, None)
        allow_read = await guard("Read", {"file_path": "ok.txt"}, None)
        return deny_write, deny_nb, allow_read

    deny_write, deny_nb, allow_read = asyncio.run(_check())
    assert deny_write["behavior"] == "deny"
    assert "denied by configuration" in deny_write["message"]
    assert deny_nb["behavior"] == "deny"
    assert allow_read["behavior"] == "allow"


def test_tool_permissions_allowed_tools_whitelist(tmp_path: Path):
    from claudebot_gateway.agent_runtime.claude_adapter import _make_workspace_guard
    from claudebot_gateway.config import ToolPermissionConfig

    workspace = tmp_path / "ws"
    workspace.mkdir(parents=True, exist_ok=True)
    perms = ToolPermissionConfig(allowed_tools=["Read", "Grep", "Glob"])
    guard = _make_workspace_guard(workspace, tool_permissions=perms)

    async def _check() -> tuple[dict, dict]:
        allow_grep = await guard("Grep", {"pattern": "foo"}, None)
        deny_write = await guard("Write", {"file_path": "out.txt"}, None)
        return allow_grep, deny_write

    allow_grep, deny_write = asyncio.run(_check())
    assert allow_grep["behavior"] == "allow"
    assert deny_write["behavior"] == "deny"
    assert "not in the allowed list" in deny_write["message"]


def test_tool_permissions_shell_allowed_patterns(tmp_path: Path):
    from claudebot_gateway.agent_runtime.claude_adapter import _make_workspace_guard
    from claudebot_gateway.config import ToolPermissionConfig

    workspace = tmp_path / "ws"
    workspace.mkdir(parents=True, exist_ok=True)
    perms = ToolPermissionConfig(allowed_shell_patterns=["git status", "git log*", "ls *"])
    guard = _make_workspace_guard(workspace, tool_permissions=perms)

    async def _check() -> tuple[dict, dict, dict]:
        allow_git_status = await guard("Bash", {"command": "git status"}, None)
        allow_git_log = await guard("Bash", {"command": "git log --oneline -5"}, None)
        deny_rm = await guard("Bash", {"command": "rm -rf /"}, None)
        return allow_git_status, allow_git_log, deny_rm

    allow_git_status, allow_git_log, deny_rm = asyncio.run(_check())
    assert allow_git_status["behavior"] == "allow"
    assert allow_git_log["behavior"] == "allow"
    assert deny_rm["behavior"] == "deny"
    assert "Shell access denied" in deny_rm["message"]


def test_tool_permissions_config_parsing(tmp_path: Path, monkeypatch):
    from claudebot_gateway.config import load_gateway_config

    config_dir = tmp_path / ".claudebot"
    config_dir.mkdir(parents=True, exist_ok=True)
    (config_dir / "config.json").write_text(
        json.dumps({
            "agent_runtime": {
                "claude": {
                    "restrict_to_workspace": True,
                    "tool_permissions": {
                        "allowed_shell_patterns": ["git status", "ls *"],
                        "denied_tools": ["NotebookEdit"],
                        "allowed_tools": [],
                    },
                }
            }
        }),
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
    config = load_gateway_config()
    perms = config.agent_runtime.claude.tool_permissions
    assert perms.allowed_shell_patterns == ["git status", "ls *"]
    assert perms.denied_tools == ["NotebookEdit"]
    assert perms.allowed_tools == []


def test_denied_tools_takes_priority_over_shell_patterns(tmp_path: Path):
    from claudebot_gateway.agent_runtime.claude_adapter import _make_workspace_guard
    from claudebot_gateway.config import ToolPermissionConfig

    workspace = tmp_path / "ws"
    workspace.mkdir(parents=True, exist_ok=True)
    perms = ToolPermissionConfig(
        denied_tools=["Bash"],
        allowed_shell_patterns=["git status"],
    )
    guard = _make_workspace_guard(workspace, tool_permissions=perms)

    async def _check() -> dict:
        return await guard("Bash", {"command": "git status"}, None)

    result = asyncio.run(_check())
    assert result["behavior"] == "deny"
    assert "denied by configuration" in result["message"]
