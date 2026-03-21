from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from claudebot_gateway.agent_runtime import AgentExecutionResult
from claudebot_gateway.config import GatewayConfig
from claudebot_gateway.runtime import GatewayApp


class CollectingAdapter:
    def __init__(self) -> None:
        self.sent: list[dict[str, str]] = []

    async def send(self, message: dict[str, str]) -> None:
        self.sent.append(message)


class EchoRuntime:
    async def execute(self, request: Any) -> AgentExecutionResult:
        return AgentExecutionResult(text=f"echo:{request.prompt}", provider="test")


class FailingRuntime:
    async def execute(self, request: Any) -> AgentExecutionResult:
        _ = request
        raise RuntimeError("boom")


class TrackingRuntime:
    def __init__(self, *, prefix: str = "ok") -> None:
        self.requests: list[Any] = []
        self._prefix = prefix

    async def execute(self, request: Any) -> AgentExecutionResult:
        self.requests.append(request)
        return AgentExecutionResult(text=f"{self._prefix}:{request.prompt}", provider="test")


class CliCaptureRuntime:
    def __init__(self, *, text: str = "runtime-output") -> None:
        self.workspace: Path | None = None
        self.prompt: str | None = None
        self._text = text

    async def execute(self, request: Any) -> AgentExecutionResult:
        self.workspace = request.workspace
        self.prompt = request.prompt
        return AgentExecutionResult(text=self._text, provider="test")


@pytest.fixture
def collecting_adapter() -> CollectingAdapter:
    return CollectingAdapter()


@pytest.fixture
def echo_runtime() -> EchoRuntime:
    return EchoRuntime()


@pytest.fixture
def failing_runtime() -> FailingRuntime:
    return FailingRuntime()


@pytest.fixture
def tracking_runtime() -> TrackingRuntime:
    return TrackingRuntime()


@pytest.fixture
def cli_capture_runtime() -> CliCaptureRuntime:
    return CliCaptureRuntime()


@pytest.fixture
def gateway_app_factory() -> Callable[[Path], GatewayApp]:
    def _create(tmp_path: Path) -> GatewayApp:
        return GatewayApp(
            config=GatewayConfig(
                workspace_root=tmp_path / "workspaces",
                sqlite_path=tmp_path / "state" / "gateway.db",
            )
        )

    return _create
