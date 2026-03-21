import asyncio
from pathlib import Path

import pytest

from claudebot_gateway.agent_runtime import AgentExecutionRequest, AgentExecutionResult


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


def test_gateway_runtime_stop_closes_inbound_intake(tmp_path: Path, gateway_app_factory):
    async def _run() -> bool:
        app = gateway_app_factory(tmp_path)
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

    with pytest.raises(UnsupportedRuntimeProviderError) as exc_info:
        GatewayApp(
            config=GatewayConfig(
                workspace_root=tmp_path / "workspaces",
                sqlite_path=tmp_path / "state" / "gateway.db",
                agent_runtime=AgentRuntimeConfig(provider="not-supported"),
            )
        )
    assert "not-supported" in str(exc_info.value)


def test_gateway_app_heartbeat_agent_uses_runtime_execution(tmp_path: Path):
    from claudebot_gateway.config import GatewayConfig
    from claudebot_gateway.runtime import GatewayApp

    class _FakeRuntime:
        def __init__(self) -> None:
            self.calls: list[AgentExecutionRequest] = []

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
        assert request.channel is not None
        assert request.destination is not None
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
            self.calls: list[AgentExecutionRequest] = []

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
        assert request.channel is not None
        assert request.destination is not None
        return response, request.channel, request.destination

    text, channel, destination = asyncio.run(_run())
    assert text == "runtime:daily"
    assert channel == "system"
    assert destination == "cron:cron_job_01"


def test_gateway_app_wires_enabled_extended_channels(tmp_path: Path):
    from claudebot_gateway.config import ChannelConfig, ChannelToggle, FeishuChannelConfig, GatewayConfig, TelegramChannelConfig
    from claudebot_gateway.runtime import GatewayApp

    app = GatewayApp(
        config=GatewayConfig(
            workspace_root=tmp_path / "workspaces",
            sqlite_path=tmp_path / "state" / "gateway.db",
            channels=ChannelConfig(
                cli=ChannelToggle(enabled=True),
                telegram=TelegramChannelConfig(
                    enabled=True,
                    bot_token="tg-token",
                    send_max_attempts=7,
                    base_backoff_seconds=0.25,
                    max_backoff_seconds=3.0,
                ),
                discord=ChannelToggle(enabled=True),
                feishu=FeishuChannelConfig(
                    enabled=True,
                    app_id="fei-app",
                    app_secret="fei-secret",
                    verify_token="verify-me",
                    encrypt_key="enc-key",
                    send_max_attempts=6,
                    base_backoff_seconds=0.4,
                    max_backoff_seconds=2.4,
                ),
                whatsapp=ChannelToggle(enabled=True),
                slack=ChannelToggle(enabled=True),
            ),
        )
    )
    assert "cli" in app._adapters
    assert "telegram" in app._adapters
    assert "discord" in app._adapters
    assert "feishu" in app._adapters
    assert "whatsapp" in app._adapters
    assert "slack" in app._adapters
    telegram = app._adapters["telegram"]
    assert telegram._token == "tg-token"
    assert telegram._send_max_attempts == 7
    assert telegram._base_backoff_seconds == 0.25
    assert telegram._max_backoff_seconds == 3.0
    feishu = app._adapters["feishu"]
    assert feishu._app_id == "fei-app"
    assert feishu._app_secret == "fei-secret"
    assert feishu._verify_token == "verify-me"
    assert feishu._encrypt_key == "enc-key"
    assert feishu._send_max_attempts == 6


def test_gateway_app_builders_preserve_enabled_channels_and_allowed_senders(tmp_path: Path):
    from claudebot_gateway.config import ChannelConfig, ChannelToggle, FeishuChannelConfig, GatewayConfig, TelegramChannelConfig
    from claudebot_gateway.message_bus import MessageBus
    from claudebot_gateway.runtime import GatewayApp

    config = GatewayConfig(
        workspace_root=tmp_path / "workspaces",
        sqlite_path=tmp_path / "state" / "gateway.db",
        channels=ChannelConfig(
            cli=ChannelToggle(enabled=True, allowed_senders=["cli-user", ""]),
            telegram=TelegramChannelConfig(enabled=True, allowed_senders=["tg-user"]),
            discord=ChannelToggle(enabled=False, allowed_senders=["dc-user"]),
            feishu=FeishuChannelConfig(enabled=True, allowed_senders=["", "fei-user"]),
            whatsapp=ChannelToggle(enabled=False, allowed_senders=["wa-user"]),
            slack=ChannelToggle(enabled=True, allowed_senders=[]),
        ),
    )
    adapters, channels = GatewayApp._build_channels(config=config, bus=MessageBus())
    allowed = GatewayApp._build_allowed_senders(config)

    assert set(adapters.keys()) == {"cli", "telegram", "feishu", "slack"}
    assert set(channels.keys()) == {"cli", "telegram", "feishu", "slack"}
    assert allowed == {
        "cli": {"cli-user"},
        "telegram": {"tg-user"},
        "discord": {"dc-user"},
        "feishu": {"fei-user"},
        "whatsapp": {"wa-user"},
    }


