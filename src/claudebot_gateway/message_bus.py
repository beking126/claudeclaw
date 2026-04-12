import asyncio
from typing import Any


class MessageBus:
    def __init__(self, inbound_maxsize: int = 1000, outbound_maxsize: int = 1000):
        self.inbound: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=inbound_maxsize)
        self.outbound: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=outbound_maxsize)
        self._inbound_intake_open = True

    async def publish_inbound(self, item: dict[str, Any]) -> None:
        if not self._inbound_intake_open:
            raise RuntimeError("Inbound intake is closed")
        await self.inbound.put(item)

    async def try_publish_inbound(self, item: dict[str, Any]) -> bool:
        if not self._inbound_intake_open:
            return False
        try:
            self.inbound.put_nowait(item)
        except asyncio.QueueFull:
            return False
        return True

    async def publish_outbound(self, item: dict[str, Any]) -> None:
        await self.outbound.put(item)

    def close_inbound_intake(self) -> None:
        self._inbound_intake_open = False
