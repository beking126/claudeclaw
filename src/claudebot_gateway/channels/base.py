import asyncio
import logging
from abc import ABC

_LOGGER = logging.getLogger("claudebot_gateway.channels.base")


class BaseChannel(ABC):
    def __init__(
        self,
        *,
        send_max_attempts: int = 1,
        base_backoff_seconds: float = 0.5,
        max_backoff_seconds: float = 8.0,
    ) -> None:
        self._running = False
        self._send_max_attempts = max(1, send_max_attempts)
        self._base_backoff_seconds = max(0.0, base_backoff_seconds)
        self._max_backoff_seconds = max(self._base_backoff_seconds, max_backoff_seconds)
        self._last_error: str | None = None

    async def start(self) -> None:
        self._running = True

    async def stop(self) -> None:
        self._running = False

    async def poll_once(self) -> None:
        return None

    def health(self) -> dict[str, object]:
        return {"running": self._running}

    async def send(self, message: dict[str, str]) -> None:
        if not self._running:
            raise RuntimeError(f"{self.__class__.__name__} is not running")
        last_exception: Exception | None = None
        for attempt in range(1, self._send_max_attempts + 1):
            try:
                await self._send_message(message)
                self._last_error = None
                return
            except Exception as exc:
                last_exception = exc
                self._last_error = str(exc)
                if attempt == self._send_max_attempts:
                    break
                backoff = self._next_backoff_seconds(attempt)
                _LOGGER.warning(
                    "%s_send_retry attempt=%s retry_in=%s error=%s",
                    self.__class__.__name__.lower(),
                    attempt,
                    f"{backoff:.2f}s",
                    self._last_error,
                )
                if backoff > 0:
                    await asyncio.sleep(backoff)
        if last_exception is None:
            raise RuntimeError(f"{self.__class__.__name__} send failed without exception")
        raise last_exception

    def _next_backoff_seconds(self, attempt: int) -> float:
        delay = self._base_backoff_seconds * (2 ** max(0, attempt - 1))
        return min(delay, self._max_backoff_seconds)

    async def _send_message(self, message: dict[str, str]) -> None:
        raise NotImplementedError
