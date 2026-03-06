from typing import Any

from claudebot_gateway.message_bus import MessageBus


class OutboundDispatcher:
    def __init__(self, adapters: dict[str, Any]):
        self._adapters = adapters

    async def dispatch_once(self, bus: MessageBus) -> bool:
        outbound = await bus.outbound.get()
        channel = outbound["channel"]
        adapter = self._adapters.get(channel)
        if adapter is None:
            return False
        await adapter.send(outbound)
        return True
