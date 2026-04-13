"""Database migration system for SqliteStore.

Each migration is a numbered function that runs once and is tracked in
a ``schema_migrations`` table.  Adding a new table or column means
appending a new migration entry — the runner picks it up automatically
on the next startup.
"""

import sqlite3


# ---------------------------------------------------------------------------
# Migration registry
# ---------------------------------------------------------------------------

_MIGRATIONS: list[tuple[int, str]] = []
"""(version, description) pairs registered by ``@migration``."""


def _register(version: int, description: str, fn) -> None:
    if any(v == version for v, _ in _MIGRATIONS):
        raise ValueError(f"Duplicate migration version {version}")
    _MIGRATIONS.append((version, description))
    _MIGRATIONS.sort()
    fn._migration_version = version  # type: ignore[attr-defined]
    _MIGRATION_FUNCS[version] = fn


_MIGRATION_FUNCS: dict[int, object] = {}


def migration(version: int, description: str):
    """Decorator that registers a function as a schema migration."""

    def decorator(fn):
        _register(version, description, fn)
        return fn

    return decorator


# ---------------------------------------------------------------------------
# Migrations
# ---------------------------------------------------------------------------

@migration(1, "initial schema")
def _m001_initial(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS channel_identity (
            source_key TEXT PRIMARY KEY,
            channel_type TEXT NOT NULL,
            raw_ids_json TEXT NOT NULL,
            sanitized_ids_json TEXT NOT NULL,
            workspace_key TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    conn.execute(
        """
        CREATE TRIGGER IF NOT EXISTS channel_identity_updated_at
        AFTER UPDATE ON channel_identity
        BEGIN
            UPDATE channel_identity
            SET updated_at = CURRENT_TIMESTAMP
            WHERE source_key = NEW.source_key;
        END
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS cron_runs (
            run_id INTEGER PRIMARY KEY AUTOINCREMENT,
            job_id TEXT NOT NULL,
            prompt TEXT NOT NULL,
            workspace_key TEXT NOT NULL,
            status TEXT NOT NULL,
            error TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS deliveries (
            delivery_id INTEGER PRIMARY KEY AUTOINCREMENT,
            job_id TEXT NOT NULL,
            channel TEXT NOT NULL,
            destination TEXT NOT NULL,
            status TEXT NOT NULL,
            failure_reason TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS cron_jobs (
            job_id TEXT PRIMARY KEY,
            prompt TEXT NOT NULL,
            channel TEXT NOT NULL,
            destination TEXT NOT NULL,
            interval_seconds INTEGER NOT NULL,
            schedule_kind TEXT NOT NULL DEFAULT 'every',
            schedule_value TEXT NOT NULL DEFAULT '',
            next_run_epoch_seconds REAL NOT NULL,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS heartbeat_runs (
            run_id INTEGER PRIMARY KEY AUTOINCREMENT,
            actionable INTEGER NOT NULL,
            status TEXT NOT NULL,
            error TEXT,
            workspace_key TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS agent_sessions (
            session_row_id INTEGER PRIMARY KEY AUTOINCREMENT,
            provider TEXT NOT NULL,
            workspace_path TEXT NOT NULL,
            channel TEXT,
            destination TEXT,
            session_id TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(provider, workspace_path, channel, destination)
        )
        """
    )
    conn.execute(
        """
        CREATE TRIGGER IF NOT EXISTS agent_sessions_updated_at
        AFTER UPDATE ON agent_sessions
        BEGIN
            UPDATE agent_sessions
            SET updated_at = CURRENT_TIMESTAMP
            WHERE session_row_id = NEW.session_row_id;
        END
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS agent_turns (
            turn_id INTEGER PRIMARY KEY AUTOINCREMENT,
            provider TEXT NOT NULL,
            session_id TEXT,
            workspace_path TEXT NOT NULL,
            channel TEXT,
            destination TEXT,
            prompt_text TEXT NOT NULL,
            response_text TEXT NOT NULL,
            metadata_json TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_agent_turns_session_id
        ON agent_turns(session_id)
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_agent_turns_created_at
        ON agent_turns(created_at)
        """
    )


@migration(2, "ensure cron_jobs has schedule columns")
def _m002_cron_schedule_columns(conn: sqlite3.Connection) -> None:
    """Back-fill schedule_kind and schedule_value for databases created before
    these columns existed."""
    rows = conn.execute("PRAGMA table_info(cron_jobs)").fetchall()
    existing = {str(row[1]) for row in rows}  # row[1] is column name
    if "schedule_kind" not in existing:
        conn.execute("ALTER TABLE cron_jobs ADD COLUMN schedule_kind TEXT NOT NULL DEFAULT 'every'")
    if "schedule_value" not in existing:
        conn.execute("ALTER TABLE cron_jobs ADD COLUMN schedule_value TEXT NOT NULL DEFAULT ''")


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

def ensure_schema(conn: sqlite3.Connection) -> None:
    """Run all pending migrations against *conn*.

    Safe to call on every startup.  Each migration runs at most once,
    tracked by the ``schema_migrations`` table.
    """
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version INTEGER PRIMARY KEY,
            description TEXT NOT NULL,
            applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )

    applied = {
        row[0]
        for row in conn.execute("SELECT version FROM schema_migrations").fetchall()
    }

    for version, description in _MIGRATIONS:
        if version in applied:
            continue
        fn = _MIGRATION_FUNCS[version]
        fn(conn)  # type: ignore[operator]
        conn.execute(
            "INSERT INTO schema_migrations (version, description) VALUES (?, ?)",
            (version, description),
        )
        conn.commit()
