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
    restrict_to_workspace: bool = False
    session_persistence_enabled: bool = True
    session_scope: str = "workspace_channel_destination"


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
    agent_turns_retention_days: int = 90
    rate_limit_max_requests_per_sender: int = 0
    rate_limit_window_seconds: float = 60.0


def load_gateway_config(
    *,
    config_path: Path | None = None,
    workspace_root: Path | None = None,
    sqlite_path: Path | None = None,
) -> GatewayConfig:
    effective_config_path = config_path or Path(".claudebot/config.json")
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
            _apply_feishu_config(config.channels.feishu, feishu_raw)
        telegram_raw = channels_raw.get("telegram")
        if isinstance(telegram_raw, dict):
            _apply_telegram_config(config.channels.telegram, telegram_raw)
    agent_runtime_raw = raw.get("agent_runtime")
    if isinstance(agent_runtime_raw, dict):
        provider_raw = agent_runtime_raw.get("provider")
        if isinstance(provider_raw, str) and provider_raw:
            config.agent_runtime.provider = provider_raw
        claude_raw = agent_runtime_raw.get("claude")
        if isinstance(claude_raw, dict):
            session_persistence_enabled = claude_raw.get("session_persistence_enabled")
            if isinstance(session_persistence_enabled, bool):
                config.agent_runtime.claude.session_persistence_enabled = session_persistence_enabled
            session_scope = claude_raw.get("session_scope")
            if isinstance(session_scope, str) and session_scope:
                config.agent_runtime.claude.session_scope = session_scope
            restrict_to_workspace = claude_raw.get("restrict_to_workspace")
            if isinstance(restrict_to_workspace, bool):
                config.agent_runtime.claude.restrict_to_workspace = restrict_to_workspace
    rate_limit_raw = raw.get("rate_limit")
    if isinstance(rate_limit_raw, dict):
        max_requests = rate_limit_raw.get("max_requests_per_sender")
        if isinstance(max_requests, int):
            config.rate_limit_max_requests_per_sender = max_requests
        window_seconds = rate_limit_raw.get("window_seconds")
        if isinstance(window_seconds, (int, float)):
            config.rate_limit_window_seconds = float(window_seconds)
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


def _read_str(raw: dict[str, Any], key: str) -> str | None:
    value = raw.get(key)
    if isinstance(value, str):
        return value
    return None


def _read_int(raw: dict[str, Any], key: str) -> int | None:
    value = raw.get(key)
    if isinstance(value, int):
        return value
    return None


def _read_float(raw: dict[str, Any], key: str) -> float | None:
    value = raw.get(key)
    if isinstance(value, int | float):
        return float(value)
    return None


def _apply_retry_backoff_fields(raw: dict[str, Any], channel: TelegramChannelConfig | FeishuChannelConfig) -> None:
    send_max_attempts = _read_int(raw, "send_max_attempts")
    if send_max_attempts is not None:
        channel.send_max_attempts = send_max_attempts
    base_backoff = _read_float(raw, "base_backoff_seconds")
    if base_backoff is not None:
        channel.base_backoff_seconds = base_backoff
    max_backoff = _read_float(raw, "max_backoff_seconds")
    if max_backoff is not None:
        channel.max_backoff_seconds = max_backoff


def _apply_telegram_config(channel: TelegramChannelConfig, raw: dict[str, Any]) -> None:
    _apply_channel_toggle(channel, raw)
    token = _read_str(raw, "bot_token")
    if token is not None:
        channel.bot_token = token
    _apply_retry_backoff_fields(raw, channel)


def _apply_feishu_config(channel: FeishuChannelConfig, raw: dict[str, Any]) -> None:
    _apply_channel_toggle(channel, raw)
    app_id = _read_str(raw, "app_id")
    if app_id is not None:
        channel.app_id = app_id
    app_secret = _read_str(raw, "app_secret")
    if app_secret is not None:
        channel.app_secret = app_secret
    verify_token = _read_str(raw, "verify_token")
    if verify_token is not None:
        channel.verify_token = verify_token
    encrypt_key = _read_str(raw, "encrypt_key")
    if encrypt_key is not None:
        channel.encrypt_key = encrypt_key
    _apply_retry_backoff_fields(raw, channel)
