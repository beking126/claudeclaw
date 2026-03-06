from claudebot_gateway.runtime import GatewayRuntime


class HealthService:
    def __init__(self, *, runtime: GatewayRuntime, http_enabled: bool):
        self._runtime = runtime
        self._http_enabled = http_enabled
        self._http_started = False

    async def start_http_if_enabled(self) -> bool:
        if not self._http_enabled:
            self._http_started = False
            return False
        self._http_started = True
        return True

    def snapshot(self) -> dict[str, object]:
        return {
            "http_enabled": self._http_enabled,
            "http_started": self._http_started,
            "runtime": self._runtime.health_snapshot(),
        }
