import re
from pathlib import Path


_INVALID_CHAR_PATTERN = re.compile(r"[^a-z0-9_-]+")
_UNDERSCORE_PATTERN = re.compile(r"_+")
_PROMPT_FILES = ("SOUL.md", "USER.md", "TOOLS.md")


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


def load_workspace_prompt_files(workspace: Path) -> dict[str, str]:
    workspace_path = Path(workspace)
    loaded: dict[str, str] = {}
    for filename in _PROMPT_FILES:
        file_path = workspace_path / filename
        try:
            loaded[filename] = file_path.read_text(encoding="utf-8")
        except (FileNotFoundError, OSError):
            loaded[filename] = ""
    return loaded


def compose_workspace_prompt(prompt: str, prompt_files: dict[str, str]) -> str:
    blocks: list[str] = []
    for filename in _PROMPT_FILES:
        content = prompt_files.get(filename, "").strip()
        if not content:
            continue
        title = filename.removesuffix(".md")
        blocks.append(f"[{title}]\n{content}")
    blocks.append(prompt)
    return "\n\n".join(blocks)


def validate_workspace_path(path: Path, root: Path) -> Path:
    resolved = path.resolve()
    if not resolved.is_relative_to(root.resolve()):
        raise ValueError(f"workspace path escapes root: {resolved}")
    return resolved


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
