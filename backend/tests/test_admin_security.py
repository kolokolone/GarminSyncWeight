"""Tests for ADMIN_API_TOKEN protection on sensitive routes."""

import pytest
from app.config import get_settings
from app.main import create_app
from fastapi.testclient import TestClient

# ── Helpers ────────────────────────────────────────────────────────


def _make_client(monkeypatch, admin_api_token: str = ""):
    """Create a TestClient with a specific ADMIN_API_TOKEN."""
    monkeypatch.setenv("ADMIN_API_TOKEN", admin_api_token)
    get_settings.cache_clear()
    app = create_app()
    return TestClient(app)


# ── Access without token configured ─────────────────────────────────


def test_all_routes_open_when_token_empty(monkeypatch):
    """When ADMIN_API_TOKEN is empty, all protected routes must be accessible."""
    client = _make_client(monkeypatch, admin_api_token="")

    # POST /api/withings/auth/config
    resp = client.post("/api/withings/auth/config", json={
        "client_id": "test", "client_secret": "test"
    })
    assert resp.status_code != 401, f"POST /config blocked: {resp.status_code}"

    # POST /api/sync/run
    resp = client.post("/api/sync/run", json={
        "start_date": "2026-06-01", "end_date": "2026-06-01"
    })
    # 409 or other error is fine (no real tokens) — just not 401
    assert resp.status_code != 401, f"POST /sync/run blocked: {resp.status_code}"

    # GET /api/logs/backend
    resp = client.get("/api/logs/backend")
    assert resp.status_code != 401, f"GET /logs blocked: {resp.status_code}"


# ── Access denied without token ────────────────────────────────────


def test_protected_route_denied_without_token(monkeypatch):
    """Protected routes return 401 when ADMIN_API_TOKEN is configured
    and no valid token is provided."""
    client = _make_client(monkeypatch, admin_api_token="secret123")

    resp = client.post("/api/sync/run", json={
        "start_date": "2026-06-01", "end_date": "2026-06-01"
    })
    assert resp.status_code == 401
    assert "Token admin requis" in resp.json()["detail"]


# ── Access granted with Authorization header ───────────────────────


def test_protected_route_ok_with_bearer_header(monkeypatch):
    """Protected routes accept Authorization: Bearer <token>."""
    client = _make_client(monkeypatch, admin_api_token="secret123")

    resp = client.post("/api/sync/run", json={
        "start_date": "2026-06-01", "end_date": "2026-06-01"
    }, headers={"Authorization": "Bearer secret123"})
    assert resp.status_code != 401, f"Bearer auth rejected: {resp.status_code}"


# ── Access granted with query param ─────────────────────────────────


def test_protected_route_ok_with_query_param(monkeypatch):
    """Protected routes accept ?token=<token> query parameter."""
    client = _make_client(monkeypatch, admin_api_token="secret123")

    resp = client.post("/api/sync/run?token=secret123", json={
        "start_date": "2026-06-01", "end_date": "2026-06-01"
    })
    assert resp.status_code != 401, f"Query param auth rejected: {resp.status_code}"


# ── Wrong token rejected ───────────────────────────────────────────


def test_wrong_token_rejected(monkeypatch):
    """Wrong token returns 401."""
    client = _make_client(monkeypatch, admin_api_token="secret123")

    resp = client.post("/api/sync/run", json={
        "start_date": "2026-06-01", "end_date": "2026-06-01"
    }, headers={"Authorization": "Bearer wrongtoken"})
    assert resp.status_code == 401


def test_wrong_query_token_rejected(monkeypatch):
    """Wrong ?token= returns 401."""
    client = _make_client(monkeypatch, admin_api_token="secret123")

    resp = client.post("/api/sync/run?token=wrong", json={
        "start_date": "2026-06-01", "end_date": "2026-06-01"
    })
    assert resp.status_code == 401


# ── OAuth callback NOT protected ────────────────────────────────────


