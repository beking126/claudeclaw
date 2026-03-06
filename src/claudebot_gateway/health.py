from typing import Callable, Protocol


class RuntimeHealth(Protocol):
    def health_snapshot(self) -> dict[str, object]:
        ...


class HealthService:
    def __init__(
        self,
        *,
        runtime: RuntimeHealth,
        http_enabled: bool,
        signal_provider: Callable[[], dict[str, object]] | None = None,
    ):
        self._runtime = runtime
        self._http_enabled = http_enabled
        self._http_started = False
        self._signal_provider = signal_provider

    async def start_http_if_enabled(self) -> bool:
        if not self._http_enabled:
            self._http_started = False
            return False
        self._http_started = True
        return True

    def snapshot(self) -> dict[str, object]:
        signals = {} if self._signal_provider is None else self._signal_provider()
        return {
            "http_enabled": self._http_enabled,
            "http_started": self._http_started,
            "runtime": self._runtime.health_snapshot(),
            "signals": signals,
        }
