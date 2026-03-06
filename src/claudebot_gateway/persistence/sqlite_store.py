import json
import sqlite3
from pathlib import Path
from typing import Any


class SqliteStore:
    def __init__(self, db_path: Path):
        self._db_path = Path(db_path)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self._db_path)
        self._conn.row_factory = sqlite3.Row
        self._ensure_schema()

    def _ensure_schema(self) -> None:
        self._conn.execute(
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
        self._conn.execute(
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
        self._conn.execute(
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
        self._conn.execute(
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
        self._conn.execute(
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
        self._conn.commit()

    def upsert_channel_identity(
        self,
        *,
        source_key: str,
        channel_type: str,
        raw_ids: dict[str, str],
        sanitized_ids: dict[str, str],
        workspace_key: str,
    ) -> None:
        self._conn.execute(
            """
            INSERT INTO channel_identity (
                source_key, channel_type, raw_ids_json, sanitized_ids_json, workspace_key
            ) VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(source_key) DO UPDATE SET
                channel_type = excluded.channel_type,
                raw_ids_json = excluded.raw_ids_json,
                sanitized_ids_json = excluded.sanitized_ids_json,
                workspace_key = excluded.workspace_key
            """,
            (
                source_key,
                channel_type,
                json.dumps(raw_ids, sort_keys=True),
                json.dumps(sanitized_ids, sort_keys=True),
                workspace_key,
            ),
        )
        self._conn.commit()

    def get_channel_identity(self, source_key: str) -> dict[str, Any] | None:
        row = self._conn.execute(
            """
            SELECT source_key, channel_type, raw_ids_json, sanitized_ids_json, workspace_key
            FROM channel_identity
            WHERE source_key = ?
            """,
            (source_key,),
        ).fetchone()
        if row is None:
            return None
        return {
            "source_key": row["source_key"],
            "channel_type": row["channel_type"],
            "raw_ids": json.loads(row["raw_ids_json"]),
            "sanitized_ids": json.loads(row["sanitized_ids_json"]),
            "workspace_key": row["workspace_key"],
        }

    def record_cron_run(
        self,
        *,
        job_id: str,
        prompt: str,
        workspace_key: str,
        status: str,
        error: str | None,
    ) -> None:
        self._conn.execute(
            """
            INSERT INTO cron_runs (job_id, prompt, workspace_key, status, error)
            VALUES (?, ?, ?, ?, ?)
            """,
            (job_id, prompt, workspace_key, status, error),
        )
        self._conn.commit()

    def record_delivery(
        self,
        *,
        job_id: str,
        channel: str,
        destination: str,
        status: str,
        failure_reason: str | None,
    ) -> None:
        self._conn.execute(
            """
            INSERT INTO deliveries (job_id, channel, destination, status, failure_reason)
            VALUES (?, ?, ?, ?, ?)
            """,
            (job_id, channel, destination, status, failure_reason),
        )
        self._conn.commit()

    def get_last_delivery_by_job(self, job_id: str) -> dict[str, Any] | None:
        row = self._conn.execute(
            """
            SELECT job_id, channel, destination, status, failure_reason
            FROM deliveries
            WHERE job_id = ?
            ORDER BY delivery_id DESC
            LIMIT 1
            """,
            (job_id,),
        ).fetchone()
        if row is None:
            return None
        return {
            "job_id": row["job_id"],
            "channel": row["channel"],
            "destination": row["destination"],
            "status": row["status"],
            "failure_reason": row["failure_reason"],
        }

    def record_heartbeat_run(
        self,
        *,
        actionable: bool,
        status: str,
        error: str | None,
        workspace_key: str,
    ) -> None:
        self._conn.execute(
            """
            INSERT INTO heartbeat_runs (actionable, status, error, workspace_key)
            VALUES (?, ?, ?, ?)
            """,
            (1 if actionable else 0, status, error, workspace_key),
        )
        self._conn.commit()

    def get_last_heartbeat_run(self) -> dict[str, Any] | None:
        row = self._conn.execute(
            """
            SELECT actionable, status, error, workspace_key
            FROM heartbeat_runs
            ORDER BY run_id DESC
            LIMIT 1
            """
        ).fetchone()
        if row is None:
            return None
        return {
            "actionable": row["actionable"],
            "status": row["status"],
            "error": row["error"],
            "workspace_key": row["workspace_key"],
        }
