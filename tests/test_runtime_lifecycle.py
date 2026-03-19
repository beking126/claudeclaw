import asyncio
from pathlib import Path

from claudebot_gateway.agent_runtime import AgentExecutionResult


class _CounterWorker:
    def __init__(self):
        self.count = 0

    async def run_until_stopped(self, stop_event: asyncio.Event) -> None:
        while not stop_event.is_set():
            self.count += 1
            await asyncio.sleep(0.01)


def test_runtime_graceful_shutdown_drains_and_stops_tasks():
    from claudebot_gateway.runtime import GatewayRuntime

    async def _run() -> dict[str, object]:
        worker = _CounterWorker()
        runtime = GatewayRuntime(workers=[worker.run_until_stopped], drain_timeout_seconds=1.0)
        await runtime.start()
        await asyncio.sleep(0.05)
        await runtime.stop()
        return runtime.health_snapshot()

    health = asyncio.run(_run())
    assert health["running"] is False
    assert health["started"] is True
    assert health["stopped"] is True
    assert health["unhandled_errors"] == 0


def test_gateway_app_run_once_reads_heartbeat_file(tmp_path: Path):
    from claudebot_gateway.config import GatewayConfig
    from claudebot_gateway.persistence.sqlite_store import SqliteStore
    from claudebot_gateway.runtime import GatewayApp

    async def _run() -> None:
        workspace_root = tmp_path / "workspaces"
        heartbeat_file = workspace_root / "heartbeat" / "HEARTBEAT.md"
        heartbeat_file.parent.mkdir(parents=True, exist_ok=True)
        heartbeat_file.write_text("check this\n", encoding="utf-8")
        app = GatewayApp(
            config=GatewayConfig(
                workspace_root=workspace_root,
                sqlite_path=tmp_path / "state" / "gateway.db",
                heartbeat_interval_seconds=1,
            )
        )
        await app.run_once()

    asyncio.run(_run())
    run = SqliteStore(db_path=tmp_path / "state" / "gateway.db").get_last_heartbeat_run()
    assert run is not None
    assert run["actionable"] == 1


def test_gateway_runtime_stop_closes_inbound_intake(tmp_path: Path):
    from claudebot_gateway.config import GatewayConfig
    from claudebot_gateway.runtime import GatewayApp

    async def _run() -> bool:
        app = GatewayApp(
            config=GatewayConfig(
                workspace_root=tmp_path / "workspaces",
                sqlite_path=tmp_path / "state" / "gateway.db",
                heartbeat_interval_seconds=1,
            )
        )
        await app._runtime.start()
        await app._runtime.stop()
        accepted = await app._bus.try_publish_inbound({"channel": "cli", "destination": "d", "text": "x"})
        return accepted

    accepted = asyncio.run(_run())
    assert accepted is False


def test_gateway_app_init_fails_for_unsupported_runtime_provider(tmp_path: Path):
    from claudebot_gateway.agent_runtime import UnsupportedRuntimeProviderError
    from claudebot_gateway.config import AgentRuntimeConfig, GatewayConfig
    from claudebot_gateway.runtime import GatewayApp

    try:
        GatewayApp(
            config=GatewayConfig(
                workspace_root=tmp_path / "workspaces",
                sqlite_path=tmp_path / "state" / "gateway.db",
                agent_runtime=AgentRuntimeConfig(provider="not-supported"),
            )
        )
        assert False
    except UnsupportedRuntimeProviderError as exc:
        assert "not-supported" in str(exc)


def test_gateway_app_heartbeat_agent_uses_runtime_execution(tmp_path: Path):
    from claudebot_gateway.config import GatewayConfig
    from claudebot_gateway.runtime import GatewayApp

    class _FakeRuntime:
        def __init__(self) -> None:
            self.calls = []

        async def execute(self, request):
            self.calls.append(request)
            return AgentExecutionResult(text="hb-ok", provider="test")

    async def _run() -> tuple[str, str, str]:
        app = GatewayApp(
            config=GatewayConfig(
                workspace_root=tmp_path / "workspaces",
                sqlite_path=tmp_path / "state" / "gateway.db",
            )
        )
        fake = _FakeRuntime()
        app._agent_runtime = fake
        response = await app._heartbeat_agent("check", tmp_path / "workspaces" / "heartbeat")
        request = fake.calls[0]
        return response, request.channel, request.destination

    text, channel, destination = asyncio.run(_run())
    assert text == "hb-ok"
    assert channel == "system"
    assert destination == "heartbeat:tick"


def test_gateway_app_cron_agent_uses_runtime_execution(tmp_path: Path):
    from claudebot_gateway.config import GatewayConfig
    from claudebot_gateway.runtime import GatewayApp

    class _FakeRuntime:
        def __init__(self) -> None:
            self.calls = []

        async def execute(self, request):
            self.calls.append(request)
            return AgentExecutionResult(text=f"runtime:{request.prompt}", provider="test")

    async def _run() -> tuple[str, str, str]:
        app = GatewayApp(
            config=GatewayConfig(
                workspace_root=tmp_path / "workspaces",
                sqlite_path=tmp_path / "state" / "gateway.db",
            )
        )
        fake = _FakeRuntime()
        app._agent_runtime = fake
        response = await app._cron_agent("daily", tmp_path / "workspaces" / "cron_job_01")
        request = fake.calls[0]
        return response, request.channel, request.destination

    text, channel, destination = asyncio.run(_run())
    assert text == "runtime:daily"
    assert channel == "system"
    assert destination == "cron:cron_job_01"
