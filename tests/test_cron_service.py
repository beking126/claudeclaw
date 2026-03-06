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
