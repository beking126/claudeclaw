from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol


@dataclass(slots=True)
class AgentExecutionRequest:
    prompt: str
    workspace: Path
    channel: str | None = None
    destination: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class AgentExecutionResult:
    text: str
    provider: str
    metadata: dict[str, Any] = field(default_factory=dict)


class AgentRuntime(Protocol):
    async def execute(self, request: AgentExecutionRequest) -> AgentExecutionResult: ...
