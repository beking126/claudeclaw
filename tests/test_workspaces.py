from pathlib import Path


def test_sanitizes_channel_workspace_key():
    from claudebot_gateway.workspaces import make_channel_workspace_key

    assert make_channel_workspace_key("TeleGram", "Chat:123/ABC") == "telegram_chat_123_abc"


def test_resolves_special_workspaces(tmp_path: Path):
    from claudebot_gateway.workspaces import WorkspaceResolver

    resolver = WorkspaceResolver(tmp_path / "workspaces")

    assert resolver.main() == tmp_path / "workspaces" / "main"
    assert resolver.heartbeat() == tmp_path / "workspaces" / "heartbeat"
    assert resolver.cron("job-01") == tmp_path / "workspaces" / "cron_job-01"


def test_loads_workspace_prompt_files_and_composes_prompt(tmp_path: Path):
    from claudebot_gateway.workspaces import compose_workspace_prompt, load_workspace_prompt_files

    workspace = tmp_path / "workspaces" / "main"
    workspace.mkdir(parents=True, exist_ok=True)
    (workspace / "SOUL.md").write_text("soul text", encoding="utf-8")
    (workspace / "USER.md").write_text("user text", encoding="utf-8")
    (workspace / "TOOLS.md").write_text("tools text", encoding="utf-8")

    loaded = load_workspace_prompt_files(workspace)
    composed = compose_workspace_prompt("do task", loaded)

    assert loaded["SOUL.md"] == "soul text"
    assert loaded["USER.md"] == "user text"
    assert loaded["TOOLS.md"] == "tools text"
    assert composed.index("SOUL") < composed.index("USER")
    assert composed.index("USER") < composed.index("TOOLS")
    assert composed.endswith("do task")


def test_prompt_file_loader_tolerates_missing_files(tmp_path: Path):
    from claudebot_gateway.workspaces import load_workspace_prompt_files

    workspace = tmp_path / "workspaces" / "main"
    workspace.mkdir(parents=True, exist_ok=True)
    loaded = load_workspace_prompt_files(workspace)
    assert loaded["SOUL.md"] == ""
    assert loaded["USER.md"] == ""
    assert loaded["TOOLS.md"] == ""
