"""Persistence layer for sync attempts and results."""

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from sqlite3 import Connection
from typing import Any

from app.storage.db import init_db


class SyncStore:
    """Sync event persistence for idempotency and audit trail."""

    def __init__(self, data_dir: Path) -> None:
        self._db_path = data_dir / "withings_tokens.db"
        self._conn: Connection | None = None

    @property
    def conn(self) -> Connection:
        if self._conn is None:
            self._conn = init_db(self._db_path)
        return self._conn

    def event_exists(self, idempotency_key: str) -> bool:
        """Check whether this key was really handled by a prior sync."""
        row = self.conn.execute(
            """SELECT 1 FROM sync_events
               WHERE idempotency_key = ?
                 AND status IN ('synced', 'skipped_existing')
               LIMIT 1""",
            (idempotency_key,),
        ).fetchone()
        return row is not None

    def start_attempt(self, start_date: str, end_date: str) -> int:
        now = datetime.now(UTC).isoformat()
        cur = self.conn.execute(
            """INSERT INTO sync_attempts (started_at, start_date, end_date, status)
               VALUES (?, ?, ?, ?)""",
            (now, start_date, end_date, "running"),
        )
        self.conn.commit()
        return int(cur.lastrowid)

    def finish_attempt(
        self,
        attempt_id: int,
        status: str,
        summary: dict[str, Any] | None = None,
        error_message: str | None = None,
    ) -> None:
        self.conn.execute(
            """UPDATE sync_attempts
               SET completed_at = ?, status = ?, summary_json = ?, error_message = ?
               WHERE id = ?""",
            (
                datetime.now(UTC).isoformat(),
                status,
                json.dumps(summary, ensure_ascii=False) if summary else None,
                error_message,
                attempt_id,
            ),
        )
        self.conn.commit()

    def save_event(
        self,
        idempotency_key: str,
        source: str,
        source_measure_group_id: str | None,
        source_measured_at_utc: str | None,
        garmin_date: str,
        weight_kg: str | None,
        status: str,
        garmin_write_method: str | None = None,
        garmin_measure_id: str | None = None,
        garmin_response: dict[str, Any] | None = None,
        error_message: str | None = None,
        report: dict[str, Any] | None = None,
    ) -> None:
        """Insert or update a sync event by idempotency key."""
        now = datetime.now(UTC).isoformat()
        payload_hash = self.payload_hash(report or garmin_response or {})
        self.conn.execute(
            """INSERT INTO sync_events
               (idempotency_key, source, withings_measure_id,
                source_measured_at_utc, local_date, weight_kg, payload_hash,
                status, garmin_write_method, garmin_measure_id,
                garmin_response_json, error_message, report_json, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(idempotency_key) DO UPDATE SET
                status = excluded.status,
                garmin_write_method = excluded.garmin_write_method,
                garmin_measure_id = excluded.garmin_measure_id,
                garmin_response_json = excluded.garmin_response_json,
                error_message = excluded.error_message,
                report_json = excluded.report_json,
                updated_at = excluded.updated_at""",
            (
                idempotency_key,
                source,
                source_measure_group_id,
                source_measured_at_utc,
                garmin_date,
                weight_kg,
                payload_hash,
                status,
                garmin_write_method,
                garmin_measure_id,
                json.dumps(garmin_response) if garmin_response else None,
                error_message,
                json.dumps(report) if report else None,
                now,
                now,
            ),
        )
        self.conn.commit()

    def get_event_by_key(self, idempotency_key: str) -> dict[str, Any] | None:
        """Return a sync event by its idempotency key."""
        row = self.conn.execute(
            "SELECT * FROM sync_events WHERE idempotency_key = ?",
            (idempotency_key,),
        ).fetchone()
        if row is None:
            return None
        return dict(row)

    def last_sync_time(self) -> str | None:
        """Return the ISO timestamp of the most recent sync event."""
        row = self.conn.execute(
            """SELECT created_at FROM sync_events
               WHERE status = 'synced'
               ORDER BY created_at DESC LIMIT 1"""
        ).fetchone()
        return row["created_at"] if row else None

    @staticmethod
    def payload_hash(payload: dict[str, Any]) -> str:
        encoded = json.dumps(
            payload,
            sort_keys=True,
            ensure_ascii=False,
            default=str,
        ).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None
