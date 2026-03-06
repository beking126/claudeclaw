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
