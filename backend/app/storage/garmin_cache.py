"""Persistent SQLite cache for Garmin Connect API responses.

Stores weigh-in and body-composition data per date in SQLite with a 1-hour TTL.
Each row stores the parsed model dicts as JSON, keyed by ``(date, source_type)``
with a ``UNIQUE`` constraint so re-fetching the same date overwrites cleanly.

Entry invalidation
------------------
- **TTL** (1 h) — stale entries are skipped and the API is called again.
- **Write‑triggered** — after a successful ``add_body_composition`` the
  corresponding date is evicted immediately so the next read pulls fresh data.
- **Explicit** — ``invalidate_date`` / ``invalidate_range`` / ``clear`` are
  available for manual or background invalidation.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from app.storage.db import init_db

GARMIN_CACHE_TTL_SECONDS = 3600  # 1 hour


class GarminCacheStore:
    """Persistent read‑through cache for Garmin API responses.

    Each row holds a JSON array of model dicts (the list returned by the
    underlying endpoint).  ``get()`` returns ``None`` when the entry is
    missing **or** expired — callers treat both identically.
    """

    def __init__(self, data_dir: Path) -> None:
        self._db_path = data_dir / "withings_tokens.db"
        self._conn: sqlite3.Connection | None = None

    # ── connection management ──────────────────────────────────

    @property
    def conn(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = init_db(self._db_path)
        return self._conn

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    # ── helpers ────────────────────────────────────────────────

    @staticmethod
    def _now() -> datetime:
        return datetime.now(UTC)

    @staticmethod
    def _is_fresh(cache_expires_at: str) -> bool:
        try:
            return datetime.fromisoformat(cache_expires_at) > datetime.now(UTC)
        except (ValueError, TypeError):
            return False

    # ── public API ─────────────────────────────────────────────

    def get(self, source_type: str, date_str: str) -> list[dict[str, Any]] | None:
        """Return cached data *list* if present and fresh, otherwise ``None``."""
        row = self.conn.execute(
            """SELECT data_json, cache_expires_at
               FROM garmin_measurements_cache
               WHERE source_type = ? AND date = ?""",
            (source_type, date_str),
        ).fetchone()
        if row is None or not self._is_fresh(row["cache_expires_at"]):
            return None
        try:
            return json.loads(row["data_json"])
        except (json.JSONDecodeError, TypeError):
            return None

    def set(
        self,
        source_type: str,
        date_str: str,
        data: list[dict[str, Any]],
    ) -> None:
        """Cache *data* for a date.  Overwrites any existing entry."""
        now = self._now()
        expires_at = now + timedelta(seconds=GARMIN_CACHE_TTL_SECONDS)
        self.conn.execute(
            """INSERT OR REPLACE INTO garmin_measurements_cache
               (date, source_type, data_json,
                fetched_at, cache_expires_at,
                created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                date_str,
                source_type,
                json.dumps(data, ensure_ascii=False),
                now.isoformat(),
                expires_at.isoformat(),
                now.isoformat(),
                now.isoformat(),
            ),
        )
        self.conn.commit()

    def invalidate_date(self, date_str: str) -> None:
        """Remove **all** cached entries (both weigh_in and body_composition) for a date."""
        self.conn.execute(
            "DELETE FROM garmin_measurements_cache WHERE date = ?",
            (date_str,),
        )
        self.conn.commit()

    def invalidate_range(self, start_date: str, end_date: str) -> None:
        """Remove all cached entries in a date range (inclusive)."""
        self.conn.execute(
            "DELETE FROM garmin_measurements_cache WHERE date BETWEEN ? AND ?",
            (start_date, end_date),
        )
        self.conn.commit()

    def clear(self) -> None:
        """Remove **all** cached entries — emergency flush."""
        self.conn.execute("DELETE FROM garmin_measurements_cache")
        self.conn.commit()
