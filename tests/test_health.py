import asyncio


def test_http_health_only_available_when_feature_flag_enabled():
    from claudebot_gateway.health import HealthService
    from claudebot_gateway.runtime import GatewayRuntime

    async def _run() -> tuple[bool, bool, dict[str, object]]:
        runtime = GatewayRuntime(workers=[])
        await runtime.start()
        disabled = HealthService(runtime=runtime, http_enabled=False)
        enabled = HealthService(runtime=runtime, http_enabled=True)
        disabled_started = await disabled.start_http_if_enabled()
        enabled_started = await enabled.start_http_if_enabled()
        snapshot = enabled.snapshot()
        await runtime.stop()
        return disabled_started, enabled_started, snapshot

    disabled_started, enabled_started, snapshot = asyncio.run(_run())
    assert disabled_started is False
    assert enabled_started is True
    assert snapshot["runtime"]["running"] is True
    assert snapshot["http_enabled"] is True
