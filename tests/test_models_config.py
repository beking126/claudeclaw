from pathlib import Path
import json


def test_workspace_layout_constants():
    from claudebot_gateway.models import WorkspaceKind

    assert WorkspaceKind.MAIN.value == "main"
    assert WorkspaceKind.HEARTBEAT.value == "heartbeat"


def test_config_defaults(tmp_path: Path):
    from claudebot_gateway.config import GatewayConfig

    config = GatewayConfig(workspace_root=tmp_path / "workspaces")

    assert config.channels.cli.enabled is True
    assert config.channels.telegram.enabled is False
    assert config.channels.discord.enabled is False
    assert config.channels.feishu.enabled is False
    assert config.channels.whatsapp.enabled is False
    assert config.channels.slack.enabled is False
    assert config.channels.cli.allowed_senders == []
    assert config.channels.telegram.allowed_senders == []
    assert config.channels.telegram.bot_token is None
    assert config.channels.telegram.send_max_attempts == 3
    assert config.channels.telegram.base_backoff_seconds == 0.5
    assert config.channels.telegram.max_backoff_seconds == 8.0
    assert config.message_bus.inbound_maxsize == 1000
    assert config.agent_runtime.provider == "claude"
    assert config.agent_runtime.claude.tools == []


def test_load_gateway_config_from_local_json(tmp_path: Path):
    from claudebot_gateway.config import load_gateway_config

    config_dir = tmp_path / "claudebot"
    config_dir.mkdir(parents=True, exist_ok=True)
    config_path = config_dir / "config.json"
    config_path.write_text(
        json.dumps(
            {
                "workspace_root": "custom_workspaces",
                "sqlite_path": "custom_state/gateway.db",
                "channels": {
                    "telegram": {
                        "enabled": True,
                        "allowed_senders": ["alice"],
                        "bot_token": "from-json-token",
                        "send_max_attempts": 5,
                        "base_backoff_seconds": 0.2,
                        "max_backoff_seconds": 2.0,
                    }
                },
            }
        ),
        encoding="utf-8",
    )

    config = load_gateway_config(config_path=config_path)
    assert config.workspace_root == Path("custom_workspaces")
    assert config.sqlite_path == Path("custom_state/gateway.db")
    assert config.channels.telegram.enabled is True
    assert config.channels.telegram.allowed_senders == ["alice"]
    assert config.channels.telegram.bot_token == "from-json-token"
    assert config.channels.telegram.send_max_attempts == 5
