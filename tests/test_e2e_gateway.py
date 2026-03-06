import asyncio
from pathlib import Path


class _CollectingAdapter:
    def __init__(self):
        self.sent: list[dict[str, str]] = []

    async def send(self, message: dict[str, str]) -> None:
        self.sent.append(message)


def test_gateway_e2e_cli_message_cron_heartbeat_flow(tmp_path: Path):
    from claudebot_gateway.agent_runner import AgentRunner
    from claudebot_gateway.cron_service import CronService
    from claudebot_gateway.heartbeat_service import HeartbeatService
    from claudebot_gateway.message_bus import MessageBus
    from claudebot_gateway.outbound_dispatcher import OutboundDispatcher

    async def _run() -> dict[str, object]:
        adapter = _CollectingAdapter()
        bus = MessageBus(inbound_maxsize=1)
        runner = AgentRunner(
            turn_handler=lambda inbound: {
                "channel": "telegram",
                "destination": inbound["destination"],
                "text": f"reply:{inbound['text']}",
            }
        )
        dispatcher = OutboundDispatcher(adapters={"telegram": adapter})
        await bus.publish_inbound({"channel": "cli", "destination": "chat:1", "text": "hello"})
        accepted = await bus.try_publish_inbound({"channel": "cli", "destination": "chat:1", "text": "overflow"})
        rejection = bus.make_busy_rejection("cli", "chat:1")
        await runner.process_once(bus)
        await dispatcher.dispatch_once(bus)

        cron = CronService(db_path=tmp_path / "gateway.db", workspace_root=tmp_path / "workspaces")
        await cron.run_job_once(
            job_id="job-01",
            prompt="daily",
            target={"channel": "telegram", "destination": "chat:1"},
            send_func=adapter.send,
            agent_func=lambda _prompt, _ws: asyncio.sleep(0, result="cron-report"),
        )

        heartbeat = HeartbeatService(db_path=tmp_path / "gateway.db", workspace_root=tmp_path / "workspaces")
        await heartbeat.run_once(
            source_text="ping",
            agent_func=lambda _text, _ws: asyncio.sleep(0, result="ok"),
        )
        return {
            "accepted": accepted,
            "rejection": rejection,
            "delivered": adapter.sent,
            "heartbeat_last": heartbeat.get_last_run(),
            "cron_last": cron.get_last_delivery("job-01"),
        }

    result = asyncio.run(_run())
    assert result["accepted"] is False
    assert result["rejection"]["text"] == "System busy. Try again shortly."
    assert len(result["delivered"]) >= 2
    assert result["heartbeat_last"]["status"] == "ok"
    assert result["cron_last"]["status"] == "ok"
