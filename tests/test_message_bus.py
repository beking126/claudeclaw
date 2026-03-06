import asyncio


def test_rejects_newest_when_inbound_queue_full():
    from claudebot_gateway.message_bus import MessageBus

    async def _run() -> bool:
        bus = MessageBus(inbound_maxsize=1)
        await bus.publish_inbound({"id": "1"})
        return await bus.try_publish_inbound({"id": "2"})

    accepted = asyncio.run(_run())
    assert accepted is False
