"""SQLite database initialisation and connection management."""

import sqlite3
from pathlib import Path

SYNC_SCHEMA = """
CREATE TABLE IF NOT EXISTS sync_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    idempotency_key TEXT UNIQUE NOT NULL,
    source TEXT NOT NULL,
    withings_measure_id TEXT,
    source_measured_at_utc TEXT,
    local_date TEXT NOT NULL,
    weight_kg TEXT,
    payload_hash TEXT,
    status TEXT NOT NULL,
    garmin_write_method TEXT,
    garmin_measure_id TEXT,
    garmin_response_json TEXT,
    error_message TEXT,
    report_json TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
"""

ATTEMPT_SCHEMA = """
CREATE TABLE IF NOT EXISTS sync_attempts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at TEXT NOT NULL,
    completed_at TEXT,
    start_date TEXT NOT NULL,
    end_date TEXT NOT NULL,
    status TEXT NOT NULL,
    summary_json TEXT,
    error_message TEXT
);
"""

TOKEN_SCHEMA = """
CREATE TABLE IF NOT EXISTS withings_tokens (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    userid          TEXT,
    access_token    TEXT NOT NULL,
    refresh_token   TEXT NOT NULL,
    token_type      TEXT NOT NULL DEFAULT 'Bearer',
    expires_at      REAL NOT NULL,
    scope           TEXT,
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL
);
"""

STATE_SCHEMA = """
CREATE TABLE IF NOT EXISTS withings_oauth_states (
    state       TEXT PRIMARY KEY,
    created_at  REAL NOT NULL
);
"""


def init_db(db_path: Path) -> sqlite3.Connection:
    """Open or create the SQLite database and ensure all tables exist."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA foreign_keys=ON;")
    conn.executescript(TOKEN_SCHEMA)
    conn.executescript(STATE_SCHEMA)
    _migrate_sync_events_if_needed(conn)
    conn.executescript(SYNC_SCHEMA)
    conn.executescript(ATTEMPT_SCHEMA)
    _ensure_column(conn, "withings_tokens", "userid", "TEXT")
    _ensure_column(conn, "withings_tokens", "updated_at", "TEXT")
    _ensure_column(conn, "sync_events", "withings_measure_id", "TEXT")
    _ensure_column(conn, "sync_events", "local_date", "TEXT")
    _ensure_column(conn, "sync_events", "payload_hash", "TEXT")
    _ensure_column(conn, "sync_events", "garmin_measure_id", "TEXT")
    _ensure_column(conn, "sync_events", "error_message", "TEXT")
    _ensure_column(conn, "sync_events", "updated_at", "TEXT")
    conn.commit()
    return conn


def _ensure_column(conn: sqlite3.Connection, table: str, column: str, definition: str) -> None:
    columns = {row[1] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}
    if column not in columns:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


def _migrate_sync_events_if_needed(conn: sqlite3.Connection) -> None:
    columns = {row[1] for row in conn.execute("PRAGMA table_info(sync_events)").fetchall()}
    legacy_column = "dry" + "_run"
    if legacy_column not in columns:
        return
    conn.execute("ALTER TABLE sync_events RENAME TO sync_events_legacy")
    conn.executescript(SYNC_SCHEMA)
    legacy_rows = conn.execute(
        """SELECT idempotency_key, source, source_measure_group_id,
                  source_measured_at_utc, garmin_date, weight_kg, status,
                  garmin_write_method, garmin_response_json, report_json, created_at
           FROM sync_events_legacy"""
    ).fetchall()
    for row in legacy_rows:
        status = str(row["status"])
        if "duplicate" in status:
            new_status = "skipped_existing"
        elif "conflict" in status:
            new_status = "skipped_conflict"
        elif "invalid" in status:
            new_status = "invalid"
        elif "written" in status:
            new_status = "synced"
        else:
            new_status = "failed"
        conn.execute(
            """INSERT OR IGNORE INTO sync_events
               (idempotency_key, source, withings_measure_id, source_measured_at_utc,
                local_date, weight_kg, status, garmin_write_method, garmin_response_json,
                report_json, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                row["idempotency_key"],
                row["source"],
                row["source_measure_group_id"],
                row["source_measured_at_utc"],
                row["garmin_date"],
                row["weight_kg"],
                new_status,
                row["garmin_write_method"],
                row["garmin_response_json"],
                row["report_json"],
                row["created_at"],
                row["created_at"],
            ),
        )
    conn.execute("DROP TABLE sync_events_legacy")
