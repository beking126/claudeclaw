from pathlib import Path


def test_workspace_layout_constants():
    from claudebot_gateway.models import WorkspaceKind

    assert WorkspaceKind.MAIN.value == "main"
    assert WorkspaceKind.HEARTBEAT.value == "heartbeat"


def test_config_defaults(tmp_path: Path):
    from claudebot_gateway.config import GatewayConfig

    config = GatewayConfig(workspace_root=tmp_path / "workspaces")

    assert config.channels.cli.enabled is True
    assert config.channels.telegram.enabled is False
    assert config.message_bus.inbound_maxsize == 1000
