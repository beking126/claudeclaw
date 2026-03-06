import asyncio
from pathlib import Path


def test_heartbeat_triggers_only_when_actionable(tmp_path: Path):
    from claudebot_gateway.heartbeat_service import HeartbeatService

    async def _run() -> tuple[bool, bool, dict[str, str] | None]:
        service = HeartbeatService(db_path=tmp_path / "gateway.db", workspace_root=tmp_path / "workspaces")
        calls: list[str] = []

        async def agent(prompt: str, workspace: Path) -> str:
            calls.append(f"{prompt}|{workspace.name}")
            return "ok"

        first = await service.run_once(source_text="   ", agent_func=agent)
        second = await service.run_once(source_text="ping me", agent_func=agent)
        last = service.get_last_run()
        return first, second, last

    first, second, last = asyncio.run(_run())
    assert first is False
    assert second is True
    assert last is not None
    assert last["actionable"] == "1"
    assert last["workspace_key"] == "heartbeat"


def test_heartbeat_loads_source_text_from_heartbeat_file(tmp_path: Path):
    from claudebot_gateway.heartbeat_service import HeartbeatService

    service = HeartbeatService(db_path=tmp_path / "gateway.db", workspace_root=tmp_path / "workspaces")
    heartbeat_file = tmp_path / "workspaces" / "heartbeat" / "HEARTBEAT.md"
    heartbeat_file.parent.mkdir(parents=True, exist_ok=True)
    heartbeat_file.write_text("ship release\n", encoding="utf-8")

    text = service.load_source_text()
    assert text == "ship release\n"
