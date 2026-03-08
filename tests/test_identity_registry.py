from pathlib import Path
from typing import cast


def test_round_trip_identity_mapping(tmp_path: Path):
    from claudebot_gateway.identity_registry import IdentityRegistry

    reg = IdentityRegistry(db_path=tmp_path / "gateway.db")
    key = reg.register("telegram", {"chat_id": "12345"})
    loaded = reg.resolve(key)
    raw_ids = cast(dict[str, str], loaded["raw_ids"])

    assert loaded["channel_type"] == "telegram"
    assert loaded["workspace_key"] == "telegram_12345"
    assert raw_ids["chat_id"] == "12345"
