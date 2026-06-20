"""Persistence layer for sync events and dry-run reports.

Stores every sync attempt (including dry-runs) in the SQLite
``sync_events`` table for idempotency and audit.
"""

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
        """Check whether an event with this key already exists."""
        row = self.conn.execute(
            "SELECT 1 FROM sync_events WHERE idempotency_key = ? LIMIT 1",
            (idempotency_key,),
        ).fetchone()
        return row is not None

    def save_event(
        self,
        idempotency_key: str,
        source: str,
        source_measure_group_id: str | None,
        source_measured_at_utc: str | None,
        garmin_date: str,
        weight_kg: str | None,
        status: str,
        dry_run: bool,
        garmin_write_method: str | None = None,
        garmin_response: dict[str, Any] | None = None,
        report: dict[str, Any] | None = None,
    ) -> None:
        """Insert or ignore a sync event (idempotency_key is UNIQUE)."""
        now = datetime.now(UTC).isoformat()
        self.conn.execute(
            """INSERT OR IGNORE INTO sync_events
               (idempotency_key, source, source_measure_group_id,
                source_measured_at_utc, garmin_date, weight_kg,
                status, dry_run, garmin_write_method,
                garmin_response_json, report_json, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                idempotency_key,
                source,
                source_measure_group_id,
                source_measured_at_utc,
                garmin_date,
                weight_kg,
                status,
                1 if dry_run else 0,
                garmin_write_method,
                json.dumps(garmin_response) if garmin_response else None,
                json.dumps(report) if report else None,
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
            "SELECT created_at FROM sync_events ORDER BY created_at DESC LIMIT 1"
        ).fetchone()
        return row["created_at"] if row else None

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None
