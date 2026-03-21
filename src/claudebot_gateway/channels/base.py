from abc import ABC, abstractmethod


class BaseChannel(ABC):
    def __init__(self) -> None:
        self._running = False

    async def start(self) -> None:
        self._running = True

    async def stop(self) -> None:
        self._running = False

    async def poll_once(self) -> None:
        return None

    def health(self) -> dict[str, object]:
        return {"running": self._running}

    @abstractmethod
    async def send(self, message: dict[str, str]) -> None:
        raise NotImplementedError
