from datetime import datetime, timedelta, timezone
from pathlib import Path


def test_sqlite_store_exposes_row_mapping_helpers(tmp_path: Path):
    from claudebot_gateway.persistence.sqlite_store import SqliteStore

    store = SqliteStore(db_path=tmp_path / "state" / "gateway.db")
    assert callable(getattr(store, "_row_to_delivery"))
    assert callable(getattr(store, "_row_to_cron_job"))
    assert callable(getattr(store, "_row_to_heartbeat_run"))
    assert callable(getattr(store, "_row_to_agent_session"))
    assert callable(getattr(store, "_row_to_agent_turn"))


def test_purge_old_turns_deletes_expired_and_keeps_recent(tmp_path: Path):
    from claudebot_gateway.persistence.sqlite_store import SqliteStore

    store = SqliteStore(db_path=tmp_path / "state" / "gateway.db")
    old_ts = (datetime.now(timezone.utc) - timedelta(days=100)).strftime("%Y-%m-%d %H:%M:%S")
    recent_ts = (datetime.now(timezone.utc) - timedelta(hours=1)).strftime("%Y-%m-%d %H:%M:%S")

    store._conn.execute(
        "INSERT INTO agent_turns (provider, session_id, workspace_path, channel, destination, prompt_text, response_text, metadata_json, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        ("claude", "old-session", "/ws", "cli", "cli:stdout", "old prompt", "old response", "{}", old_ts),
    )
    store._conn.execute(
        "INSERT INTO agent_turns (provider, session_id, workspace_path, channel, destination, prompt_text, response_text, metadata_json, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        ("claude", "recent-session", "/ws", "cli", "cli:stdout", "recent prompt", "recent response", "{}", recent_ts),
    )
    store._conn.commit()

    deleted = store.purge_old_turns(max_age_days=30)
    assert deleted == 1

    remaining = store.list_agent_turns(session_id="recent-session")
    assert len(remaining) == 1
    assert remaining[0]["prompt_text"] == "recent prompt"

    old_remaining = store.list_agent_turns(session_id="old-session")
    assert len(old_remaining) == 0
