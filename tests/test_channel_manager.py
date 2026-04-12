import asyncio

from claudebot_gateway.channels.base import BaseChannel


class _HealthyChannel(BaseChannel):
    async def start(self) -> None:
        return None

    async def stop(self) -> None:
        return None

class _LifecycleChannel(_HealthyChannel):
    def __init__(self) -> None:
        self.started = 0
        self.stopped = 0

    async def start(self) -> None:
        self.started += 1

    async def stop(self) -> None:
        self.stopped += 1

    async def send(self, message: dict[str, str]) -> None:
        _ = message


def test_channel_start_failure_does_not_stop_manager():
    from claudebot_gateway.channel_manager import ChannelManager

    async def _run() -> dict[str, bool]:
        class _FailingStartChannel(BaseChannel):
            async def start(self) -> None:
                raise RuntimeError("boom")

            async def stop(self) -> None:
                return None

        manager = ChannelManager(
            channels={
                "ok": _HealthyChannel(),
                "bad": _FailingStartChannel(),
            }
        )
        return await manager.start_all()

    result = asyncio.run(_run())
    assert result["ok"] is True
    assert result["bad"] is False


def test_channel_manager_lifecycle_and_status_snapshot():
    from claudebot_gateway.channel_manager import ChannelManager

    async def _run() -> tuple[dict[str, object], dict[str, object], int, int]:
        channel = _LifecycleChannel()
        manager = ChannelManager(channels={"x": channel})
        await manager.start_all()
        running = manager.status_snapshot()
        await manager.stop_all()
        stopped = manager.status_snapshot()
        return running["x"], stopped["x"], channel.started, channel.stopped

    running, stopped, started, stopped_calls = asyncio.run(_run())
    assert started == 1
    assert stopped_calls == 1
    assert running["state"] == "running"
    assert running["last_error"] is None
    assert stopped["state"] == "stopped"


def test_channel_manager_start_failure_marks_degraded():
    from claudebot_gateway.channel_manager import ChannelManager

    class _StartFailChannel(BaseChannel):
        async def start(self) -> None:
            raise RuntimeError("connect failed")

        async def stop(self) -> None:
            return None

    async def _run() -> dict[str, object]:
        manager = ChannelManager(channels={"x": _StartFailChannel()})
        await manager.start_all()
        return manager.status_snapshot()["x"]

    status = asyncio.run(_run())
    assert status["state"] == "degraded"
    assert status["reconnect_attempts"] == 1