def test_oauth_callback_always_accessible(monkeypatch):
    """GET /api/withings/auth/callback must NEVER require admin token,
    even when ADMIN_API_TOKEN is configured."""
    client = _make_client(monkeypatch, admin_api_token="secret123")

    # The callback requires code/state params, but it should not return 401
    # (it returns a redirect to error page instead)
    resp = client.get("/api/withings/auth/callback")
    assert resp.status_code != 401, (
        f"OAuth callback incorrectly blocked: {resp.status_code}"
    )


# ── Public GET routes remain open ───────────────────────────────────


def test_public_get_routes_open(monkeypatch):
    """Routes like /api/status, /api/measurements/latest remain open
    even with ADMIN_API_TOKEN configured."""
    client = _make_client(monkeypatch, admin_api_token="secret123")

    # /api/status (GET)
    resp = client.get("/api/status")
    assert resp.status_code != 401, f"/api/status blocked: {resp.status_code}"

    # /api/healthz (GET)
    resp = client.get("/api/healthz")
    assert resp.status_code != 401, f"/api/healthz blocked: {resp.status_code}"

    # /api/sync/reports/latest (GET)
    resp = client.get("/api/sync/reports/latest")
    assert resp.status_code != 401, f"/api/sync/reports/latest blocked: {resp.status_code}"


# ── Protected routes set ────────────────────────────────────────────

PROTECTED_ROUTES = [
    ("POST", "/api/withings/auth/config", {"client_id": "x", "client_secret": "y"}),
    ("POST", "/api/withings/auth/disconnect", None),
    ("POST", "/api/withings/auth/test", None),
    ("POST", "/api/garmin/auth/login", {"email": "x", "password": "y", "otp": ""}),
    ("POST", "/api/garmin/auth/reauthenticate", None),
    ("POST", "/api/garmin/auth/disconnect", {"confirm": True}),
    ("POST", "/api/sync/run", {"start_date": "2026-06-01", "end_date": "2026-06-01"}),
    ("POST", "/api/sync", {"start_date": "2026-06-01", "end_date": "2026-06-01"}),
    ("GET", "/api/logs/backend", None),
    ("POST", "/api/measurements/manual", {"date": "2026-06-01", "weight_kg": 70}),
    ("DELETE", "/api/measurements/manual/1", None),
]


@pytest.mark.parametrize("method,url,payload", PROTECTED_ROUTES)
def test_all_protected_routes_require_token(monkeypatch, method, url, payload):
    """Every route in PROTECTED_ROUTES must return 401 with ADMIN_API_TOKEN set."""
    client = _make_client(monkeypatch, admin_api_token="secret123")

    if method == "GET":
        resp = client.get(url)
    elif method == "POST":
        resp = client.post(url, json=payload or {})
    elif method == "DELETE":
        resp = client.delete(url)

    assert resp.status_code == 401, (
        f"{method} {url} returned {resp.status_code} instead of 401"
    )


NON_PROTECTED_ROUTES = [
    ("GET", "/api/status"),
    ("GET", "/api/healthz"),
    ("GET", "/api/withings/auth/config"),
    ("GET", "/api/withings/auth/status"),
    ("GET", "/api/garmin/auth/status"),
    ("GET", "/api/sync/reports/latest"),
    ("GET", "/api/sync/stats"),
    ("GET", "/api/measurements/latest"),
    ("GET", "/api/measurements/recent"),
    ("GET", "/api/measurements/history"),
    ("GET", "/api/measurements/manual"),
]


@pytest.mark.parametrize("method,url", NON_PROTECTED_ROUTES)
def test_non_protected_routes_stay_open(monkeypatch, method, url):
    """Public GET routes must NOT require admin token."""
    client = _make_client(monkeypatch, admin_api_token="secret123")

    if method == "GET":
        resp = client.get(url)

    assert resp.status_code != 401, (
        f"{method} {url} incorrectly blocked with 401"
    )
