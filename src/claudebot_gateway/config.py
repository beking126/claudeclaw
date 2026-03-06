from dataclasses import dataclass, field
from pathlib import Path


@dataclass(slots=True)
class ChannelToggle:
    enabled: bool


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
    channels: ChannelConfig = field(default_factory=ChannelConfig)
    message_bus: MessageBusConfig = field(default_factory=MessageBusConfig)
    health_http: HealthHttpConfig = field(default_factory=HealthHttpConfig)
    heartbeat_interval_seconds: int = 300
    sqlite_path: Path = Path("state/gateway.db")
