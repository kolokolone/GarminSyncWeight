"""Persistent OAuth2 token store for Withings.

Tokens are stored in the SQLite database at ``data/withings_tokens.db``.
Only one token row is kept (the latest). Old rows are cleaned on write.

Security:
  - Tokens are never logged (redact.py catches ``access_token`` / ``refresh_token``).
  - The database file is in ``data/`` which is excluded from git.
  - No token is ever exposed through the API.
"""

import time
from datetime import UTC, datetime
from pathlib import Path
from sqlite3 import Connection
from typing import Any

from app.storage.db import init_db

TOKEN_DB_FILENAME = "withings_tokens.db"


class TokenStore:
    """Persistent OAuth2 token store backed by SQLite."""

    def __init__(self, data_dir: Path) -> None:
        self._db_path = data_dir / TOKEN_DB_FILENAME
        self._conn: Connection | None = None

    @property
    def conn(self) -> Connection:
        if self._conn is None:
            self._conn = init_db(self._db_path)
        return self._conn

    def save_token(self, token_data: dict[str, Any]) -> None:
        """Atomically store the latest token, removing any previous row."""
        now = datetime.now(UTC).isoformat()
        expires_in = token_data.get("expires_in", 3600)
        expires_at = time.time() + expires_in
        self.conn.execute("DELETE FROM withings_tokens")  # keep at most one
        self.conn.execute(
            """INSERT INTO withings_tokens
               (access_token, refresh_token, token_type, expires_at, scope, created_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (
                token_data["access_token"],
                token_data.get("refresh_token", ""),
                token_data.get("token_type", "Bearer"),
                expires_at,
                token_data.get("scope", ""),
                now,
            ),
        )
        self.conn.commit()

    def save_oauth_state(self, state: str) -> None:
        """Store a temporary OAuth state for callback validation."""
        self.conn.execute(
            "INSERT OR REPLACE INTO withings_oauth_states (state, created_at) VALUES (?, ?)",
            (state, time.time()),
        )
        self.conn.commit()

    def consume_oauth_state(self, state: str, max_age_seconds: int = 600) -> bool:
        """Validate and remove a temporary OAuth state.

        States are single-use and expire after ``max_age_seconds``.
        """
        row = self.conn.execute(
            "SELECT created_at FROM withings_oauth_states WHERE state = ?",
            (state,),
        ).fetchone()
        self.conn.execute("DELETE FROM withings_oauth_states WHERE state = ?", (state,))
        self.conn.execute(
            "DELETE FROM withings_oauth_states WHERE created_at < ?",
            (time.time() - max_age_seconds,),
        )
        self.conn.commit()
        if row is None:
            return False
        return time.time() - float(row["created_at"]) <= max_age_seconds

    def get_token(self) -> dict[str, Any] | None:
        """Return the stored token dict, or None."""
        row = self.conn.execute(
            "SELECT access_token, refresh_token, token_type, expires_at, scope "
            "FROM withings_tokens ORDER BY id DESC LIMIT 1"
        ).fetchone()
        if row is None:
            return None
        return {
            "access_token": row["access_token"],
            "refresh_token": row["refresh_token"],
            "token_type": row["token_type"],
            "expires_at": row["expires_at"],
            "scope": row["scope"],
        }

    def is_token_expired(self) -> bool:
        """Return True if the stored token is expired or missing."""
        token = self.get_token()
        if token is None:
            return True
        return time.time() >= token.get("expires_at", 0) - 60  # 1 min safety margin

    def get_access_token(self) -> str | None:
        """Return the current access token, or None."""
        token = self.get_token()
        return token["access_token"] if token else None

    def get_refresh_token(self) -> str | None:
        """Return the stored refresh token, or None."""
        token = self.get_token()
        return token.get("refresh_token") if token else None

    def clear_token(self) -> None:
        """Remove all stored tokens."""
        self.conn.execute("DELETE FROM withings_tokens")
        self.conn.commit()

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None
