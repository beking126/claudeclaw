import asyncio
import logging
from collections.abc import Coroutine
from pathlib import Path
from typing import Any, Callable

from claudebot_gateway.agent_runner import AgentRunner, TurnHandler
from claudebot_gateway.channel_manager import ChannelManager
from claudebot_gateway.channels.cli import CliChannel
from claudebot_gateway.channels.telegram import TelegramChannel
from claudebot_gateway.config import GatewayConfig
from claudebot_gateway.cron_service import CronService
from claudebot_gateway.health import HealthService
from claudebot_gateway.heartbeat_service import HeartbeatService
from claudebot_gateway.message_bus import MessageBus
from claudebot_gateway.outbound_dispatcher import OutboundDispatcher
from claudebot_gateway.workspaces import WorkspaceResolver


Worker = Callable[[asyncio.Event], Coroutine[Any, Any, None]]
_LOGGER = logging.getLogger("claudebot_gateway.runtime")


class GatewayRuntime:
    def __init__(self, *, workers: list[Worker], drain_timeout_seconds: float = 2.0):
        self._workers = workers
        self._drain_timeout_seconds = drain_timeout_seconds
        self._stop_event = asyncio.Event()
        self._tasks: list[asyncio.Task[None]] = []
        self._started = False
        self._running = False
        self._stopped = False
        self._unhandled_errors = 0

    async def start(self) -> None:
        if self._running:
            return
        _LOGGER.debug("runtime_start worker_count=%s", len(self._workers))
        self._started = True
        self._stopped = False
        self._running = True
        self._stop_event.clear()
        self._tasks = []
        for worker in self._workers:
            task: asyncio.Task[None] = asyncio.create_task(worker(self._stop_event))
            task.add_done_callback(self._handle_task_done)
            self._tasks.append(task)

    async def stop(self) -> None:
        if not self._started or self._stopped:
            return
        _LOGGER.debug("runtime_stop active_tasks=%s", sum(0 if t.done() else 1 for t in self._tasks))
        self._running = False
        self._stop_event.set()
        try:
            await asyncio.wait_for(asyncio.gather(*self._tasks, return_exceptions=True), timeout=self._drain_timeout_seconds)
        except asyncio.TimeoutError:
            for task in self._tasks:
                if not task.done():
                    task.cancel()
            await asyncio.gather(*self._tasks, return_exceptions=True)
        self._stopped = True

    def health_snapshot(self) -> dict[str, object]:
        return {
            "started": self._started,
            "running": self._running,
            "stopped": self._stopped,
            "worker_count": len(self._workers),
            "active_tasks": sum(0 if t.done() else 1 for t in self._tasks),
            "unhandled_errors": self._unhandled_errors,
        }

    def _handle_task_done(self, task: asyncio.Task[None]) -> None:
        try:
            task.result()
        except asyncio.CancelledError:
            return
        except Exception:
            self._unhandled_errors += 1


class GatewayApp:
    def __init__(self, *, config: GatewayConfig, turn_handler: TurnHandler | None = None):
        self._config = config
        self._workspace_resolver = WorkspaceResolver(config.workspace_root)
        self._workspace_resolver.main().mkdir(parents=True, exist_ok=True)
        _LOGGER.info(
            "key_paths workspace_root=%s main_workspace=%s sqlite_path=%s",
            config.workspace_root.resolve(),
            self._workspace_resolver.main().resolve(),
            config.sqlite_path.resolve(),
        )
        self._bus = MessageBus(
            inbound_maxsize=config.message_bus.inbound_maxsize,
            outbound_maxsize=config.message_bus.outbound_maxsize,
        )
        self._adapters: dict[str, Any] = {}
        channels: dict[str, Any] = {}
        if config.channels.cli.enabled:
            cli = CliChannel()
            self._adapters["cli"] = cli
            channels["cli"] = cli
        if config.channels.telegram.enabled:
            telegram = TelegramChannel()
            self._adapters["telegram"] = telegram
            channels["telegram"] = telegram
        self._channel_manager = ChannelManager(channels=channels)
        self._agent_runner = AgentRunner(turn_handler=turn_handler or self._default_turn_handler)
        self._dispatcher = OutboundDispatcher(adapters=self._adapters)
        self._cron = CronService(db_path=config.sqlite_path, workspace_root=config.workspace_root)
        self._heartbeat = HeartbeatService(db_path=config.sqlite_path, workspace_root=config.workspace_root)
        self._runtime = GatewayRuntime(
            workers=[
                self._channel_worker,
                self._agent_worker,
                self._dispatch_worker,
                self._heartbeat_worker,
            ]
        )
        self._health = HealthService(runtime=self._runtime, http_enabled=config.health_http.enabled)

    async def run_once(self, demo_text: str = "") -> None:
        await self._runtime.start()
        await self._health.start_http_if_enabled()
        if demo_text:
            await self._bus.publish_inbound(
                {
                    "channel": "cli",
                    "destination": "cli:stdout",
                    "text": demo_text,
                }
            )
        await asyncio.sleep(0.05)
        await self._runtime.stop()

    async def run_forever(self) -> None:
        await self._runtime.start()
        await self._health.start_http_if_enabled()
        try:
            await asyncio.Event().wait()
        finally:
            await self._runtime.stop()

    def status(self) -> dict[str, object]:
        return self._health.snapshot()

    async def _channel_worker(self, stop_event: asyncio.Event) -> None:
        while not stop_event.is_set():
            await self._channel_manager.poll_once_all()
            await asyncio.sleep(0.05)

    async def _agent_worker(self, stop_event: asyncio.Event) -> None:
        while not stop_event.is_set():
            try:
                await asyncio.wait_for(self._agent_runner.process_once(self._bus), timeout=0.05)
            except TimeoutError:
                continue

    async def _dispatch_worker(self, stop_event: asyncio.Event) -> None:
        while not stop_event.is_set():
            try:
                await asyncio.wait_for(self._dispatcher.dispatch_once(self._bus), timeout=0.05)
            except TimeoutError:
                continue

    async def _heartbeat_worker(self, stop_event: asyncio.Event) -> None:
        interval = max(1, self._config.heartbeat_interval_seconds)
        while not stop_event.is_set():
            await self._heartbeat.run_once(source_text="", agent_func=self._noop_agent)
            try:
                await asyncio.wait_for(stop_event.wait(), timeout=float(interval))
            except TimeoutError:
                continue

    async def _noop_agent(self, prompt: str, workspace: Path) -> str:
        _ = (prompt, workspace)
        return "ok"

    def _default_turn_handler(self, inbound: dict[str, Any]) -> dict[str, Any]:
        return {
            "channel": inbound.get("channel", "cli"),
            "destination": inbound.get("destination", "cli:stdout"),
            "text": f"echo:{inbound.get('text', '')}",
        }
