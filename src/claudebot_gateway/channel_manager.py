import asyncio
from collections.abc import Awaitable, Callable
from typing import Any
from claudebot_gateway.channels.base import BaseChannel
import logging

_LOGGER = logging.getLogger(__name__)

class ChannelManager:
    def __init__(self, channels: dict[str, BaseChannel]):
        self._channels = channels
        self._status: dict[str, dict[str, object]] = {
            name: {
                "state": "stopped",
                "last_error": None,
                "reconnect_attempts": 0,
            }
            for name in channels
        }

    async def start_all(self) -> dict[str, bool]:
        return await self._run_all(self._run_start)

    async def stop_all(self) -> dict[str, bool]:
        return await self._run_all(self._run_stop)

    async def poll_once_all(self) -> dict[str, bool]:
        return await self._run_all(self._run_poll_once)

    def status_snapshot(self) -> dict[str, dict[str, object]]:
        return {
            name: {
                "state": status["state"],
                "last_error": status["last_error"],
                "reconnect_attempts": status["reconnect_attempts"],
            }
            for name, status in self._status.items()
        }

    def _increment_reconnect_attempts(self, name: str) -> None:
        current = self._status[name].get("reconnect_attempts")
        attempts = current if isinstance(current, int) else 0
        self._status[name]["reconnect_attempts"] = attempts + 1

    async def _run_all(
        self, operation: Callable[[str, Any], Awaitable[tuple[str, bool]]]
    ) -> dict[str, bool]:
        tasks = [operation(name, channel) for name, channel in self._channels.items()]
        results = await asyncio.gather(*tasks)
        return dict(results)

    async def _run_start(self, name: str, channel: BaseChannel) -> tuple[str, bool]:
        try:
            _LOGGER.info(f"Starting channel {name}...")
            await channel.start()
        except Exception as exc:
            self._status[name]["state"] = "degraded"
            self._status[name]["last_error"] = str(exc)
            self._increment_reconnect_attempts(name)
            _LOGGER.error(f"Error starting channel {name}: {exc}")
            return name, False
        self._status[name]["state"] = "running"
        self._status[name]["last_error"] = None
        return name, True

    async def _run_stop(self, name: str, channel: BaseChannel) -> tuple[str, bool]:
        try:
            await channel.stop()
        except Exception as exc:
            self._status[name]["state"] = "degraded"
            self._status[name]["last_error"] = str(exc)
            return name, False
        self._status[name]["state"] = "stopped"
        return name, True

    async def _run_poll_once(self, name: str, channel: BaseChannel) -> tuple[str, bool]:
        try:
            await channel.poll_once()
        except Exception as exc:
            self._status[name]["state"] = "degraded"
            self._status[name]["last_error"] = str(exc)
            self._increment_reconnect_attempts(name)
            _LOGGER.error(f"Error polling channel {name}: {exc}")
            return name, False
        if self._status[name]["state"] != "stopped":
            self._status[name]["state"] = "running"
            self._status[name]["last_error"] = None
        return name, True
