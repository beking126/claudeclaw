import asyncio
from typing import Any


class ChannelManager:
    def __init__(self, channels: dict[str, Any]):
        self._channels = channels

    async def poll_once_all(self) -> dict[str, bool]:
        async def _run(name: str, channel: Any) -> tuple[str, bool]:
            try:
                await channel.poll_once()
                return name, True
            except Exception:
                return name, False

        tasks = [_run(name, channel) for name, channel in self._channels.items()]
        results = await asyncio.gather(*tasks)
        return dict(results)
