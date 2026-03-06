from pathlib import Path


def test_round_trip_identity_mapping(tmp_path: Path):
    from claudebot_gateway.identity_registry import IdentityRegistry

    reg = IdentityRegistry(db_path=tmp_path / "gateway.db")
    key = reg.register("telegram", {"chat_id": "12345"})
    loaded = reg.resolve(key)

    assert loaded["channel_type"] == "telegram"
    assert loaded["workspace_key"] == "telegram_12345"
    assert loaded["raw_ids"]["chat_id"] == "12345"
