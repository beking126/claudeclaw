import re
from pathlib import Path


_INVALID_CHAR_PATTERN = re.compile(r"[^a-z0-9_-]+")
_UNDERSCORE_PATTERN = re.compile(r"_+")


def sanitize_workspace_token(value: str) -> str:
    normalized = value.lower().strip()
    normalized = _INVALID_CHAR_PATTERN.sub("_", normalized)
    normalized = _UNDERSCORE_PATTERN.sub("_", normalized).strip("_")
    if not normalized:
        raise ValueError("Workspace token is empty after sanitization")
    return normalized


def make_channel_workspace_key(channel_name: str, channel_id: str) -> str:
    return f"{sanitize_workspace_token(channel_name)}_{sanitize_workspace_token(channel_id)}"


def make_cron_workspace_key(job_id: str) -> str:
    return f"cron_{sanitize_workspace_token(job_id)}"


class WorkspaceResolver:
    def __init__(self, root: Path):
        self._root = Path(root)

    @property
    def root(self) -> Path:
        return self._root

    def main(self) -> Path:
        return self._root / "main"

    def heartbeat(self) -> Path:
        return self._root / "heartbeat"

    def channel(self, channel_name: str, channel_id: str) -> Path:
        return self._root / make_channel_workspace_key(channel_name, channel_id)

    def cron(self, job_id: str) -> Path:
        return self._root / make_cron_workspace_key(job_id)
