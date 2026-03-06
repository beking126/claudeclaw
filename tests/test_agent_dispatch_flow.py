import asyncio

from claudebot_gateway.message_bus import MessageBus


class _FakeAdapter:
    def __init__(self):
        self.sent: list[dict[str, str]] = []

    async def send(self, message: dict[str, str]) -> None:
        self.sent.append(message)


def test_inbound_generates_outbound_with_target_channel():
    from claudebot_gateway.agent_runner import AgentRunner
    from claudebot_gateway.outbound_dispatcher import OutboundDispatcher

    async def _run() -> list[dict[str, str]]:
        bus = MessageBus()
        adapter = _FakeAdapter()
        runner = AgentRunner(
            turn_handler=lambda inbound: {
                "channel": "telegram",
                "destination": inbound["destination"],
                "text": f"echo:{inbound['text']}",
            }
        )
        dispatcher = OutboundDispatcher(adapters={"telegram": adapter})
        await bus.publish_inbound({"channel": "cli", "destination": "chat:1", "text": "hi"})
        await runner.process_once(bus)
        await dispatcher.dispatch_once(bus)
        return adapter.sent

    sent = asyncio.run(_run())
    assert sent[0]["channel"] == "telegram"
    assert sent[0]["destination"] == "chat:1"
    assert sent[0]["text"] == "echo:hi"
