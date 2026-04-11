import asyncio
import logging
from collections.abc import Coroutine
from copy import deepcopy
from pathlib import Path
from typing import Any, Callable

from claudebot_gateway.agent_runtime import AgentExecutionRequest, create_agent_runtime
from claudebot_gateway.agent_runner import AgentRunner
from claudebot_gateway.channel_manager import ChannelManager
from claudebot_gateway.channels.cli import CliChannel
from claudebot_gateway.channels.discord import DiscordChannel
from claudebot_gateway.channels.feishu import FeishuChannel
from claudebot_gateway.channels.slack import SlackBridgeChannel
from claudebot_gateway.channels.telegram import TelegramChannel
from claudebot_gateway.channels.whatsapp import WhatsAppBridgeChannel
from claudebot_gateway.config import GatewayConfig
from claudebot_gateway.cron_service import CronService
from claudebot_gateway.health import HealthService
from claudebot_gateway.heartbeat_service import HeartbeatService
from claudebot_gateway.message_bus import MessageBus
from claudebot_gateway.outbound_dispatcher import OutboundDispatcher
from claudebot_gateway.persistence.sqlite_store import SqliteStore
from claudebot_gateway.workspaces import compose_workspace_prompt, load_workspace_prompt_files
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


class SessionContextRuntime:
    def __init__(
        self,
        *,
        runtime: Any,
        store: SqliteStore,
        session_persistence_enabled: bool,
    ):
        self._runtime = runtime
        self._store = store
        self._session_persistence_enabled = session_persistence_enabled

    async def execute(self, request: AgentExecutionRequest) -> Any:
        request_metadata = deepcopy(request.metadata) if isinstance(request.metadata, dict) else {}
        workspace_path = str(request.workspace)
        channel = request.channel
        destination = request.destination
        prompt_files = load_workspace_prompt_files(request.workspace)
        request_metadata["workspace_prompt_files_loaded"] = [name for name, content in prompt_files.items() if content.strip()]
        composed_prompt = compose_workspace_prompt(request.prompt, prompt_files)
        if self._session_persistence_enabled and "resume_session_id" not in request_metadata:
            latest_session = self._store.get_latest_agent_session(
                provider="claude",
                workspace_path=workspace_path,
                channel=channel,
                destination=destination,
            )
            if latest_session is not None:
                latest_session_id = latest_session.get("session_id")
                if isinstance(latest_session_id, str) and latest_session_id:
                    request_metadata["resume_session_id"] = latest_session_id
        resolved_request = AgentExecutionRequest(
            prompt=composed_prompt,
            workspace=request.workspace,
            channel=channel,
            destination=destination,
            metadata=request_metadata,
        )
        result = await self._runtime.execute(resolved_request)
        if not self._session_persistence_enabled:
            return result
        result_metadata = result.metadata if isinstance(result.metadata, dict) else {}
        session_id_raw = result_metadata.get("session_id")
        session_id = str(session_id_raw) if isinstance(session_id_raw, str | int) else None
        try:
            self._store.record_agent_turn(
                provider=result.provider,
                session_id=session_id,
                workspace_path=workspace_path,
                channel=channel,
                destination=destination,
                prompt_text=request.prompt,
                response_text=result.text,
                metadata=result_metadata,
            )
            if session_id:
                self._store.upsert_latest_agent_session(
                    provider=result.provider,
                    workspace_path=workspace_path,
                    channel=channel,
                    destination=destination,
                    session_id=session_id,
                )
        except Exception:
            _LOGGER.exception("session_persistence_failed")
        return result


