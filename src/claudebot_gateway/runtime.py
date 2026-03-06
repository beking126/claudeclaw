import asyncio
from collections.abc import Coroutine
from typing import Any, Callable


Worker = Callable[[asyncio.Event], Coroutine[Any, Any, None]]


class GatewayRuntime:
    def __init__(self, *, workers: list[Worker], drain_timeout_seconds: float = 2.0):
        self._workers = workers
        self._drain_timeout_seconds = drain_timeout_seconds
        self._stop_event = asyncio.Event()
        self._tasks: list[asyncio.Task[None]] = []
        self._started = False
        self._running = False
        self._stopped = False
        self._unhandled_errors = 0

    async def start(self) -> None:
        if self._running:
            return
        self._started = True
        self._stopped = False
        self._running = True
        self._stop_event.clear()
        self._tasks = []
        for worker in self._workers:
            task: asyncio.Task[None] = asyncio.create_task(worker(self._stop_event))
            task.add_done_callback(self._handle_task_done)
            self._tasks.append(task)

    async def stop(self) -> None:
        if not self._started or self._stopped:
            return
        self._running = False
        self._stop_event.set()
        try:
            await asyncio.wait_for(asyncio.gather(*self._tasks, return_exceptions=True), timeout=self._drain_timeout_seconds)
        except asyncio.TimeoutError:
            for task in self._tasks:
                if not task.done():
                    task.cancel()
            await asyncio.gather(*self._tasks, return_exceptions=True)
        self._stopped = True

    def health_snapshot(self) -> dict[str, object]:
        return {
            "started": self._started,
            "running": self._running,
            "stopped": self._stopped,
            "worker_count": len(self._workers),
            "active_tasks": sum(0 if t.done() else 1 for t in self._tasks),
            "unhandled_errors": self._unhandled_errors,
        }

    def _handle_task_done(self, task: asyncio.Task[None]) -> None:
        try:
            task.result()
        except asyncio.CancelledError:
            return
        except Exception:
            self._unhandled_errors += 1
