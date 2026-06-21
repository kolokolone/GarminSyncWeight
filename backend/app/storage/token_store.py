"""Persistent OAuth2 token store for Withings."""

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
        """Atomically store the latest token, including rotated refresh tokens."""
        now = datetime.now(UTC).isoformat()
        expires_in = int(token_data.get("expires_in", 3600))
        expires_at = time.time() + expires_in
        self.conn.execute("DELETE FROM withings_tokens")  # keep at most one
        self.conn.execute(
            """INSERT INTO withings_tokens
               (userid, access_token, refresh_token, token_type,
                expires_at, scope, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                str(token_data.get("userid", "")) or None,
                token_data["access_token"],
                token_data.get("refresh_token", ""),
                token_data.get("token_type", "Bearer"),
                expires_at,
                token_data.get("scope", ""),
                now,
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
            "SELECT userid, access_token, refresh_token, token_type, expires_at, scope "
            "FROM withings_tokens ORDER BY id DESC LIMIT 1"
        ).fetchone()
        if row is None:
            return None
        row_dict = dict(row)
        return {
            "access_token": row_dict["access_token"],
            "refresh_token": row_dict["refresh_token"],
            "token_type": row_dict["token_type"],
            "expires_at": row_dict["expires_at"],
            "scope": row_dict["scope"],
            "userid": row_dict.get("userid"),
        }

    def is_token_expired(self, margin_seconds: int = 300) -> bool:
        """Return True if the stored token is expired or missing."""
        token = self.get_token()
        if token is None:
            return True
        return time.time() >= float(token.get("expires_at", 0)) - margin_seconds

    def token_scope(self) -> str:
        token = self.get_token()
        return str(token.get("scope", "")) if token else ""

    def has_scope(self, required_scope: str) -> bool:
        scopes = {
            scope.strip()
            for scope in self.token_scope().replace(" ", ",").split(",")
            if scope.strip()
        }
        return required_scope in scopes

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
