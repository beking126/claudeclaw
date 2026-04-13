class SlidingWindowRateLimiter:
    def __init__(self, *, max_requests: int, window_seconds: float):
        self._max_requests = max_requests
        self._window_seconds = window_seconds
        self._buckets: dict[str, tuple[float, int]] = {}

    @property
    def max_requests(self) -> int:
        return self._max_requests

    def is_allowed(self, key: str, *, now: float) -> bool:
        if self._max_requests <= 0:
            return True
        if len(self._buckets) > 1000:
            expired = [k for k, (ws, _) in self._buckets.items() if now - ws >= self._window_seconds]
            for k in expired:
                del self._buckets[k]
        window_start, count = self._buckets.get(key, (0.0, 0))
        if now - window_start >= self._window_seconds:
            window_start = now
            count = 0
        count += 1
        self._buckets[key] = (window_start, count)
        return count <= self._max_requests

    def update_limits(self, *, max_requests: int, window_seconds: float) -> None:
        self._max_requests = max_requests
        self._window_seconds = window_seconds
        self._buckets.clear()
