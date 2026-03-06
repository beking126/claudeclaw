from pathlib import Path
import time
from typing import Awaitable, Callable

from claudebot_gateway.persistence.sqlite_store import SqliteStore
from claudebot_gateway.workspaces import WorkspaceResolver


SendFunc = Callable[[dict[str, str]], Awaitable[None]]
AgentFunc = Callable[[str, Path], Awaitable[str]]


class CronService:
    def __init__(self, db_path: Path, workspace_root: Path):
        self._store = SqliteStore(db_path=db_path)
        self._resolver = WorkspaceResolver(workspace_root)

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
        delivery_status = "ok"
        run_status = "ok"
        try:
            await send_func(
                {
                    "channel": target["channel"],
                    "destination": target["destination"],
                    "text": report,
                }
            )
        except Exception as exc:
            failure_reason = str(exc)
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
        interval_seconds: int,
        run_at_epoch_seconds: float | None = None,
    ) -> None:
        first_run = time.time() if run_at_epoch_seconds is None else run_at_epoch_seconds
        self._store.upsert_cron_job(
            job_id=job_id,
            prompt=prompt,
            channel=target["channel"],
            destination=target["destination"],
            interval_seconds=interval_seconds,
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
            interval_seconds = int(job["interval_seconds"])
            next_run = now + max(1, interval_seconds)
            self._store.update_cron_job_next_run(
                job_id=str(job["job_id"]),
                next_run_epoch_seconds=next_run,
            )
        return len(jobs)

    def due_job_count(self, *, now_epoch_seconds: float | None = None) -> int:
        now = time.time() if now_epoch_seconds is None else now_epoch_seconds
        return len(self._store.list_due_cron_jobs(now_epoch_seconds=now))

    def get_last_delivery(self, job_id: str) -> dict[str, str] | None:
        delivery = self._store.get_last_delivery_by_job(job_id)
        if delivery is None:
            return None
        return {k: "" if v is None else str(v) for k, v in delivery.items()}
