"""SQLite database initialisation and connection management.

Tables:
  - withings_tokens : OAuth2 token storage
  - withings_oauth_states : temporary OAuth2 state validation
  - sync_events     : idempotency & sync history
"""

import sqlite3
from pathlib import Path

SYNC_SCHEMA = """
CREATE TABLE IF NOT EXISTS sync_events (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    idempotency_key TEXT UNIQUE NOT NULL,
    source      TEXT NOT NULL,
    source_measure_group_id TEXT,
    source_measured_at_utc TEXT,
    garmin_date TEXT NOT NULL,
    weight_kg   TEXT,
    status      TEXT NOT NULL,
    dry_run     INTEGER NOT NULL,
    garmin_write_method TEXT,
    garmin_response_json TEXT,
    report_json TEXT,
    created_at  TEXT NOT NULL
);
"""

TOKEN_SCHEMA = """
CREATE TABLE IF NOT EXISTS withings_tokens (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    access_token    TEXT NOT NULL,
    refresh_token   TEXT NOT NULL,
    token_type      TEXT NOT NULL DEFAULT 'Bearer',
    expires_at      REAL NOT NULL,
    scope           TEXT,
    created_at      TEXT NOT NULL
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
    conn.executescript(SYNC_SCHEMA)
    conn.commit()
    return conn