def test_gateway_app_build_services_returns_expected_components(tmp_path: Path):
    from claudebot_gateway.agent_runner import AgentRunner
    from claudebot_gateway.config import GatewayConfig
    from claudebot_gateway.cron_service import CronService
    from claudebot_gateway.health import HealthService
    from claudebot_gateway.heartbeat_service import HeartbeatService
    from claudebot_gateway.outbound_dispatcher import OutboundDispatcher
    from claudebot_gateway.runtime import GatewayApp, GatewayRuntime

    app = GatewayApp(
        config=GatewayConfig(
            workspace_root=tmp_path / "workspaces",
            sqlite_path=tmp_path / "state" / "gateway.db",
        )
    )
    components = app._build_services(config=app._config, channel_allowed_senders={})
    agent_runner, dispatcher, cron, heartbeat, runtime, health = components
    assert isinstance(agent_runner, AgentRunner)
    assert isinstance(dispatcher, OutboundDispatcher)
    assert isinstance(cron, CronService)
    assert isinstance(heartbeat, HeartbeatService)
    assert isinstance(runtime, GatewayRuntime)
    assert isinstance(health, HealthService)
    snapshot = runtime.health_snapshot()
    assert snapshot["worker_count"] == 4


def test_gateway_app_wires_health_http_host_and_port(tmp_path: Path):
    from claudebot_gateway.config import GatewayConfig, HealthHttpConfig
    from claudebot_gateway.runtime import GatewayApp

    app = GatewayApp(
        config=GatewayConfig(
            workspace_root=tmp_path / "workspaces",
            sqlite_path=tmp_path / "state" / "gateway.db",
            health_http=HealthHttpConfig(enabled=True, host="127.0.0.1", port=0),
        )
    )
    assert app._health._http_enabled is True
    assert app._health._host == "127.0.0.1"
    assert app._health._port == 0


def test_gateway_app_persists_turns_and_uses_persisted_resume(tmp_path: Path):
    from claudebot_gateway.agent_runtime import AgentExecutionResult
    from claudebot_gateway.config import GatewayConfig
    from claudebot_gateway.persistence.sqlite_store import SqliteStore
    from claudebot_gateway.runtime import GatewayApp

    class _TrackingRuntime:
        def __init__(self):
            self.requests: list[AgentExecutionRequest] = []
            self._count = 0

        async def execute(self, request):
            self.requests.append(request)
            self._count += 1
            return AgentExecutionResult(
                text=f"ok-{self._count}",
                provider="claude",
                metadata={"session_id": f"s-{self._count}", "usage": {"input_tokens": self._count}},
            )

    async def _run() -> tuple[str | None, str, str]:
        workspace_root = tmp_path / "workspaces"
        main_workspace = workspace_root / "main"
        main_workspace.mkdir(parents=True, exist_ok=True)
        (main_workspace / "SOUL.md").write_text("soul context", encoding="utf-8")
        app = GatewayApp(
            config=GatewayConfig(
                workspace_root=workspace_root,
                sqlite_path=tmp_path / "state" / "gateway.db",
            )
        )
        tracking = _TrackingRuntime()
        app._agent_runner._runtime = app._runtime_with_session_context(tracking)
        await app._bus.publish_inbound({"channel": "telegram", "destination": "chat:99", "text": "hello"})
        await app._agent_runner.process_once(app._bus)
        await app._bus.publish_inbound({"channel": "telegram", "destination": "chat:99", "text": "again"})
        await app._agent_runner.process_once(app._bus)
        first_prompt = tracking.requests[0].prompt
        second_resume = tracking.requests[1].metadata.get("resume_session_id")
        second_prompt = tracking.requests[1].prompt
        return second_resume if isinstance(second_resume, str) else None, first_prompt, second_prompt

    resumed_session_id, first_prompt, second_prompt = asyncio.run(_run())
    assert resumed_session_id == "s-1"
    assert "SOUL" in first_prompt
    assert first_prompt.endswith("hello")
    assert second_prompt.endswith("again")
    store = SqliteStore(db_path=tmp_path / "state" / "gateway.db")
    latest = store.get_latest_agent_session(
        provider="claude",
        workspace_path=str(tmp_path / "workspaces" / "main"),
        channel="telegram",
        destination="chat:99",
    )
    assert latest is not None
    assert latest["session_id"] == "s-2"
