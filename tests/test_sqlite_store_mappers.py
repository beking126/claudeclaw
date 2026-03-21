from pathlib import Path


def test_sqlite_store_exposes_row_mapping_helpers(tmp_path: Path):
    from claudebot_gateway.persistence.sqlite_store import SqliteStore

    store = SqliteStore(db_path=tmp_path / "state" / "gateway.db")
    assert callable(getattr(store, "_row_to_delivery"))
    assert callable(getattr(store, "_row_to_cron_job"))
    assert callable(getattr(store, "_row_to_heartbeat_run"))
    assert callable(getattr(store, "_row_to_agent_session"))
    assert callable(getattr(store, "_row_to_agent_turn"))
