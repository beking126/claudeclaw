from pathlib import Path


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
