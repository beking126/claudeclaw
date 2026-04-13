import json
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from claudebot_gateway.persistence.migrations import ensure_schema


class SqliteStore:
    _CRON_JOB_COLUMNS = "job_id, prompt, channel, destination, interval_seconds, schedule_kind, schedule_value, next_run_epoch_seconds"

    def __init__(self, db_path: Path):
        self._db_path = Path(db_path)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self._db_path)
        self._conn.row_factory = sqlite3.Row
        ensure_schema(self._conn)

    def _row_to_delivery(self, row: sqlite3.Row) -> dict[str, Any]:
        return {
            "job_id": row["job_id"],
            "channel": row["channel"],
            "destination": row["destination"],
            "status": row["status"],
            "failure_reason": row["failure_reason"],
        }

    def _row_to_cron_job(self, row: sqlite3.Row) -> dict[str, Any]:
        return {
            "job_id": row["job_id"],
            "prompt": row["prompt"],
            "channel": row["channel"],
            "destination": row["destination"],
            "interval_seconds": row["interval_seconds"],
            "schedule_kind": row["schedule_kind"],
            "schedule_value": row["schedule_value"],
            "next_run_epoch_seconds": row["next_run_epoch_seconds"],
        }

    def _row_to_heartbeat_run(self, row: sqlite3.Row) -> dict[str, Any]:
        return {
            "actionable": row["actionable"],
            "status": row["status"],
            "error": row["error"],
            "workspace_key": row["workspace_key"],
        }

    def _row_to_agent_session(self, row: sqlite3.Row) -> dict[str, Any]:
        return {
            "provider": row["provider"],
            "workspace_path": row["workspace_path"],
            "channel": row["channel"],
            "destination": row["destination"],
            "session_id": row["session_id"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }

    def _row_to_agent_turn(self, row: sqlite3.Row) -> dict[str, Any]:
        return {
            "provider": row["provider"],
            "session_id": row["session_id"],
            "workspace_path": row["workspace_path"],
            "channel": row["channel"],
            "destination": row["destination"],
            "prompt_text": row["prompt_text"],
            "response_text": row["response_text"],
            "metadata": json.loads(row["metadata_json"]),
            "created_at": row["created_at"],
        }

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
        return self._row_to_delivery(row)

    def upsert_cron_job(
        self,
        *,
        job_id: str,
        prompt: str,
        channel: str,
        destination: str,
        interval_seconds: int,
        schedule_kind: str,
        schedule_value: str,
        next_run_epoch_seconds: float,
    ) -> None:
        self._conn.execute(
            """
            INSERT INTO cron_jobs (
                job_id, prompt, channel, destination, interval_seconds, schedule_kind, schedule_value, next_run_epoch_seconds
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(job_id) DO UPDATE SET
                prompt = excluded.prompt,
                channel = excluded.channel,
                destination = excluded.destination,
                interval_seconds = excluded.interval_seconds,
                schedule_kind = excluded.schedule_kind,
                schedule_value = excluded.schedule_value,
                next_run_epoch_seconds = excluded.next_run_epoch_seconds,
                updated_at = CURRENT_TIMESTAMP
            """,
            (job_id, prompt, channel, destination, interval_seconds, schedule_kind, schedule_value, next_run_epoch_seconds),
        )
        self._conn.commit()

    def list_due_cron_jobs(self, *, now_epoch_seconds: float) -> list[dict[str, Any]]:
        rows = self._conn.execute(
            f"""
            SELECT {self._CRON_JOB_COLUMNS}
            FROM cron_jobs
            WHERE next_run_epoch_seconds <= ?
            ORDER BY next_run_epoch_seconds ASC
            """,
            (now_epoch_seconds,),
        ).fetchall()
        return [self._row_to_cron_job(row) for row in rows]

    def count_due_cron_jobs(self, *, now_epoch_seconds: float) -> int:
        row = self._conn.execute(
            "SELECT COUNT(*) FROM cron_jobs WHERE next_run_epoch_seconds <= ?",
            (now_epoch_seconds,),
        ).fetchone()
        return int(row[0]) if row else 0

    def list_all_cron_jobs(self) -> list[dict[str, Any]]:
        rows = self._conn.execute(
            f"""
            SELECT {self._CRON_JOB_COLUMNS}
            FROM cron_jobs
            ORDER BY next_run_epoch_seconds ASC
            """
        ).fetchall()
        return [self._row_to_cron_job(row) for row in rows]

    def update_cron_job_next_run(self, *, job_id: str, next_run_epoch_seconds: float) -> None:
        self._conn.execute(
            """
            UPDATE cron_jobs
            SET next_run_epoch_seconds = ?, updated_at = CURRENT_TIMESTAMP
            WHERE job_id = ?
            """,
            (next_run_epoch_seconds, job_id),
        )
        self._conn.commit()

    def delete_cron_job(self, *, job_id: str) -> int:
        cursor = self._conn.execute("DELETE FROM cron_jobs WHERE job_id = ?", (job_id,))
        self._conn.commit()
        return cursor.rowcount

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
        return self._row_to_heartbeat_run(row)

    def upsert_latest_agent_session(
        self,
        *,
        provider: str,
        workspace_path: str,
        channel: str | None,
        destination: str | None,
        session_id: str,
    ) -> None:
        self._conn.execute(
            """
            INSERT INTO agent_sessions (provider, workspace_path, channel, destination, session_id)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(provider, workspace_path, channel, destination) DO UPDATE SET
                session_id = excluded.session_id
            """,
            (provider, workspace_path, channel, destination, session_id),
        )
        self._conn.commit()

    def get_latest_agent_session(
        self,
        *,
        provider: str,
        workspace_path: str,
        channel: str | None,
        destination: str | None,
    ) -> dict[str, Any] | None:
        row = self._conn.execute(
            """
            SELECT provider, workspace_path, channel, destination, session_id, created_at, updated_at
            FROM agent_sessions
            WHERE provider = ? AND workspace_path = ? AND channel IS ? AND destination IS ?
            """,
            (provider, workspace_path, channel, destination),
        ).fetchone()
        if row is None:
            return None
        return self._row_to_agent_session(row)

    def record_agent_turn(
        self,
        *,
        provider: str,
        session_id: str | None,
        workspace_path: str,
        channel: str | None,
        destination: str | None,
        prompt_text: str,
        response_text: str,
        metadata: dict[str, Any] | None,
    ) -> None:
        self._conn.execute(
            """
            INSERT INTO agent_turns (
                provider, session_id, workspace_path, channel, destination, prompt_text, response_text, metadata_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                provider,
                session_id,
                workspace_path,
                channel,
                destination,
                prompt_text,
                response_text,
                json.dumps(metadata or {}, sort_keys=True),
            ),
        )
        self._conn.commit()

    def list_agent_turns(self, *, session_id: str) -> list[dict[str, Any]]:
        rows = self._conn.execute(
            """
            SELECT provider, session_id, workspace_path, channel, destination, prompt_text, response_text, metadata_json, created_at
            FROM agent_turns
            WHERE session_id = ?
            ORDER BY turn_id ASC
            """,
            (session_id,),
        ).fetchall()
        return [self._row_to_agent_turn(row) for row in rows]

    def purge_old_turns(self, *, max_age_days: int) -> int:
        cutoff = (datetime.now(timezone.utc) - timedelta(days=max_age_days)).isoformat()
        cursor = self._conn.execute(
            "DELETE FROM agent_turns WHERE created_at < ?",
            (cutoff,),
        )
        self._conn.commit()
        return cursor.rowcount
