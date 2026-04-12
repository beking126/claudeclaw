import logging
from typing import Any

from claudebot_gateway.message_bus import MessageBus

_LOGGER = logging.getLogger("claudebot_gateway.outbound_dispatcher")


class OutboundDispatcher:
    def __init__(self, adapters: dict[str, Any]):
        self._adapters = adapters

    async def dispatch_once(self, bus: MessageBus) -> bool:
        outbound = await bus.outbound.get()
        channel = outbound["channel"]
        destination = str(outbound.get("destination", ""))
        adapter = self._adapters.get(channel)
        if adapter is None:
            _LOGGER.warning(
                "outbound_dispatch_missing_adapter channel=%s destination=%s",
                channel,
                destination,
            )
            return False
        try:
            await adapter.send(outbound)
        except Exception:
            _LOGGER.exception(
                "outbound_dispatch_failed channel=%s destination=%s",
                channel,
                destination,
            )
            return False
        _LOGGER.info(
            "outbound_dispatched channel=%s destination=%s",
            channel,
            destination,
        )
        return True
