import asyncio


def test_rejects_newest_when_inbound_queue_full():
    from claudebot_gateway.message_bus import MessageBus

    async def _run() -> bool:
        bus = MessageBus(inbound_maxsize=1)
        await bus.publish_inbound({"id": "1"})
        return await bus.try_publish_inbound({"id": "2"})

    accepted = asyncio.run(_run())
    assert accepted is False


def test_rejects_inbound_when_intake_closed():
    from claudebot_gateway.message_bus import MessageBus

    async def _run() -> tuple[bool, bool]:
        bus = MessageBus(inbound_maxsize=2)
        bus.close_inbound_intake()
        accepted_try = await bus.try_publish_inbound({"id": "1"})
        try:
            await bus.publish_inbound({"id": "2"})
            accepted_publish = True
        except RuntimeError:
            accepted_publish = False
        return accepted_try, accepted_publish

    accepted_try, accepted_publish = asyncio.run(_run())
    assert accepted_try is False
    assert accepted_publish is False
