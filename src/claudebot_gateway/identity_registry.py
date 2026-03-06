from pathlib import Path

from claudebot_gateway.persistence.sqlite_store import SqliteStore
from claudebot_gateway.workspaces import make_channel_workspace_key, sanitize_workspace_token


class IdentityRegistry:
    def __init__(self, db_path: Path):
        self._store = SqliteStore(db_path=db_path)

    def register(self, channel_type: str, raw_ids: dict[str, str]) -> str:
        if not raw_ids:
            raise ValueError("raw_ids cannot be empty")
        normalized_channel_type = sanitize_workspace_token(channel_type)
        normalized_raw_ids = {k: str(v) for k, v in raw_ids.items()}
        primary_id = normalized_raw_ids[sorted(normalized_raw_ids.keys())[0]]
        sanitized_primary_id = sanitize_workspace_token(primary_id)
        source_key = f"{normalized_channel_type}:{sanitized_primary_id}"
        workspace_key = make_channel_workspace_key(normalized_channel_type, primary_id)
        sanitized_ids = {k: sanitize_workspace_token(str(v)) for k, v in normalized_raw_ids.items()}
        self._store.upsert_channel_identity(
            source_key=source_key,
            channel_type=normalized_channel_type,
            raw_ids=normalized_raw_ids,
            sanitized_ids=sanitized_ids,
            workspace_key=workspace_key,
        )
        return source_key

    def resolve(self, source_key: str) -> dict[str, object]:
        record = self._store.get_channel_identity(source_key)
        if record is None:
            raise KeyError(f"Unknown source key: {source_key}")
        return record
