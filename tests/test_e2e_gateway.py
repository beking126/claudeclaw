import asyncio
from pathlib import Path
from typing import cast

def test_gateway_e2e_cli_message_cron_heartbeat_flow(tmp_path: Path, collecting_adapter, echo_runtime):
    from claudebot_gateway.agent_runner import AgentRunner
    from claudebot_gateway.cron_service import CronService
    from claudebot_gateway.heartbeat_service import HeartbeatService
    from claudebot_gateway.message_bus import MessageBus
    from claudebot_gateway.outbound_dispatcher import OutboundDispatcher

    async def _run() -> dict[str, object]:
        bus = MessageBus(inbound_maxsize=1)
        runner = AgentRunner(runtime=echo_runtime, default_workspace=tmp_path / "workspaces" / "main")
        dispatcher = OutboundDispatcher(adapters={"telegram": collecting_adapter})
        await bus.publish_inbound({"channel": "telegram", "destination": "chat:1", "text": "hello"})
        accepted = await bus.try_publish_inbound({"channel": "telegram", "destination": "chat:1", "text": "overflow"})
        rejection = bus.make_busy_rejection("cli", "chat:1")
        await runner.process_once(bus)
        await dispatcher.dispatch_once(bus)

        cron = CronService(db_path=tmp_path / "gateway.db", workspace_root=tmp_path / "workspaces")
        await cron.run_job_once(
            job_id="job-01",
            prompt="daily",
            target={"channel": "telegram", "destination": "chat:1"},
            send_func=collecting_adapter.send,
            agent_func=lambda _prompt, _ws: asyncio.sleep(0, result="cron-report"),
        )
        await cron.schedule_job(
            job_id="job-02",
            prompt="hourly",
            target={"channel": "telegram", "destination": "chat:1"},
            interval_seconds=60,
            run_at_epoch_seconds=0.0,
        )
        due_count = await cron.run_due_jobs(
            now_epoch_seconds=1.0,
            send_func=collecting_adapter.send,
            agent_func=lambda _prompt, _ws: asyncio.sleep(0, result="cron-due-report"),
        )

        heartbeat = HeartbeatService(db_path=tmp_path / "gateway.db", workspace_root=tmp_path / "workspaces")
        await heartbeat.run_once(
            source_text="ping",
            agent_func=lambda _text, _ws: asyncio.sleep(0, result="ok"),
        )
        return {
            "accepted": accepted,
            "rejection": rejection,
            "delivered": collecting_adapter.sent,
            "heartbeat_last": heartbeat.get_last_run(),
            "cron_last": cron.get_last_delivery("job-01"),
            "cron_due_count": due_count,
        }

    result = asyncio.run(_run())
    assert result["accepted"] is False
    rejection = cast(dict[str, str], result["rejection"])
    delivered = cast(list[dict[str, str]], result["delivered"])
    heartbeat_last = cast(dict[str, object], result["heartbeat_last"])
    cron_last = cast(dict[str, object], result["cron_last"])
    assert rejection["text"] == "System busy. Try again shortly."
    assert len(delivered) >= 2
    assert heartbeat_last["status"] == "ok"
    assert cron_last["status"] == "ok"
    assert result["cron_due_count"] == 1
