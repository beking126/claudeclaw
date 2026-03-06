import inspect
from typing import Any, Awaitable, Callable

from claudebot_gateway.message_bus import MessageBus


TurnHandler = Callable[[dict[str, Any]], dict[str, Any] | Awaitable[dict[str, Any]]]


class AgentRunner:
    def __init__(self, turn_handler: TurnHandler):
        self._turn_handler = turn_handler

    async def process_once(self, bus: MessageBus) -> dict[str, Any]:
        inbound = await bus.inbound.get()
        outbound = self._turn_handler(inbound)
        if inspect.isawaitable(outbound):
            outbound = await outbound
        await bus.publish_outbound(outbound)
        return outbound
