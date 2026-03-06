from pathlib import Path
from typing import Awaitable, Callable

from claudebot_gateway.persistence.sqlite_store import SqliteStore
from claudebot_gateway.workspaces import WorkspaceResolver


HeartbeatAgentFunc = Callable[[str, Path], Awaitable[str]]


class HeartbeatService:
    def __init__(self, db_path: Path, workspace_root: Path):
        self._store = SqliteStore(db_path=db_path)
        self._resolver = WorkspaceResolver(workspace_root)

    async def run_once(self, *, source_text: str, agent_func: HeartbeatAgentFunc) -> bool:
        actionable = bool(source_text.strip())
        workspace = self._resolver.heartbeat()
        workspace.mkdir(parents=True, exist_ok=True)
        status = "skipped"
        error: str | None = None
        if actionable:
            try:
                await agent_func(source_text, workspace)
                status = "ok"
            except Exception as exc:
                status = "error"
                error = str(exc)
        self._store.record_heartbeat_run(
            actionable=actionable,
            status=status,
            error=error,
            workspace_key=workspace.name,
        )
        return actionable

    def load_source_text(self) -> str:
        workspace = self._resolver.heartbeat()
        file_path = workspace / "HEARTBEAT.md"
        if not file_path.exists():
            return ""
        return file_path.read_text(encoding="utf-8")

    def get_last_run(self) -> dict[str, str] | None:
        run = self._store.get_last_heartbeat_run()
        if run is None:
            return None
        return {k: "" if v is None else str(v) for k, v in run.items()}