class GatewayApp:
    def __init__(self, *, config: GatewayConfig):
        self._config = config
        self._agent_runtime = create_agent_runtime(config)
        self._store = SqliteStore(db_path=config.sqlite_path)
        self._session_runtime = self._runtime_with_session_context(self._agent_runtime)
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
        self._adapters, channels = self._build_channels(config=config, bus=self._bus)
        self._channel_manager = ChannelManager(channels=channels)
        channel_allowed_senders = self._build_allowed_senders(config)
        (
            self._agent_runner,
            self._dispatcher,
            self._cron,
            self._heartbeat,
            self._runtime,
            self._health,
        ) = self._build_services(
            config=config,
            channel_allowed_senders=channel_allowed_senders,
        )

    @staticmethod
    def _build_channels(*, config: GatewayConfig, bus: MessageBus) -> tuple[dict[str, Any], dict[str, Any]]:
        adapters: dict[str, Any] = {}
        channels: dict[str, Any] = {}
        if config.channels.cli.enabled:
            cli = CliChannel()
            adapters["cli"] = cli
            channels["cli"] = cli
        if config.channels.telegram.enabled:
            telegram = TelegramChannel(
                bus=bus,
                token=config.channels.telegram.bot_token,
                send_max_attempts=config.channels.telegram.send_max_attempts,
                base_backoff_seconds=config.channels.telegram.base_backoff_seconds,
                max_backoff_seconds=config.channels.telegram.max_backoff_seconds,
            )
            adapters["telegram"] = telegram
            channels["telegram"] = telegram
        if config.channels.discord.enabled:
            discord = DiscordChannel()
            adapters["discord"] = discord
            channels["discord"] = discord
        if config.channels.feishu.enabled:
            feishu = FeishuChannel(
                bus=bus,
                app_id=config.channels.feishu.app_id,
                app_secret=config.channels.feishu.app_secret,
                verify_token=config.channels.feishu.verify_token,
                encrypt_key=config.channels.feishu.encrypt_key,
                send_max_attempts=config.channels.feishu.send_max_attempts,
                base_backoff_seconds=config.channels.feishu.base_backoff_seconds,
                max_backoff_seconds=config.channels.feishu.max_backoff_seconds,
            )
            adapters["feishu"] = feishu
            channels["feishu"] = feishu
        if config.channels.whatsapp.enabled:
            whatsapp = WhatsAppBridgeChannel()
            adapters["whatsapp"] = whatsapp
            channels["whatsapp"] = whatsapp
        if config.channels.slack.enabled:
            slack = SlackBridgeChannel()
            adapters["slack"] = slack
            channels["slack"] = slack
        return adapters, channels

    @staticmethod
    def _build_allowed_senders(config: GatewayConfig) -> dict[str, set[str]]:
        channel_senders: dict[str, set[str]] = {}
        channel_entries = [
            ("cli", config.channels.cli.allowed_senders),
            ("telegram", config.channels.telegram.allowed_senders),
            ("discord", config.channels.discord.allowed_senders),
            ("feishu", config.channels.feishu.allowed_senders),
            ("whatsapp", config.channels.whatsapp.allowed_senders),
            ("slack", config.channels.slack.allowed_senders),
        ]
        for channel_name, allowed_senders in channel_entries:
            allowed = {sender for sender in allowed_senders if sender}
            if allowed:
                channel_senders[channel_name] = allowed
        return channel_senders

    def _build_services(
        self,
        *,
        config: GatewayConfig,
        channel_allowed_senders: dict[str, set[str]],
    ) -> tuple[AgentRunner, OutboundDispatcher, CronService, HeartbeatService, GatewayRuntime, HealthService]:
        agent_runner = AgentRunner(
            runtime=self._session_runtime,
            default_workspace=self._workspace_resolver.main(),
            channel_allowed_senders=channel_allowed_senders,
        )
        dispatcher = OutboundDispatcher(adapters=self._adapters)
        cron = CronService(db_path=config.sqlite_path, workspace_root=config.workspace_root)
        heartbeat = HeartbeatService(db_path=config.sqlite_path, workspace_root=config.workspace_root)
        runtime = GatewayRuntime(
            workers=[
                self._agent_worker,
                self._dispatch_worker,
                self._cron_worker,
                self._heartbeat_worker,
            ],
            on_stopping_hooks=[self._bus.close_inbound_intake],
        )
        health = HealthService(
            runtime=runtime,
            http_enabled=config.health_http.enabled,
            host=config.health_http.host,
            port=config.health_http.port,
            signal_provider=self._health_signals,
        )
        return agent_runner, dispatcher, cron, heartbeat, runtime, health

    def _channel_allowed_senders(self, config: GatewayConfig) -> dict[str, set[str]]:
        return self._build_allowed_senders(config)

    async def run_once(self, demo_text: str = "") -> None:
        await self._channel_manager.start_all()
        await self._runtime.start()
        await self._health.start_http_if_enabled()
        try:
            if demo_text:
                await self._bus.publish_inbound(
                    {
                        "channel": "cli",
                        "destination": "cli:stdout",
                        "text": demo_text,
                    }
                )
                # Wait for the agent to process the message.
                await asyncio.sleep(30)
        finally:
            await self._health.stop_http_if_started()
            await self._runtime.stop()
            await self._channel_manager.stop_all()

    async def run_forever(self) -> None:
        await self._channel_manager.start_all()
        await self._runtime.start()
        await self._health.start_http_if_enabled()
        try:
            await asyncio.Event().wait()
        finally:
            await self._health.stop_http_if_started()
            await self._runtime.stop()
            await self._channel_manager.stop_all()

    def status(self) -> dict[str, object]:
        return self._health.snapshot()

    def _health_signals(self) -> dict[str, object]:
        return {
            "inbound_queue_depth": self._bus.inbound.qsize(),
            "outbound_queue_depth": self._bus.outbound.qsize(),
            "due_cron_jobs": self._cron.due_job_count(),
            "last_heartbeat_run": self._heartbeat.get_last_run(),
            "channels": self._channel_manager.status_snapshot(),
        }

    async def _agent_worker(self, stop_event: asyncio.Event) -> None:
        while not stop_event.is_set():
            if self._bus.inbound.empty():
                try:
                    await asyncio.wait_for(stop_event.wait(), timeout=0.05)
                except TimeoutError:
                    continue
                continue
            try:
                await self._agent_runner.process_once(self._bus)
            except Exception:
                _LOGGER.exception("agent_worker_process_failed")

    async def _dispatch_worker(self, stop_event: asyncio.Event) -> None:
        while not stop_event.is_set():
            if self._bus.outbound.empty():
                try:
                    await asyncio.wait_for(stop_event.wait(), timeout=0.05)
                except TimeoutError:
                    continue
                continue
            try:
                await self._dispatcher.dispatch_once(self._bus)
            except Exception:
                _LOGGER.exception("dispatch_worker_process_failed")

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
        runtime = self._runtime_with_session_context(self._agent_runtime)
        result = await runtime.execute(
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
        runtime = self._runtime_with_session_context(self._agent_runtime)
        result = await runtime.execute(
            AgentExecutionRequest(
                prompt=prompt,
                workspace=selected_workspace,
                channel="cli",
                destination="cli:stdout",
            )
        )
        return result.text

    def _runtime_with_session_context(self, runtime: Any) -> SessionContextRuntime:
        return SessionContextRuntime(
            runtime=runtime,
            store=self._store,
            session_persistence_enabled=self._config.agent_runtime.claude.session_persistence_enabled,
        )
