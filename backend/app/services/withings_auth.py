"""Withings OAuth2 authentication flow.

Implements the Authorization Code flow with PKCE-like state validation.
Tokens are stored in the TokenStore (SQLite).

Endpoints:
  - GET /api/withings/auth/start  → redirect user to Withings
  - GET /api/withings/auth/callback  → handle the callback

Security:
  - state parameter is generated and validated
  - tokens are never logged or exposed via API
  - auto-refresh when token is near expiration
"""

import secrets
from typing import Any
from urllib.parse import urlencode

import httpx
from app.config import Settings
from app.storage.token_store import TokenStore

WITHINGS_AUTH_URL = "https://account.withings.com/oauth2_user/authorize2"
WITHINGS_TOKEN_URL = "https://wbsapi.withings.net/v2/oauth2"

_logger = None


def _log() -> Any:
    global _logger
    if _logger is None:
        from app.logging_config import get_logger

        _logger = get_logger("security")
    return _logger


class WithingsAuthService:
    """Handles the Withings OAuth2 dance and token lifecycle."""

    def __init__(self, settings: Settings, token_store: TokenStore) -> None:
        self._settings = settings
        self._token_store = token_store

    # ── Public API ─────────────────────────────────────────────

    def build_authorize_url(self) -> tuple[str, str]:
        """Generate the Withings authorization URL and return (url, state)."""
        state = secrets.token_urlsafe(32)
        self._token_store.save_oauth_state(state)
        params = {
            "response_type": "code",
            "client_id": self._settings.withings_client_id,
            "redirect_uri": self._settings.withings_redirect_uri,
            "scope": self._settings.withings_scope,
            "state": state,
        }
        url = f"{WITHINGS_AUTH_URL}?{urlencode(params)}"
        _log().info("Authorization URL generated — state=%s...", state[:8])
        return url, state

    async def handle_callback(self, code: str, state: str) -> dict[str, Any]:
        """Exchange the authorization code for tokens.

        Args:
            code: The authorization code from Withings.
            state: The state parameter (must match what we generated).

        Returns:
            A dict with 'ok': True and token summary (no raw tokens), or 'ok': False with error.

        Raises:
            ValueError if state is invalid.
        """
        if not self._token_store.consume_oauth_state(state):
            _log().warning("Invalid state parameter received — possible CSRF attempt")
            raise ValueError("Invalid state parameter. Restart the OAuth flow.")

        if not code:
            _log().warning("Authorization code missing in callback")
            raise ValueError("Authorization code is missing.")

        token_data = await self._exchange_code(code)
        self._token_store.save_token(token_data)

        _log().info("Withings OAuth2 tokens saved successfully")
        return {"ok": True, "message": "Withings authentication successful. Token stored."}

    async def get_valid_access_token(self) -> str:
        """Return a valid access token, refreshing if needed.

        Raises RuntimeError if no token is available or refresh fails.
        """
        token = self._token_store.get_token()
        if token is None:
            raise RuntimeError("No Withings token available. Authenticate first.")

        if self._token_store.is_token_expired():
            _log().info("Withings token expired or near-expiry — refreshing")
            refreshed = await self._refresh_access_token(token)
            self._token_store.save_token(refreshed)
            return str(refreshed["access_token"])

        return str(token["access_token"])

    def is_configured(self) -> bool:
        """Return True if Withings client credentials are set."""
        return bool(self._settings.withings_client_id and self._settings.withings_client_secret)

    def has_token(self) -> bool:
        """Return True if a token is stored."""
        return self._token_store.get_token() is not None

    def clear_token(self) -> None:
        """Remove the stored token (disconnect)."""
        self._token_store.clear_token()
        _log().info("Withings token cleared")

    # ── Internal helpers ───────────────────────────────────────

    async def _exchange_code(self, code: str) -> dict[str, Any]:
        """Exchange an authorization code for tokens via the Withings API."""
        _log().info("Exchanging authorization code for tokens")
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                WITHINGS_TOKEN_URL,
                data={
                    "action": "requesttoken",
                    "grant_type": "authorization_code",
                    "client_id": self._settings.withings_client_id,
                    "client_secret": self._settings.withings_client_secret,
                    "code": code,
                    "redirect_uri": self._settings.withings_redirect_uri,
                },
            )
            resp.raise_for_status()
            body = resp.json()
            _log().info("Token exchange response status: %s", body.get("status"))
            if body.get("status") != 0:
                error = body.get("error", "unknown")
                _log().error(
                    "Token exchange failed — status=%s error=%s",
                    body.get("status"), error,
                )
                raise RuntimeError(f"Withings token exchange failed: {error}")
            return body["body"]

    async def _refresh_access_token(self, token: dict[str, Any]) -> dict[str, Any]:
        """Refresh an expired token."""
        refresh_token = token.get("refresh_token", "")
        if not refresh_token:
            raise RuntimeError("No refresh token available. Re-authenticate with Withings.")

        _log().info("Refreshing Withings access token")
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                WITHINGS_TOKEN_URL,
                data={
                    "action": "requesttoken",
                    "grant_type": "refresh_token",
                    "client_id": self._settings.withings_client_id,
                    "client_secret": self._settings.withings_client_secret,
                    "refresh_token": refresh_token,
                },
            )
            resp.raise_for_status()
            body = resp.json()
            if body.get("status") != 0:
                error = body.get("error", "unknown")
                _log().error("Token refresh failed — status=%s error=%s", body.get("status"), error)
                raise RuntimeError(f"Withings token refresh failed: {error}")
            return body["body"]
