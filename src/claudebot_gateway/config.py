from dataclasses import dataclass, field
import json
from pathlib import Path
from typing import Any


@dataclass(slots=True)
class ClaudeRuntimeOptions:
    tools: list[str] = field(default_factory=list)
    allowed_tools: list[str] = field(default_factory=list)
    disallowed_tools: list[str] = field(default_factory=list)
    system_prompt: str | None = None
    mcp_servers: dict[str, object] = field(default_factory=dict)
    hooks: dict[str, object] | None = None
    continue_conversation: bool = False
    resume: str | None = None
    max_turns: int | None = None
    model: str | None = None
    fallback_model: str | None = None
    setting_sources: list[str] | None = None
    skills: list[str] = field(default_factory=list)
    sub_agents: dict[str, dict[str, object]] = field(default_factory=dict)
    env: dict[str, str] = field(default_factory=dict)
    extra_args: dict[str, str | None] = field(default_factory=dict)
    permission_mode: str | None = None


@dataclass(slots=True)
class AgentRuntimeConfig:
    provider: str = "claude"
    claude: ClaudeRuntimeOptions = field(default_factory=ClaudeRuntimeOptions)


@dataclass(slots=True)
class ChannelToggle:
    enabled: bool
    allowed_senders: list[str] = field(default_factory=list)


@dataclass(slots=True)
class TelegramChannelConfig(ChannelToggle):
    bot_token: str | None = None
    send_max_attempts: int = 3
    base_backoff_seconds: float = 0.5
    max_backoff_seconds: float = 8.0


@dataclass(slots=True)
class FeishuChannelConfig(ChannelToggle):
    app_id: str | None = None
    app_secret: str | None = None
    verify_token: str | None = None
    encrypt_key: str | None = None
    send_max_attempts: int = 3
    base_backoff_seconds: float = 0.5
    max_backoff_seconds: float = 8.0


@dataclass(slots=True)
class ChannelConfig:
    cli: ChannelToggle = field(default_factory=lambda: ChannelToggle(enabled=True))
    telegram: TelegramChannelConfig = field(default_factory=lambda: TelegramChannelConfig(enabled=False))
    discord: ChannelToggle = field(default_factory=lambda: ChannelToggle(enabled=False))
    feishu: FeishuChannelConfig = field(default_factory=lambda: FeishuChannelConfig(enabled=False))
    whatsapp: ChannelToggle = field(default_factory=lambda: ChannelToggle(enabled=False))
    slack: ChannelToggle = field(default_factory=lambda: ChannelToggle(enabled=False))


@dataclass(slots=True)
class MessageBusConfig:
    inbound_maxsize: int = 1000
    outbound_maxsize: int = 1000


@dataclass(slots=True)
class HealthHttpConfig:
    enabled: bool = False
    host: str = "127.0.0.1"
    port: int = 8787


@dataclass(slots=True)
class GatewayConfig:
    workspace_root: Path
    agent_runtime: AgentRuntimeConfig = field(default_factory=AgentRuntimeConfig)
    channels: ChannelConfig = field(default_factory=ChannelConfig)
    message_bus: MessageBusConfig = field(default_factory=MessageBusConfig)
    health_http: HealthHttpConfig = field(default_factory=HealthHttpConfig)
    heartbeat_interval_seconds: int = 300
    sqlite_path: Path = Path("state/gateway.db")


def load_gateway_config(
    *,
    config_path: Path | None = None,
    workspace_root: Path | None = None,
    sqlite_path: Path | None = None,
) -> GatewayConfig:
    effective_config_path = config_path or Path("claudebot/config.json")
    raw: dict[str, Any] = {}
    if effective_config_path.exists():
        loaded = json.loads(effective_config_path.read_text(encoding="utf-8"))
        if isinstance(loaded, dict):
            raw = loaded
    workspace = workspace_root or Path(str(raw.get("workspace_root", "workspaces")))
    sqlite = sqlite_path or Path(str(raw.get("sqlite_path", "state/gateway.db")))
    config = GatewayConfig(workspace_root=workspace, sqlite_path=sqlite)
    channels_raw = raw.get("channels")
    if isinstance(channels_raw, dict):
        _apply_channel_toggle(config.channels.cli, channels_raw.get("cli"))
        _apply_channel_toggle(config.channels.discord, channels_raw.get("discord"))
        _apply_channel_toggle(config.channels.whatsapp, channels_raw.get("whatsapp"))
        _apply_channel_toggle(config.channels.slack, channels_raw.get("slack"))
        feishu_raw = channels_raw.get("feishu")
        if isinstance(feishu_raw, dict):
            _apply_channel_toggle(config.channels.feishu, feishu_raw)
            app_id = feishu_raw.get("app_id")
            if isinstance(app_id, str):
                config.channels.feishu.app_id = app_id
            app_secret = feishu_raw.get("app_secret")
            if isinstance(app_secret, str):
                config.channels.feishu.app_secret = app_secret
            verify_token = feishu_raw.get("verify_token")
            if isinstance(verify_token, str):
                config.channels.feishu.verify_token = verify_token
            encrypt_key = feishu_raw.get("encrypt_key")
            if isinstance(encrypt_key, str):
                config.channels.feishu.encrypt_key = encrypt_key
            send_max_attempts = feishu_raw.get("send_max_attempts")
            if isinstance(send_max_attempts, int):
                config.channels.feishu.send_max_attempts = send_max_attempts
            base_backoff = feishu_raw.get("base_backoff_seconds")
            if isinstance(base_backoff, int | float):
                config.channels.feishu.base_backoff_seconds = float(base_backoff)
            max_backoff = feishu_raw.get("max_backoff_seconds")
            if isinstance(max_backoff, int | float):
                config.channels.feishu.max_backoff_seconds = float(max_backoff)
        telegram_raw = channels_raw.get("telegram")
        if isinstance(telegram_raw, dict):
            _apply_channel_toggle(config.channels.telegram, telegram_raw)
            token = telegram_raw.get("bot_token")
            if isinstance(token, str):
                config.channels.telegram.bot_token = token
            send_max_attempts = telegram_raw.get("send_max_attempts")
            if isinstance(send_max_attempts, int):
                config.channels.telegram.send_max_attempts = send_max_attempts
            base_backoff = telegram_raw.get("base_backoff_seconds")
            if isinstance(base_backoff, int | float):
                config.channels.telegram.base_backoff_seconds = float(base_backoff)
            max_backoff = telegram_raw.get("max_backoff_seconds")
            if isinstance(max_backoff, int | float):
                config.channels.telegram.max_backoff_seconds = float(max_backoff)
    return config


def _apply_channel_toggle(toggle: ChannelToggle, raw: object) -> None:
    if not isinstance(raw, dict):
        return
    enabled = raw.get("enabled")
    if isinstance(enabled, bool):
        toggle.enabled = enabled
    allowed_senders = raw.get("allowed_senders")
    if isinstance(allowed_senders, list):
        toggle.allowed_senders = [sender for sender in allowed_senders if isinstance(sender, str)]
