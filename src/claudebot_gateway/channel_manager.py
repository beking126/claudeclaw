import asyncio
from typing import Any


class ChannelManager:
    def __init__(self, channels: dict[str, Any]):
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
        async def _start(name: str, channel: Any) -> tuple[str, bool]:
            start_method = getattr(channel, "start", None)
            if callable(start_method):
                try:
                    await start_method()
                    self._status[name]["state"] = "running"
                    self._status[name]["last_error"] = None
                    return name, True
                except Exception as exc:
                    self._status[name]["state"] = "degraded"
                    self._status[name]["last_error"] = str(exc)
                    self._increment_reconnect_attempts(name)
                    return name, False
            self._status[name]["state"] = "running"
            self._status[name]["last_error"] = None
            return name, True

        tasks = [_start(name, channel) for name, channel in self._channels.items()]
        results = await asyncio.gather(*tasks)
        return dict(results)

    async def stop_all(self) -> dict[str, bool]:
        async def _stop(name: str, channel: Any) -> tuple[str, bool]:
            stop_method = getattr(channel, "stop", None)
            if callable(stop_method):
                try:
                    await stop_method()
                except Exception as exc:
                    self._status[name]["state"] = "degraded"
                    self._status[name]["last_error"] = str(exc)
                    return name, False
            self._status[name]["state"] = "stopped"
            return name, True

        tasks = [_stop(name, channel) for name, channel in self._channels.items()]
        results = await asyncio.gather(*tasks)
        return dict(results)

    async def poll_once_all(self) -> dict[str, bool]:
        async def _run(name: str, channel: Any) -> tuple[str, bool]:
            poll_once = getattr(channel, "poll_once", None)
            if not callable(poll_once):
                return name, True
            try:
                await poll_once()
                if self._status[name]["state"] != "stopped":
                    self._status[name]["state"] = "running"
                    self._status[name]["last_error"] = None
                return name, True
            except Exception as exc:
                self._status[name]["state"] = "degraded"
                self._status[name]["last_error"] = str(exc)
                self._increment_reconnect_attempts(name)
                return name, False

        tasks = [_run(name, channel) for name, channel in self._channels.items()]
        results = await asyncio.gather(*tasks)
        return dict(results)

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
