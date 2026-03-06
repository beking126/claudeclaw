import asyncio


class _HealthyChannel:
    async def poll_once(self) -> bool:
        return True


class _FailingChannel:
    async def poll_once(self) -> bool:
        raise RuntimeError("boom")


def test_channel_failure_does_not_stop_manager():
    from claudebot_gateway.channel_manager import ChannelManager

    async def _run() -> dict[str, bool]:
        manager = ChannelManager(
            channels={
                "ok": _HealthyChannel(),
                "bad": _FailingChannel(),
            }
        )
        return await manager.poll_once_all()

    result = asyncio.run(_run())
    assert result["ok"] is True
    assert result["bad"] is False
