from dataclasses import dataclass
from enum import Enum


class WorkspaceKind(str, Enum):
    MAIN = "main"
    HEARTBEAT = "heartbeat"


@dataclass(slots=True)
class InboundMessage:
    channel: str
    destination: str
    text: str


@dataclass(slots=True)
class OutboundMessage:
    channel: str
    destination: str
    text: str
