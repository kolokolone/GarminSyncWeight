"""Tests for GET /api/healthz — local Docker healthcheck endpoint."""

import pytest
from app.config import get_settings
from app.main import create_app
from fastapi.testclient import TestClient


@pytest.fixture
def client():
    """TestClient with a fresh app (no cached settings interference)."""
    get_settings.cache_clear()
    app = create_app()
    return TestClient(app)


def test_healthz_returns_200_when_dirs_exist(client):
    """GET /api/healthz should return 200 with healthy status."""
    response = client.get("/api/healthz")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert all(data["checks"].values()), f"Some dirs missing: {data['checks']}"


def test_healthz_returns_503_when_dir_missing(monkeypatch, tmp_path):
    """GET /api/healthz should return 503 when a required dir is missing."""
    # Use a path that exists so create_app() can start, then destroy it
    runtime_dir = tmp_path / "runtime_test"
    runtime_dir.mkdir()
    monkeypatch.setenv("RUNTIME_DIR", str(runtime_dir))

    get_settings.cache_clear()
    app = create_app()
    client = TestClient(app)

    # Verify healthy first
    resp = client.get("/api/healthz")
    assert resp.status_code == 200

    # Now delete the runtime dir and check healthz
    import shutil
    shutil.rmtree(str(runtime_dir))
    resp = client.get("/api/healthz")
    assert resp.status_code == 503
    data = resp.json()
    assert data["status"] == "unhealthy"


def test_healthz_no_external_api_calls(client):
    """GET /api/healthz must not call Withings, Garmin, or any external API.

    The endpoint is synchronous and returns immediately — if any external
    service is down, the healthcheck should still pass.
    """
    response = client.get("/api/healthz")
    assert response.status_code == 200
    data = response.json()
    # The response must only contain local checks, no external data
    assert "checks" in data
    assert "withings" not in data.get("checks", {})
    assert "garmin" not in data.get("checks", {})


def test_healthz_available_without_auth(client):
    """GET /api/healthz must be accessible WITHOUT admin token.

    Even when ADMIN_API_TOKEN is configured, healthz must stay open
    for Docker healthcheck.
    """
    # Default settings have admin_api_token="" — should work
    response = client.get("/api/healthz")
    assert response.status_code == 200


def test_healthz_available_with_admin_token(monkeypatch):
    """GET /api/healthz must be accessible even with ADMIN_API_TOKEN set."""
    monkeypatch.setenv("ADMIN_API_TOKEN", "secret123")
    get_settings.cache_clear()
    app = create_app()
    client = TestClient(app)

    response = client.get("/api/healthz")
    # Must NOT require auth — Docker healthcheck doesn't send tokens
    assert response.status_code == 200
