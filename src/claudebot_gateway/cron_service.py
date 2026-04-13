import asyncio
from pathlib import Path
import time
from typing import Any, Awaitable, Callable, Literal
from datetime import datetime, timezone

from claudebot_gateway.persistence.sqlite_store import SqliteStore, coerce_to_str_dict
from claudebot_gateway.workspaces import WorkspaceResolver


SendFunc = Callable[[dict[str, str]], Awaitable[None]]
AgentFunc = Callable[[str, Path], Awaitable[str]]

ScheduleKind = Literal["every", "at", "cron"]
RunStatus = Literal["ok", "error"]
DeliveryStatus = Literal["ok", "dropped"]


class CronService:
    def __init__(
        self,
        db_path: Path,
        workspace_root: Path,
        *,
        store: SqliteStore | None = None,
        delivery_max_attempts: int = 3,
        delivery_retry_backoff_seconds: float = 0.05,
        delivery_retry_backoff_max_seconds: float = 0.5,
    ):
        """
        Initialize cron execution service.

        Args:
            db_path: SQLite database path for persistence fallback.
            workspace_root: Root directory used for cron workspaces.
            store (SqliteStore | None): Optional injected persistence store for tests/integration.
            delivery_max_attempts: Maximum outbound delivery attempts per run.
            delivery_retry_backoff_seconds: Initial retry backoff in seconds.
            delivery_retry_backoff_max_seconds: Maximum retry backoff in seconds.
        """
        self._store = store or SqliteStore(db_path=db_path)
        self._resolver = WorkspaceResolver(workspace_root)
        self._delivery_max_attempts = max(1, delivery_max_attempts)
        self._delivery_retry_backoff_seconds = max(0.0, delivery_retry_backoff_seconds)
        self._delivery_retry_backoff_max_seconds = max(0.0, delivery_retry_backoff_max_seconds)

    async def run_job_once(
        self,
        *,
        job_id: str,
        prompt: str,
        target: dict[str, str],
        send_func: SendFunc,
        agent_func: AgentFunc,
    ) -> dict[str, str]:
        workspace = self._resolver.cron(job_id)
        workspace.mkdir(parents=True, exist_ok=True)
        report = await agent_func(prompt, workspace)
        failure_reason: str | None = None
        delivery_status: DeliveryStatus = "ok"
        run_status: RunStatus = "ok"
        message = {
            "channel": target["channel"],
            "destination": target["destination"],
            "text": report,
        }
        failure_reason = await self._send_with_retry(message=message, send_func=send_func)
        if failure_reason is not None:
            delivery_status = "dropped"
            run_status = "error"
        self._store.record_cron_run(
            job_id=job_id,
            prompt=prompt,
            workspace_key=workspace.name,
            status=run_status,
            error=failure_reason,
        )
        self._store.record_delivery(
            job_id=job_id,
            channel=target["channel"],
            destination=target["destination"],
            status=delivery_status,
            failure_reason=failure_reason,
        )
        return {"run_status": run_status, "delivery_status": delivery_status}

    async def schedule_job(
        self,
        *,
        job_id: str,
        prompt: str,
        target: dict[str, str],
        interval_seconds: int | None = None,
        schedule_kind: ScheduleKind = "every",
        schedule_value: str | None = None,
        run_at_epoch_seconds: float | None = None,
    ) -> None:
        normalized_kind = schedule_kind.strip().lower()
        first_run = time.time() if run_at_epoch_seconds is None else run_at_epoch_seconds
        normalized_interval = 0
        normalized_value = ""
        if normalized_kind == "every":
            if interval_seconds is None:
                raise ValueError("interval_seconds is required for schedule_kind='every'")
            normalized_interval = max(1, int(interval_seconds))
            normalized_value = str(normalized_interval)
        elif normalized_kind == "at":
            normalized_value = str(first_run)
        elif normalized_kind == "cron":
            if not schedule_value:
                raise ValueError("schedule_value is required for schedule_kind='cron'")
            normalized_value = schedule_value.strip()
        else:
            raise ValueError(f"Unsupported schedule_kind: {schedule_kind}")
        self._store.upsert_cron_job(
            job_id=job_id,
            prompt=prompt,
            channel=target["channel"],
            destination=target["destination"],
            interval_seconds=normalized_interval,
            schedule_kind=normalized_kind,
            schedule_value=normalized_value,
            next_run_epoch_seconds=first_run,
        )

    async def run_due_jobs(
        self,
        *,
        now_epoch_seconds: float | None = None,
        send_func: SendFunc,
        agent_func: AgentFunc,
    ) -> int:
        now = time.time() if now_epoch_seconds is None else now_epoch_seconds
        jobs = self._store.list_due_cron_jobs(now_epoch_seconds=now)
        for job in jobs:
            await self.run_job_once(
                job_id=str(job["job_id"]),
                prompt=str(job["prompt"]),
                target={"channel": str(job["channel"]), "destination": str(job["destination"])},
                send_func=send_func,
                agent_func=agent_func,
            )
            job_id = str(job["job_id"])
            schedule_kind = str(job.get("schedule_kind", "every")).strip().lower()
            if schedule_kind == "at":
                self._store.delete_cron_job(job_id=job_id)
                continue
            if schedule_kind == "cron":
                schedule_value = str(job.get("schedule_value", ""))
                next_run = self._next_cron_epoch_seconds(schedule_value, from_epoch_seconds=now)
            else:
                interval_seconds = int(job.get("interval_seconds", 0))
                next_run = now + max(1, interval_seconds)
            self._store.update_cron_job_next_run(job_id=job_id, next_run_epoch_seconds=next_run)
        return len(jobs)

    def due_job_count(self, *, now_epoch_seconds: float | None = None) -> int:
        now = time.time() if now_epoch_seconds is None else now_epoch_seconds
        return self._store.count_due_cron_jobs(now_epoch_seconds=now)

    def list_jobs(self) -> list[dict[str, Any]]:
        return self._store.list_all_cron_jobs()

    def remove_job(self, *, job_id: str) -> bool:
        deleted = self._store.delete_cron_job(job_id=job_id)
        return deleted > 0

    def get_last_delivery(self, job_id: str) -> dict[str, str] | None:
        delivery = self._store.get_last_delivery_by_job(job_id)
        if delivery is None:
            return None
        return coerce_to_str_dict(delivery)

    def _next_cron_epoch_seconds(self, expression: str, *, from_epoch_seconds: float) -> float:
        fields = expression.strip().split()
        if len(fields) != 5:
            raise ValueError("Cron expression must have 5 fields")
        minute, hour, day, month, weekday = fields
        base = int(from_epoch_seconds // 60) * 60
        candidate = base + 60
        max_checks = 525600
        for _ in range(max_checks):
            dt = datetime.fromtimestamp(candidate, tz=timezone.utc)
            cron_weekday = (dt.weekday() + 1) % 7
            if (
                self._matches_field(minute, dt.minute, 0, 59)
                and self._matches_field(hour, dt.hour, 0, 23)
                and self._matches_field(day, dt.day, 1, 31)
                and self._matches_field(month, dt.month, 1, 12)
                and self._matches_field(weekday, cron_weekday, 0, 7)
            ):
                return float(candidate)
            candidate += 60
        raise ValueError("Unable to find next run time for cron expression")

    def _matches_field(self, field: str, value: int, minimum: int, maximum: int) -> bool:
        token = field.strip()
        if token == "*":
            return True
        if "," in token:
            return any(self._matches_field(part, value, minimum, maximum) for part in token.split(","))
        if token.startswith("*/"):
            step = int(token[2:])
            if step <= 0:
                raise ValueError("Cron step must be greater than zero")
            return value % step == 0
        if "-" in token:
            parts = token.split("-", 1)
            lo = int(parts[0])
            hi = int(parts[1])
            if lo < minimum or hi > maximum:
                raise ValueError(f"Cron range {token} out of bounds {minimum}-{maximum}")
            return lo <= value <= hi
        target = int(token)
        if target < minimum or target > maximum:
            raise ValueError(f"Cron value {target} out of range {minimum}-{maximum}")
        if maximum == 7 and target == 7:
            target = 0
        return value == target

    async def _send_with_retry(self, *, message: dict[str, str], send_func: SendFunc) -> str | None:
        failure_reason: str | None = None
        for attempt in range(1, self._delivery_max_attempts + 1):
            try:
                await send_func(message)
                return None
            except Exception as exc:
                failure_reason = str(exc)
                if attempt == self._delivery_max_attempts:
                    return failure_reason
                delay = min(
                    self._delivery_retry_backoff_seconds * attempt,
                    self._delivery_retry_backoff_max_seconds,
                )
                if delay > 0:
                    await asyncio.sleep(delay)
        return failure_reason
