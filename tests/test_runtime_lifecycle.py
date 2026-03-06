import asyncio


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
