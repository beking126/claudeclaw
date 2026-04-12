import asyncio
import json
import socket
from typing import Callable, Protocol


class RuntimeHealth(Protocol):
    def health_snapshot(self) -> dict[str, object]:
        ...


class HealthService:
    def __init__(
        self,
        *,
        runtime: RuntimeHealth,
        http_enabled: bool,
        host: str = "127.0.0.1",
        port: int = 8787,
        signal_provider: Callable[[], dict[str, object]] | None = None,
    ):
        self._runtime = runtime
        self._http_enabled = http_enabled
        self._host = host
        self._port = port
        self._bound_port: int | None = None
        self._http_started = False
        self._server: asyncio.AbstractServer | None = None
        self._signal_provider = signal_provider

    async def start_http_if_enabled(self) -> bool:
        if not self._http_enabled:
            self._http_started = False
            return False
        if self._server is not None:
            self._http_started = True
            return True
        self._server = await asyncio.start_server(self._handle_http_client, host=self._host, port=self._port)
        sockets: tuple[socket.socket, ...] | list[socket.socket] = self._server.sockets or []
        if sockets:
            sockname = sockets[0].getsockname()
            self._bound_port = int(sockname[1])
        self._http_started = True
        return True

    async def stop_http_if_started(self) -> None:
        if self._server is None:
            self._http_started = False
            return
        self._server.close()
        await self._server.wait_closed()
        self._server = None
        self._http_started = False

    def snapshot(self) -> dict[str, object]:
        signals = {} if self._signal_provider is None else self._signal_provider()
        return {
            "http_enabled": self._http_enabled,
            "http_started": self._http_started,
            "http_host": self._host,
            "http_port": self._bound_port if self._bound_port is not None else self._port,
            "runtime": self._runtime.health_snapshot(),
            "signals": signals,
        }

    async def _handle_http_client(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        status_code = 404
        payload: dict[str, object] = {"error": "not_found"}
        try:
            request_line = await reader.readline()
            request_text = request_line.decode("utf-8", errors="ignore").strip()
            parts = request_text.split(" ")
            path = parts[1] if len(parts) >= 2 else "/"
            while True:
                header_line = await reader.readline()
                if not header_line or header_line in (b"\r\n", b"\n"):
                    break
            if path in ("/health", "/healthz"):
                status_code = 200
                payload = self.snapshot()
            elif path == "/metrics":
                status_code = 200
                payload = self._metrics_snapshot()
            elif path in ("/ready", "/readyz"):
                ready = self._is_ready()
                status_code = 200 if ready else 503
                payload = {"ready": ready, "runtime": self._runtime.health_snapshot()}
        except Exception:
            status_code = 500
            payload = {"error": "internal_error"}
        body = json.dumps(payload).encode("utf-8")
        reason = "OK" if status_code < 400 else "ERROR"
        writer.write(
            (
                f"HTTP/1.1 {status_code} {reason}\r\n"
                "Content-Type: application/json\r\n"
                f"Content-Length: {len(body)}\r\n"
                "Connection: close\r\n\r\n"
            ).encode("utf-8")
            + body
        )
        await writer.drain()
        writer.close()
        await writer.wait_closed()

    def _is_ready(self) -> bool:
        runtime_snapshot = self._runtime.health_snapshot()
        running = runtime_snapshot.get("running")
        if not isinstance(running, bool):
            return False
        return running

    def _metrics_snapshot(self) -> dict[str, object]:
        signals = {} if self._signal_provider is None else self._signal_provider()
        runtime = self._runtime.health_snapshot()
        return {
            "unhandled_errors": runtime.get("unhandled_errors", 0),
            "active_tasks": runtime.get("active_tasks", 0),
            "inbound_queue_depth": signals.get("inbound_queue_depth", 0),
            "outbound_queue_depth": signals.get("outbound_queue_depth", 0),
            "due_cron_jobs": signals.get("due_cron_jobs", 0),
        }
