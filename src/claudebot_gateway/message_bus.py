import asyncio
from typing import Any


class MessageBus:
    def __init__(self, inbound_maxsize: int = 1000, outbound_maxsize: int = 1000):
        self.inbound: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=inbound_maxsize)
        self.outbound: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=outbound_maxsize)

    async def publish_inbound(self, item: dict[str, Any]) -> None:
        await self.inbound.put(item)

    async def try_publish_inbound(self, item: dict[str, Any]) -> bool:
        try:
            self.inbound.put_nowait(item)
        except asyncio.QueueFull:
            return False
        return True

    async def publish_outbound(self, item: dict[str, Any]) -> None:
        await self.outbound.put(item)

    def make_busy_rejection(self, channel: str, destination: str) -> dict[str, str]:
        return {
            "channel": channel,
            "destination": destination,
            "text": "System busy. Try again shortly.",
        }
