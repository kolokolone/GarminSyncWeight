"""Persistent store for parsed Withings measurements.

Stores ``BodyCompositionMeasurement`` records in SQLite so the Dashboard
endpoints can serve data without calling the Withings API on every request.

Write path
----------
The sync engine saves parsed measurements after each run
(``save_measurements``).  ``source_measure_group_id`` is ``UNIQUE`` so
re‑running the same range is idempotent.

Read path
---------
Routes use ``get_latest``, ``get_recent``, or ``get_measurements`` with a
store‑first / API‑fallback pattern.

Freshness
---------
There is no explicit TTL — data is refreshed on every sync.  ``fetched_at``
is stored so callers can evaluate staleness if needed.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

from app.models.withings import BodyCompositionMeasurement
from app.storage.db import init_db

_DECIMAL_FIELDS = (
    "weight_kg",
    "fat_percent",
    "fat_mass_kg",
    "fat_free_mass_kg",
    "muscle_mass_kg",
    "bone_mass_kg",
    "hydration_mass_kg",
    "hydration_percent",
    "bmi",
    "visceral_fat_mass",
    "basal_met",
    "active_met",
)


class WithingsMeasurementStore:
    """Persistent store for parsed Withings body‑composition measurements."""

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
    def _row_to_measurement(row: sqlite3.Row) -> BodyCompositionMeasurement:
        """Convert a DB row back to a ``BodyCompositionMeasurement``."""
        data: dict[str, Any] = {}
        for key in row.keys():
            value = row[key]
            if value is None:
                data[key] = None
            elif key in _DECIMAL_FIELDS:
                data[key] = Decimal(str(value))
            elif key in ("metabolic_age", "visceral_fat_rating", "physique_rating"):
                data[key] = int(value) if value is not None else None
            elif key in ("source",):
                data[key] = value
            elif key == "raw_json":
                data["raw"] = json.loads(value) if value else {}
            elif key in (
                "id", "fetched_at", "created_at", "updated_at",
            ):
                pass  # skip internal columns
            elif key in ("date",):
                pass  # mapped to garmin_date
            elif key in ("source_measure_group_id", "source_device_id"):
                data[key] = value
            elif key in ("measured_at_utc", "measured_at_local"):
                data[key] = datetime.fromisoformat(value) if value else None
            else:
                data[key] = value

        # Remap
        data["source"] = "withings"
        data["garmin_date"] = (
            datetime.fromisoformat(row["date"]).date() if row["date"] else None
        )
        # Ensure warnings list
        data.setdefault("warnings", [])
        return BodyCompositionMeasurement(**data)

    @staticmethod
    def _measurement_to_row(m: BodyCompositionMeasurement) -> dict[str, Any]:
        """Convert a measurement to a flat dict for INSERT."""
        row: dict[str, Any] = {
            "source_measure_group_id": m.source_measure_group_id,
            "source_device_id": m.source_device_id,
            "date": m.garmin_date.isoformat(),
            "measured_at_utc": m.measured_at_utc.isoformat(),
            "measured_at_local": m.measured_at_local.isoformat(),
            "raw_json": json.dumps(m.raw, ensure_ascii=False, default=str),
        }
        for field in _DECIMAL_FIELDS:
            val = getattr(m, field, None)
            row[field] = str(val) if val is not None else None
        row["metabolic_age"] = m.metabolic_age
        row["visceral_fat_rating"] = m.visceral_fat_rating
        row["physique_rating"] = m.physique_rating
        return row

    # ── public API ─────────────────────────────────────────────

    def save_measurements(
        self, measurements: list[BodyCompositionMeasurement],
    ) -> int:
        """Insert or ignore measurements.  Returns number of new rows."""
        now = datetime.now(UTC).isoformat()
        saved = 0
        for m in measurements:
            row = self._measurement_to_row(m)
            try:
                self.conn.execute(
                    """INSERT OR IGNORE INTO withings_measurements
                       (source_measure_group_id, source_device_id, date,
                        measured_at_utc, measured_at_local,
                        weight_kg, fat_percent, fat_mass_kg,
                        fat_free_mass_kg, muscle_mass_kg, bone_mass_kg,
                        hydration_mass_kg, hydration_percent, bmi,
                        visceral_fat_mass, basal_met, active_met,
                        metabolic_age, visceral_fat_rating, physique_rating,
                        raw_json, fetched_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                               ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        row["source_measure_group_id"],
                        row["source_device_id"],
                        row["date"],
                        row["measured_at_utc"],
                        row["measured_at_local"],
                        row["weight_kg"],
                        row["fat_percent"],
                        row["fat_mass_kg"],
                        row["fat_free_mass_kg"],
                        row["muscle_mass_kg"],
                        row["bone_mass_kg"],
                        row["hydration_mass_kg"],
                        row["hydration_percent"],
                        row["bmi"],
                        row["visceral_fat_mass"],
                        row["basal_met"],
                        row["active_met"],
                        row["metabolic_age"],
                        row["visceral_fat_rating"],
                        row["physique_rating"],
                        row["raw_json"],
                        now,
                    ),
                )
                if self.conn.total_changes > 0:
                    saved += 1
            except sqlite3.IntegrityError:
                pass
        self.conn.commit()
        return saved

    def get_measurements(
        self, start_date: str, end_date: str,
    ) -> list[BodyCompositionMeasurement]:
        """Return parsed measurements for a date range (inclusive)."""
        rows = self.conn.execute(
            """SELECT * FROM withings_measurements
               WHERE date BETWEEN ? AND ?
               ORDER BY measured_at_utc ASC""",
            (start_date, end_date),
        ).fetchall()
        return [self._row_to_measurement(r) for r in rows]

    def get_latest(self) -> BodyCompositionMeasurement | None:
        """Return the most recent measurement by ``measured_at_utc``."""
        row = self.conn.execute(
            """SELECT * FROM withings_measurements
               ORDER BY measured_at_utc DESC LIMIT 1""",
        ).fetchone()
        if row is None:
            return None
        return self._row_to_measurement(row)

    def get_recent(self, days: int) -> list[BodyCompositionMeasurement]:
        """Return measurements from the last *days* days."""
        cutoff = (datetime.now(UTC) - timedelta(days=days)).isoformat()
        rows = self.conn.execute(
            """SELECT * FROM withings_measurements
               WHERE measured_at_utc >= ?
               ORDER BY measured_at_utc ASC""",
            (cutoff,),
        ).fetchall()
        return [self._row_to_measurement(r) for r in rows]

    def get_by_id(
        self, group_id: str,
    ) -> BodyCompositionMeasurement | None:
        """Return a single measurement by its Withings group ID."""
        row = self.conn.execute(
            "SELECT * FROM withings_measurements WHERE source_measure_group_id = ?",
            (group_id,),
        ).fetchone()
        if row is None:
            return None
        return self._row_to_measurement(row)

    def get_count(self) -> int:
        """Return total number of stored measurements."""
        row = self.conn.execute(
            "SELECT COUNT(*) AS cnt FROM withings_measurements",
        ).fetchone()
        return row["cnt"] if row else 0

    def clear(self) -> None:
        """Remove **all** stored measurements."""
        self.conn.execute("DELETE FROM withings_measurements")
        self.conn.commit()
