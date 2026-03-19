import asyncio
import logging
from collections.abc import Coroutine
from pathlib import Path
from typing import Any, Callable

from claudebot_gateway.agent_runtime import AgentExecutionRequest, create_agent_runtime
from claudebot_gateway.agent_runner import AgentRunner
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
StopHook = Callable[[], None]


class GatewayRuntime:
    def __init__(
        self,
        *,
        workers: list[Worker],
        drain_timeout_seconds: float = 2.0,
        on_stopping_hooks: list[StopHook] | None = None,
    ):
        self._workers = workers
        self._drain_timeout_seconds = drain_timeout_seconds
        self._on_stopping_hooks = on_stopping_hooks or []
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
        for hook in self._on_stopping_hooks:
            hook()
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
    def __init__(self, *, config: GatewayConfig):
        self._config = config
        self._agent_runtime = create_agent_runtime(config)
        self._workspace_resolver = WorkspaceResolver(config.workspace_root)
        self._workspace_resolver.main().mkdir(parents=True, exist_ok=True)
        _LOGGER.info(
            "key_paths workspace_root=%s main_workspace=%s sqlite_path=%s",
            config.workspace_root.resolve(),
            self._workspace_resolver.main().resolve(),
            config.sqlite_path.resolve(),
        )
        _LOGGER.info("agent_runtime provider=%s", config.agent_runtime.provider)
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
        self._agent_runner = AgentRunner(
            runtime=self._agent_runtime,
            default_workspace=self._workspace_resolver.main(),
            channel_allowed_senders=self._channel_allowed_senders(config),
        )
        self._dispatcher = OutboundDispatcher(adapters=self._adapters)
        self._cron = CronService(db_path=config.sqlite_path, workspace_root=config.workspace_root)
        self._heartbeat = HeartbeatService(db_path=config.sqlite_path, workspace_root=config.workspace_root)
        self._runtime = GatewayRuntime(
            workers=[
                self._channel_worker,
                self._agent_worker,
                self._dispatch_worker,
                self._cron_worker,
                self._heartbeat_worker,
            ],
            on_stopping_hooks=[self._bus.close_inbound_intake],
        )
        self._health = HealthService(
            runtime=self._runtime,
            http_enabled=config.health_http.enabled,
            signal_provider=self._health_signals,
        )

    def _channel_allowed_senders(self, config: GatewayConfig) -> dict[str, set[str]]:
        channel_senders: dict[str, set[str]] = {}
        cli_allowed = {sender for sender in config.channels.cli.allowed_senders if sender}
        if cli_allowed:
            channel_senders["cli"] = cli_allowed
        telegram_allowed = {sender for sender in config.channels.telegram.allowed_senders if sender}
        if telegram_allowed:
            channel_senders["telegram"] = telegram_allowed
        return channel_senders

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
        await asyncio.sleep(50)
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

    def _health_signals(self) -> dict[str, object]:
        return {
            "inbound_queue_depth": self._bus.inbound.qsize(),
            "outbound_queue_depth": self._bus.outbound.qsize(),
            "due_cron_jobs": self._cron.due_job_count(),
            "last_heartbeat_run": self._heartbeat.get_last_run(),
        }

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
            except Exception:
                _LOGGER.exception("agent_worker_process_failed")

    async def _dispatch_worker(self, stop_event: asyncio.Event) -> None:
        while not stop_event.is_set():
            try:
                await asyncio.wait_for(self._dispatcher.dispatch_once(self._bus), timeout=0.05)
            except TimeoutError:
                continue

    async def _heartbeat_worker(self, stop_event: asyncio.Event) -> None:
        interval = max(1, self._config.heartbeat_interval_seconds)
        while not stop_event.is_set():
            source_text = self._heartbeat.load_source_text()
            await self._heartbeat.run_once(source_text=source_text, agent_func=self._heartbeat_agent)
            try:
                await asyncio.wait_for(stop_event.wait(), timeout=float(interval))
            except TimeoutError:
                continue

    async def _cron_worker(self, stop_event: asyncio.Event) -> None:
        while not stop_event.is_set():
            await self._cron.run_due_jobs(send_func=self._cron_send, agent_func=self._cron_agent)
            try:
                await asyncio.wait_for(stop_event.wait(), timeout=1.0)
            except TimeoutError:
                continue

    async def _cron_send(self, message: dict[str, str]) -> None:
        await self._bus.publish_outbound(message)

    async def _cron_agent(self, prompt: str, workspace: Path) -> str:
        return await self._execute_background_prompt(
            prompt=prompt,
            workspace=workspace,
            channel="system",
            destination=f"cron:{workspace.name}",
            metadata={"origin": "cron", "workspace_key": workspace.name},
        )

    async def _heartbeat_agent(self, prompt: str, workspace: Path) -> str:
        return await self._execute_background_prompt(
            prompt=prompt,
            workspace=workspace,
            channel="system",
            destination="heartbeat:tick",
            metadata={"origin": "heartbeat", "workspace_key": workspace.name},
        )

    async def _execute_background_prompt(
        self,
        *,
        prompt: str,
        workspace: Path,
        channel: str,
        destination: str,
        metadata: dict[str, str],
    ) -> str:
        result = await self._agent_runtime.execute(
            AgentExecutionRequest(
                prompt=prompt,
                workspace=workspace,
                channel=channel,
                destination=destination,
                metadata=metadata,
            )
        )
        return result.text

    async def execute_prompt(self, *, prompt: str, workspace: Path | None = None) -> str:
        selected_workspace = workspace or self._workspace_resolver.main()
        selected_workspace.mkdir(parents=True, exist_ok=True)
        result = await self._agent_runtime.execute(
            AgentExecutionRequest(
                prompt=prompt,
                workspace=selected_workspace,
                channel="cli",
                destination="cli:stdout",
            )
        )
        return result.text
