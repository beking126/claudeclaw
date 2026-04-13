from datetime import datetime, timedelta, timezone
from pathlib import Path

import sqlite3

from claudebot_gateway.persistence.migrations import ensure_schema


def test_migrations_run_idempotently(tmp_path: Path):
    """Running ensure_schema twice applies each migration only once."""
    db_path = tmp_path / "state" / "gateway.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    ensure_schema(conn)
    applied_first = {
        row[0] for row in conn.execute("SELECT version FROM schema_migrations").fetchall()
    }
    assert len(applied_first) >= 2  # at least initial + cron columns

    ensure_schema(conn)
    applied_second = {
        row[0] for row in conn.execute("SELECT version FROM schema_migrations").fetchall()
    }
    assert applied_first == applied_second

    conn.close()


def test_schema_migrations_table_tracks_descriptions(tmp_path: Path):
    db_path = tmp_path / "state" / "gateway.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    ensure_schema(conn)

    rows = conn.execute("SELECT version, description FROM schema_migrations ORDER BY version").fetchall()
    assert len(rows) >= 2
    descriptions = {row["version"]: row["description"] for row in rows}
    assert descriptions[1] == "initial schema"
    assert descriptions[2] == "ensure cron_jobs has schedule columns"

    conn.close()


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
