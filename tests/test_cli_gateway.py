from pathlib import Path

from claudebot_gateway.agent_runtime import AgentExecutionResult


class _FakeRuntime:
    def __init__(self):
        self.workspace: Path | None = None
        self.prompt: str | None = None

    async def execute(self, request):
        self.workspace = request.workspace
        self.prompt = request.prompt
        return AgentExecutionResult(text="runtime-output", provider="test")


def test_status_command_returns_ok():
    from claudebot_gateway.cli import main

    exit_code = main(["status"])
    assert exit_code == 0


def test_status_text_includes_signal_fields():
    from claudebot_gateway.cli import status_text

    line = status_text(
        {
            "runtime": {"running": False, "worker_count": 5, "unhandled_errors": 0},
            "signals": {"inbound_queue_depth": 2, "outbound_queue_depth": 3, "due_cron_jobs": 1},
        }
    )
    assert "in=2" in line
    assert "out=3" in line
    assert "due_cron=1" in line


def test_gateway_once_creates_runtime_artifacts(tmp_path: Path):
    from claudebot_gateway.cli import main

    workspace_root = tmp_path / "workspaces"
    db_path = tmp_path / "state" / "gateway.db"
    exit_code = main(
        [
            "gateway",
            "--once",
            "--workspace-root",
            str(workspace_root),
            "--db-path",
            str(db_path),
            "--demo-text",
            "hello",
        ]
    )
    assert exit_code == 0
    assert (workspace_root / "main").exists()
    assert db_path.exists()


def test_status_verbose_emits_debug_and_key_paths(tmp_path: Path, capsys):
    from claudebot_gateway.cli import main

    workspace_root = tmp_path / "workspaces"
    db_path = tmp_path / "state" / "gateway.db"
    exit_code = main(
        [
            "--verbose",
            "status",
            "--workspace-root",
            str(workspace_root),
            "--db-path",
            str(db_path),
        ]
    )
    captured = capsys.readouterr()
    assert exit_code == 0
    assert "DEBUG" in captured.err
    assert "workspace_root=" in captured.err
    assert "sqlite_path=" in captured.err


def test_agent_command_defaults_to_main_workspace(tmp_path: Path, capsys, monkeypatch):
    from claudebot_gateway.cli import main

    fake_runtime = _FakeRuntime()
    monkeypatch.setattr("claudebot_gateway.runtime.create_agent_runtime", lambda config: fake_runtime)
    workspace_root = tmp_path / "workspaces"
    db_path = tmp_path / "state" / "gateway.db"
    exit_code = main(
        [
            "agent",
            "--prompt",
            "hello",
            "--workspace-root",
            str(workspace_root),
            "--db-path",
            str(db_path),
        ]
    )
    captured = capsys.readouterr()
    assert exit_code == 0
    assert captured.out.strip() == "runtime-output"
    assert fake_runtime.prompt == "hello"
    assert fake_runtime.workspace == workspace_root / "main"
    assert (workspace_root / "main").exists()


def test_agent_command_supports_workspace_override(tmp_path: Path, capsys, monkeypatch):
    from claudebot_gateway.cli import main

    fake_runtime = _FakeRuntime()
    monkeypatch.setattr("claudebot_gateway.runtime.create_agent_runtime", lambda config: fake_runtime)
    workspace_root = tmp_path / "workspaces"
    db_path = tmp_path / "state" / "gateway.db"
    exit_code = main(
        [
            "agent",
            "--prompt",
            "hello",
            "--workspace-root",
            str(workspace_root),
            "--workspace",
            "custom-room",
            "--db-path",
            str(db_path),
        ]
    )
    captured = capsys.readouterr()
    assert exit_code == 0
    assert captured.out.strip() == "runtime-output"
    assert fake_runtime.workspace == workspace_root / "custom-room"


def test_status_command_loads_local_config_json(tmp_path: Path, monkeypatch):
    from claudebot_gateway.cli import main

    config_dir = tmp_path / "claudebot"
    config_dir.mkdir(parents=True, exist_ok=True)
    (config_dir / "config.json").write_text(
        '{"channels":{"telegram":{"enabled":true,"bot_token":"json-token"}}}',
        encoding="utf-8",
    )

    class _FakeApp:
        last_config = None

        def __init__(self, *, config):
            _FakeApp.last_config = config

        def status(self):
            return {
                "runtime": {"running": False, "worker_count": 0, "unhandled_errors": 0},
                "signals": {},
            }

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("claudebot_gateway.cli.GatewayApp", _FakeApp)
    exit_code = main(["status"])
    assert exit_code == 0
    assert _FakeApp.last_config is not None
    assert _FakeApp.last_config.channels.telegram.enabled is True
    assert _FakeApp.last_config.channels.telegram.bot_token == "json-token"
