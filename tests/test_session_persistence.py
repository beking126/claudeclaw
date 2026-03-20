from pathlib import Path


def test_sqlite_store_persists_agent_turn_and_latest_session(tmp_path: Path):
    from claudebot_gateway.persistence.sqlite_store import SqliteStore

    store = SqliteStore(db_path=tmp_path / "state" / "gateway.db")
    store.record_agent_turn(
        provider="claude",
        session_id="session-a",
        workspace_path=str(tmp_path / "workspaces" / "main"),
        channel="telegram",
        destination="chat:1",
        prompt_text="hello",
        response_text="world",
        metadata={"usage": {"input_tokens": 1}},
    )
    store.upsert_latest_agent_session(
        provider="claude",
        workspace_path=str(tmp_path / "workspaces" / "main"),
        channel="telegram",
        destination="chat:1",
        session_id="session-a",
    )

    latest = store.get_latest_agent_session(
        provider="claude",
        workspace_path=str(tmp_path / "workspaces" / "main"),
        channel="telegram",
        destination="chat:1",
    )
    turns = store.list_agent_turns(session_id="session-a")

    assert latest is not None
    assert latest["session_id"] == "session-a"
    assert len(turns) == 1
    assert turns[0]["prompt_text"] == "hello"
    assert turns[0]["response_text"] == "world"


def test_sqlite_store_latest_session_scope_is_isolated(tmp_path: Path):
    from claudebot_gateway.persistence.sqlite_store import SqliteStore

    workspace = str(tmp_path / "workspaces" / "main")
    store = SqliteStore(db_path=tmp_path / "state" / "gateway.db")
    store.upsert_latest_agent_session(
        provider="claude",
        workspace_path=workspace,
        channel="telegram",
        destination="chat:1",
        session_id="s-1",
    )
    store.upsert_latest_agent_session(
        provider="claude",
        workspace_path=workspace,
        channel="telegram",
        destination="chat:2",
        session_id="s-2",
    )

    s1 = store.get_latest_agent_session(
        provider="claude",
        workspace_path=workspace,
        channel="telegram",
        destination="chat:1",
    )
    s2 = store.get_latest_agent_session(
        provider="claude",
        workspace_path=workspace,
        channel="telegram",
        destination="chat:2",
    )
    assert s1 is not None and s1["session_id"] == "s-1"
    assert s2 is not None and s2["session_id"] == "s-2"
