import asyncio
import json


async def _http_get_json(host: str, port: int, path: str) -> tuple[int, dict[str, object]]:
    reader, writer = await asyncio.open_connection(host, port)
    writer.write(f"GET {path} HTTP/1.1\r\nHost: {host}\r\nConnection: close\r\n\r\n".encode("utf-8"))
    await writer.drain()
    raw = await reader.read()
    writer.close()
    await writer.wait_closed()
    header_bytes, body_bytes = raw.split(b"\r\n\r\n", 1)
    status_line = header_bytes.decode("utf-8").splitlines()[0]
    status_code = int(status_line.split(" ")[1])
    payload = json.loads(body_bytes.decode("utf-8"))
    return status_code, payload


def test_http_health_only_available_when_feature_flag_enabled():
    from claudebot_gateway.health import HealthService
    from claudebot_gateway.runtime import GatewayRuntime

    async def _run() -> tuple[bool, bool, int, int, dict[str, object], dict[str, object], dict[str, object]]:
        runtime = GatewayRuntime(workers=[])
        await runtime.start()
        disabled = HealthService(runtime=runtime, http_enabled=False)
        enabled = HealthService(runtime=runtime, http_enabled=True, host="127.0.0.1", port=0)
        disabled_started = await disabled.start_http_if_enabled()
        enabled_started = await enabled.start_http_if_enabled()
        assert enabled._bound_port is not None
        status_health, payload_health = await _http_get_json("127.0.0.1", enabled._bound_port, "/healthz")
        status_ready, payload_ready = await _http_get_json("127.0.0.1", enabled._bound_port, "/readyz")
        snapshot = enabled.snapshot()
        await enabled.stop_http_if_started()
        await runtime.stop()
        return disabled_started, enabled_started, status_health, status_ready, payload_health, payload_ready, snapshot

    disabled_started, enabled_started, status_health, status_ready, payload_health, payload_ready, snapshot = asyncio.run(_run())
    assert disabled_started is False
    assert enabled_started is True
    assert status_health == 200
    assert status_ready == 200
    assert payload_health["runtime"]["running"] is True
    assert payload_ready["ready"] is True
    assert snapshot["runtime"]["running"] is True
    assert snapshot["http_enabled"] is True
    assert snapshot["http_started"] is True


def test_health_snapshot_includes_operational_signals(tmp_path):
    import asyncio

    from claudebot_gateway.config import GatewayConfig
    from claudebot_gateway.runtime import GatewayApp

    async def _run() -> dict[str, object]:
        app = GatewayApp(
            config=GatewayConfig(
                workspace_root=tmp_path / "workspaces",
                sqlite_path=tmp_path / "state" / "gateway.db",
            )
        )
        return app.status()

    snapshot = asyncio.run(_run())
    signals = snapshot["signals"]
    assert signals["inbound_queue_depth"] == 0
    assert signals["outbound_queue_depth"] == 0
    assert "due_cron_jobs" in signals


def test_health_snapshot_includes_channel_status(tmp_path):
    import asyncio

    from claudebot_gateway.config import GatewayConfig
    from claudebot_gateway.runtime import GatewayApp

    async def _run() -> dict[str, object]:
        app = GatewayApp(
            config=GatewayConfig(
                workspace_root=tmp_path / "workspaces",
                sqlite_path=tmp_path / "state" / "gateway.db",
            )
        )
        return app.status()

    snapshot = asyncio.run(_run())
    signals = snapshot["signals"]
    channels = signals.get("channels")
    assert isinstance(channels, dict)
    assert "cli" in channels
    assert channels["cli"]["state"] == "stopped"
