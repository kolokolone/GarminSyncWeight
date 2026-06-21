"""Withings OAuth2 authentication flow.

Implements the Authorization Code flow with CSRF state validation.
Withings does not document PKCE support for this public API flow.
Tokens are stored in SQLite and refreshed before expiry.

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
WITHINGS_USER_URL = "https://wbsapi.withings.net/v2/user"

_logger = None


def _log() -> Any:
    global _logger
    if _logger is None:
        from app.logging_config import get_logger

        _logger = get_logger("security")
    return _logger


class WithingsNotConfigured(RuntimeError):
    """Withings OAuth credentials are incomplete."""


class WithingsNotConnected(RuntimeError):
    """No usable Withings token is available."""


class WithingsTokenExpired(RuntimeError):
    """Stored Withings token is expired and cannot be used as-is."""


class WithingsRefreshFailed(RuntimeError):
    """Withings refresh-token exchange failed."""


class WithingsApiError(RuntimeError):
    """Withings API returned a non-zero status."""


class WithingsInvalidScope(RuntimeError):
    """The stored Withings token does not include user.metrics."""


class WithingsAuthService:
    """Handles the Withings OAuth2 dance and token lifecycle."""

    def __init__(self, settings: Settings, token_store: TokenStore) -> None:
        self._settings = settings
        self._token_store = token_store

    # ── Public API ─────────────────────────────────────────────

    def build_authorize_url(self) -> tuple[str, str]:
        """Generate the Withings authorization URL and return (url, state)."""
        if not self.is_configured():
            raise WithingsNotConfigured("Withings OAuth credentials are not configured.")
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
        _log().info("Withings authorization URL generated")
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
            raise ValueError("Paramètre state invalide ou expiré. Relance la connexion Withings.")

        if not code:
            _log().warning("Authorization code missing in callback")
            raise ValueError("Code OAuth Withings manquant.")

        token_data = await self._exchange_code(code)
        self._validate_scope(token_data.get("scope", ""))
        self._token_store.save_token(token_data)

        _log().info("Withings OAuth2 tokens saved successfully")
        return {"ok": True, "message": "Withings authentication successful. Token stored."}

    async def get_valid_access_token(self) -> str:
        """Return a valid access token, refreshing if needed.

        Raises explicit Withings exceptions if no usable token is available.
        """
        if not self.is_configured():
            raise WithingsNotConfigured("Withings OAuth credentials are not configured.")
        token = self._token_store.get_token()
        if token is None:
            raise WithingsNotConnected(
                "Withings n'est pas connecté. Reconnecte le compte Withings."
            )

        if not self._token_store.has_scope("user.metrics"):
            raise WithingsInvalidScope("Le token Withings ne contient pas le scope user.metrics.")

        if self._token_store.is_token_expired():
            _log().info("Withings token expired or near-expiry — refreshing")
            refreshed = await self._refresh_access_token(token)
            self._validate_scope(refreshed.get("scope", token.get("scope", "")))
            self._token_store.save_token(refreshed)
            return str(refreshed["access_token"])

        return str(token["access_token"])

    async def check_connection(self) -> dict[str, Any]:
        """Perform an active Withings API call and return safe connection status."""
        try:
            token = await self.get_valid_access_token()
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.post(
                    WITHINGS_USER_URL,
                    data={"action": "getdevice"},
                    headers={"Authorization": f"Bearer {token}"},
                )
            resp.raise_for_status()
            body = resp.json()
            if body.get("status") == 0:
                return {
                    "connected": True,
                    "state": "connected",
                    "message": "Connexion Withings vérifiée.",
                }
            status = body.get("status")
            if status in (214, 343):
                return {
                    "connected": False,
                    "state": "auth_error",
                    "message": "Authentification Withings invalide. Reconnexion requise.",
                }
            return {
                "connected": False,
                "state": "api_error",
                "message": f"Erreur API Withings: {status}",
            }
        except WithingsInvalidScope as exc:
            return {"connected": False, "state": "scope_insufficient", "message": str(exc)}
        except WithingsNotConfigured as exc:
            return {"connected": False, "state": "not_configured", "message": str(exc)}
        except WithingsNotConnected as exc:
            return {"connected": False, "state": "not_connected", "message": str(exc)}
        except WithingsRefreshFailed as exc:
            return {"connected": False, "state": "refresh_failed", "message": str(exc)}
        except Exception as exc:
            return {"connected": False, "state": "api_error", "message": str(exc)}

    def is_configured(self) -> bool:
        """Return True if Withings client credentials are set."""
        return bool(self._settings.withings_client_id and self._settings.withings_client_secret)

    def has_token(self) -> bool:
        """Return True if a token is stored."""
        return self._token_store.get_token() is not None

    def disconnect(self) -> None:
        """Remove the stored token (disconnect)."""
        self._token_store.clear_token()
        _log().info("Withings token cleared")

    clear_token = disconnect

    # ── Internal helpers ───────────────────────────────────────

    async def _exchange_code(self, code: str) -> dict[str, Any]:
        """Exchange an authorization code for tokens via the Withings API."""
        _log().info("Exchanging authorization code for tokens")
        async with httpx.AsyncClient(timeout=15) as client:
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
                raise WithingsApiError(f"Withings token exchange failed: {error}")
            return body["body"]

    async def _refresh_access_token(self, token: dict[str, Any]) -> dict[str, Any]:
        """Refresh an expired token."""
        refresh_token = token.get("refresh_token", "")
        if not refresh_token:
            raise WithingsRefreshFailed("Refresh token Withings absent. Reconnexion requise.")

        _log().info("Refreshing Withings access token")
        async with httpx.AsyncClient(timeout=15) as client:
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
                raise WithingsRefreshFailed(f"Withings token refresh failed: {error}")
            return body["body"]

    @staticmethod
    def _validate_scope(scope: str) -> None:
        scopes = {item.strip() for item in scope.replace(" ", ",").split(",") if item.strip()}
        if "user.metrics" not in scopes:
            raise WithingsInvalidScope(
                "Le scope user.metrics est obligatoire pour lire les mesures Withings."
            )
