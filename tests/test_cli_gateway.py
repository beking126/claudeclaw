from pathlib import Path

def test_status_command_returns_ok_without_running_gateway():
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


def test_status_text_includes_channel_status():
    from claudebot_gateway.cli import status_text

    line = status_text(
        {
            "runtime": {"running": True, "worker_count": 5, "unhandled_errors": 0},
            "signals": {
                "inbound_queue_depth": 0,
                "outbound_queue_depth": 0,
                "due_cron_jobs": 0,
                "channels": {
                    "cli": {"state": "running", "last_error": None, "reconnect_attempts": 0},
                    "telegram": {"state": "degraded", "last_error": "connection timeout", "reconnect_attempts": 3},
                },
            },
        }
    )
    assert "channels=[" in line
    assert "cli:running" in line
    assert "telegram:degraded" in line
    assert "err=connection timeout" in line


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


def test_status_verbose_emits_debug_logs(capsys):
    from claudebot_gateway.cli import main

    exit_code = main(["--verbose", "status"])
    captured = capsys.readouterr()
    assert exit_code == 0
    assert "DEBUG" in captured.err


def test_agent_command_defaults_to_main_workspace(tmp_path: Path, capsys, monkeypatch, cli_capture_runtime):
    from claudebot_gateway.cli import main

    monkeypatch.setattr("claudebot_gateway.runtime.create_agent_runtime", lambda config: cli_capture_runtime)
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
    assert cli_capture_runtime.prompt == "hello"
    assert cli_capture_runtime.workspace == workspace_root / "main"
    assert (workspace_root / "main").exists()


def test_agent_command_supports_workspace_override(tmp_path: Path, capsys, monkeypatch, cli_capture_runtime):
    from claudebot_gateway.cli import main

    monkeypatch.setattr("claudebot_gateway.runtime.create_agent_runtime", lambda config: cli_capture_runtime)
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
    assert cli_capture_runtime.workspace == workspace_root / "custom-room"


def test_status_command_loads_local_config_json(tmp_path: Path, monkeypatch):
    from claudebot_gateway.cli import main

    config_dir = tmp_path / "claudebot"
    config_dir.mkdir(parents=True, exist_ok=True)
    (config_dir / "config.json").write_text(
        '{"channels":{"telegram":{"enabled":true,"bot_token":"json-token"}}}',
        encoding="utf-8",
    )

    monkeypatch.chdir(tmp_path)
    exit_code = main(["status"])
    assert exit_code == 0


def test_status_command_queries_live_gateway(capsys, monkeypatch):
    from claudebot_gateway.cli import main

    live_snapshot = {
        "runtime": {"started": True, "running": True, "stopped": False, "worker_count": 4, "unhandled_errors": 0},
        "signals": {
            "inbound_queue_depth": 1,
            "outbound_queue_depth": 0,
            "due_cron_jobs": 2,
            "channels": {"cli": {"state": "running", "last_error": None, "reconnect_attempts": 0}},
        },
    }

    monkeypatch.setattr(
        "claudebot_gateway.cli._fetch_live_status",
        lambda host, port: live_snapshot,
    )
    exit_code = main(["status"])
    captured = capsys.readouterr()
    assert exit_code == 0
    assert "gateway:running" in captured.out
    assert "workers=4" in captured.out
    assert "cli:running" in captured.out


def test_status_command_falls_back_when_gateway_unreachable(capsys, monkeypatch):
    from claudebot_gateway.cli import main

    monkeypatch.setattr(
        "claudebot_gateway.cli._fetch_live_status",
        lambda host, port: None,
    )
    exit_code = main(["status"])
    captured = capsys.readouterr()
    assert exit_code == 0
    assert "gateway:stopped" in captured.out


def test_agent_command_rejects_workspace_traversal(tmp_path: Path, capsys, monkeypatch, cli_capture_runtime):
    from claudebot_gateway.cli import main

    monkeypatch.setattr("claudebot_gateway.runtime.create_agent_runtime", lambda config: cli_capture_runtime)
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
            "../../etc",
            "--db-path",
            str(db_path),
        ]
    )
    captured = capsys.readouterr()
    assert exit_code == 1
    assert "escapes workspace root" in captured.err
