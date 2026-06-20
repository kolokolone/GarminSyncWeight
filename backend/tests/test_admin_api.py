"""Tests for the local admin UI and Garmin auth API surface."""

from pathlib import Path
from urllib.parse import parse_qs, urlparse

from app.config import Settings, get_settings
from app.main import app
from app.services.withings_auth import WithingsAuthService
from app.storage.token_store import TokenStore
from fastapi.testclient import TestClient


def _settings(tmp_path: Path) -> Settings:
    return Settings(  # type: ignore[call-arg]
        withings_client_id="",
        withings_client_secret="",
        data_dir=tmp_path / "data",
        log_dir=tmp_path / "logs",
        runtime_dir=tmp_path / "runtime",
        garmin_token_dir=tmp_path / "garmin-token-missing",
    )


def test_local_admin_root_serves_frontend() -> None:
    """The local root must serve the admin site, not only JSON."""
    client = TestClient(app)
    response = client.get("/")
    assert response.status_code == 200
    assert "GarminSyncWeight Admin" in response.text
    assert "Connecte Withings et Garmin" in response.text


def test_frontend_routes_fallback_to_admin() -> None:
    """Client-side admin routes should load the same frontend shell."""
    client = TestClient(app)
    response = client.get("/garmin")
    assert response.status_code == 200
    assert "GarminSyncWeight Admin" in response.text


def test_withings_start_unconfigured_redirects_to_admin(tmp_path: Path) -> None:
    """Missing Withings credentials should return the user to setup UI, not JSON."""
    app.dependency_overrides[get_settings] = lambda: _settings(tmp_path)
    try:
        client = TestClient(app)
        response = client.get("/api/withings/auth/start", follow_redirects=False)
    finally:
        app.dependency_overrides.clear()
    assert response.status_code in (302, 307)
    assert response.headers["location"].startswith("/withings?withings_auth=not_configured")


def test_withings_config_save_writes_env_without_returning_secret(
    tmp_path: Path,
    monkeypatch,
) -> None:
    """Admin can store Withings OAuth app credentials locally in .env."""
    monkeypatch.chdir(tmp_path)
    get_settings.cache_clear()
    client = TestClient(app)
    response = client.post(
        "/api/withings/auth/config",
        json={
            "client_id": "local-client-id",
            "client_secret": "local-client-secret",
            "redirect_uri": "http://127.0.0.1:8010/api/withings/auth/callback",
            "scope": "user.metrics",
        },
    )
    try:
        assert response.status_code == 200
        body = response.json()
        assert body["configured"] is True
        assert body["client_id_set"] is True
        assert body["client_secret_set"] is True
        assert "local-client-secret" not in str(body)
        env_text = (tmp_path / ".env").read_text(encoding="utf-8")
        assert 'WITHINGS_CLIENT_ID="local-client-id"' in env_text
        assert 'WITHINGS_CLIENT_SECRET="local-client-secret"' in env_text
    finally:
        get_settings.cache_clear()


def test_garmin_auth_status_no_token(tmp_path: Path) -> None:
    """Garmin auth status must be safe and not require real credentials."""
    app.dependency_overrides[get_settings] = lambda: _settings(tmp_path)
    try:
        client = TestClient(app)
        response = client.get("/api/garmin/auth/status")
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 200
    body = response.json()
    assert body["state"] == "no_token"
    assert body["token_found"] is False
    assert body["token_valid"] is False


def test_garmin_auth_disconnect_requires_confirmation(tmp_path: Path) -> None:
    """Deleting local Garmin tokens requires explicit confirmation."""
    app.dependency_overrides[get_settings] = lambda: _settings(tmp_path)
    try:
        client = TestClient(app)
        response = client.post("/api/garmin/auth/disconnect", json={"confirm": False})
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is False
    assert "Confirmation" in body["message"]


def test_withings_oauth_state_is_persistent_and_single_use(tmp_path: Path) -> None:
    """Withings OAuth state must survive service instances and be consumed once."""
    store_one = TokenStore(tmp_path)
    store_one.save_oauth_state("state-123")
    store_one.close()

    store_two = TokenStore(tmp_path)
    assert store_two.consume_oauth_state("state-123") is True
    assert store_two.consume_oauth_state("state-123") is False
    store_two.close()


def test_withings_authorize_url_contains_required_oauth_params(tmp_path: Path) -> None:
    """Withings connect URL must contain the required OAuth2 parameters."""
    settings = Settings(  # type: ignore[call-arg]
        withings_client_id="client-id",
        withings_client_secret="client-secret",
        withings_redirect_uri="http://127.0.0.1:8010/api/withings/auth/callback",
        withings_scope="user.metrics",
        data_dir=tmp_path,
    )
    auth = WithingsAuthService(settings, TokenStore(tmp_path))
    url, state = auth.build_authorize_url()
    parsed = urlparse(url)
    query = parse_qs(parsed.query)
    assert parsed.scheme == "https"
    assert query["response_type"] == ["code"]
    assert query["client_id"] == ["client-id"]
    assert query["redirect_uri"] == ["http://127.0.0.1:8010/api/withings/auth/callback"]
    assert query["scope"] == ["user.metrics"]
    assert query["state"] == [state]
