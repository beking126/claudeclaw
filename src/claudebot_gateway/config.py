from dataclasses import dataclass, field
from pathlib import Path


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
class ChannelConfig:
    cli: ChannelToggle = field(default_factory=lambda: ChannelToggle(enabled=True))
    telegram: ChannelToggle = field(default_factory=lambda: ChannelToggle(enabled=False))


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
