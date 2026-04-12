import asyncio
from pathlib import Path


def test_cron_delivery_failure_is_recorded_and_dropped(tmp_path: Path):
    from claudebot_gateway.cron_service import CronService

    async def _run() -> tuple[dict[str, str], dict[str, str] | None]:
        service = CronService(db_path=tmp_path / "gateway.db", workspace_root=tmp_path / "workspaces")

        async def send(_: dict[str, str]) -> None:
            raise RuntimeError("channel down")

        async def agent(_: str, __: Path) -> str:
            return "report"

        result = await service.run_job_once(
            job_id="job-01",
            prompt="daily report",
            target={"channel": "telegram", "destination": "chat:1"},
            send_func=send,
            agent_func=agent,
        )
        delivery = service.get_last_delivery("job-01")
        return result, delivery

    result, delivery = asyncio.run(_run())
    assert result["delivery_status"] == "dropped"
    assert result["run_status"] == "error"
    assert delivery is not None
    assert delivery["status"] == "dropped"
    assert delivery["job_id"] == "job-01"


def test_cron_scheduler_persists_jobs_and_runs_due_jobs(tmp_path: Path):
    from claudebot_gateway.cron_service import CronService

    async def _run() -> tuple[int, list[dict[str, str]], dict[str, str] | None]:
        db_path = tmp_path / "gateway.db"
        workspace_root = tmp_path / "workspaces"
        service = CronService(db_path=db_path, workspace_root=workspace_root)
        await service.schedule_job(
            job_id="job-02",
            prompt="daily report",
            target={"channel": "telegram", "destination": "chat:2"},
            interval_seconds=60,
            run_at_epoch_seconds=0.0,
        )
        restarted = CronService(db_path=db_path, workspace_root=workspace_root)
        sent: list[dict[str, str]] = []

        async def send(message: dict[str, str]) -> None:
            sent.append(message)

        async def agent(_: str, __: Path) -> str:
            return "report-body"

        count = await restarted.run_due_jobs(now_epoch_seconds=1.0, send_func=send, agent_func=agent)
        delivery = restarted.get_last_delivery("job-02")
        return count, sent, delivery

    count, sent, delivery = asyncio.run(_run())
    assert count == 1
    assert len(sent) == 1
    assert sent[0]["destination"] == "chat:2"
    assert delivery is not None
    assert delivery["status"] == "ok"


def test_cron_scheduler_supports_at_one_shot_jobs(tmp_path: Path):
    from claudebot_gateway.cron_service import CronService

    async def _run() -> tuple[int, int, list[dict[str, str]]]:
        service = CronService(db_path=tmp_path / "gateway.db", workspace_root=tmp_path / "workspaces")
        sent: list[dict[str, str]] = []

        async def send(message: dict[str, str]) -> None:
            sent.append(message)

        async def agent(_: str, __: Path) -> str:
            return "one-shot-report"

        await service.schedule_job(
            job_id="job-at-01",
            prompt="run once",
            target={"channel": "telegram", "destination": "chat:at"},
            schedule_kind="at",
            run_at_epoch_seconds=0.0,
        )
        first = await service.run_due_jobs(now_epoch_seconds=1.0, send_func=send, agent_func=agent)
        second = await service.run_due_jobs(now_epoch_seconds=2.0, send_func=send, agent_func=agent)
        return first, second, sent

    first, second, sent = asyncio.run(_run())
    assert first == 1
    assert second == 0
    assert len(sent) == 1
    assert sent[0]["destination"] == "chat:at"


def test_cron_scheduler_supports_cron_expression_jobs(tmp_path: Path):
    from claudebot_gateway.cron_service import CronService

    async def _run() -> tuple[int, int, int]:
        service = CronService(db_path=tmp_path / "gateway.db", workspace_root=tmp_path / "workspaces")
        sent: list[dict[str, str]] = []

        async def send(message: dict[str, str]) -> None:
            sent.append(message)

        async def agent(_: str, __: Path) -> str:
            return "cron-expression-report"

        await service.schedule_job(
            job_id="job-cron-01",
            prompt="run every five minutes",
            target={"channel": "telegram", "destination": "chat:cron"},
            schedule_kind="cron",
            schedule_value="*/5 * * * *",
            run_at_epoch_seconds=0.0,
        )
        first = await service.run_due_jobs(now_epoch_seconds=1.0, send_func=send, agent_func=agent)
        second = await service.run_due_jobs(now_epoch_seconds=299.0, send_func=send, agent_func=agent)
        third = await service.run_due_jobs(now_epoch_seconds=301.0, send_func=send, agent_func=agent)
        return first, second, third

    first, second, third = asyncio.run(_run())
    assert first == 1
    assert second == 0
    assert third == 1


def test_cron_delivery_retries_and_recovers_from_transient_failure(tmp_path: Path):
    from claudebot_gateway.cron_service import CronService

    async def _run() -> tuple[dict[str, str], dict[str, str] | None, int]:
        service = CronService(db_path=tmp_path / "gateway.db", workspace_root=tmp_path / "workspaces")
        attempts = 0

        async def send(_: dict[str, str]) -> None:
            nonlocal attempts
            attempts += 1
            if attempts < 3:
                raise RuntimeError("temporary channel outage")

        async def agent(_: str, __: Path) -> str:
            return "report"

        result = await service.run_job_once(
            job_id="job-retry-01",
            prompt="retry me",
            target={"channel": "telegram", "destination": "chat:retry"},
            send_func=send,
            agent_func=agent,
        )
        delivery = service.get_last_delivery("job-retry-01")
        return result, delivery, attempts

    result, delivery, attempts = asyncio.run(_run())
    assert attempts == 3
    assert result["delivery_status"] == "ok"
    assert result["run_status"] == "ok"
    assert delivery is not None
    assert delivery["status"] == "ok"


def test_cron_service_init_docstring_documents_store_dependency_injection():
    from claudebot_gateway.cron_service import CronService

    doc = CronService.__init__.__doc__ or ""
    assert "store (SqliteStore | None)" in doc
