"""Tests for the Garmin credential + OTP authentication flow."""

import time
from pathlib import Path
from typing import Any

import garminconnect
import pytest
from app.config import Settings
from app.services import garmin_auth_service as auth_module
from app.services.garmin_auth_service import GarminAuthService


class FakeGarminFactory:
    """Minimal stand-in for ``garminconnect.Garmin`` with controllable outcomes."""

    def __init__(self) -> None:
        self.start_result: tuple[str | None, Any] = (
            "needs_mfa",
            {"domain": "garmin.com", "flow": "portal"},
        )
        self.start_error: Exception | None = None
        self.resume_errors: list[Exception] = []
        self.status_error: Exception | None = None
        self.start_calls: list[dict[str, Any]] = []
        self.resume_calls: list[tuple[Any, str]] = []
        self.dumped_paths: list[str] = []

    def __call__(self, **kwargs: Any) -> "FakeGarmin":
        return FakeGarmin(self, **kwargs)


class FakeGarmin:
    def __init__(self, factory: FakeGarminFactory, **kwargs: Any) -> None:
        self.factory = factory
        self.kwargs = kwargs
        self.client = _FakeClient(factory)

    def login(self, tokenstore: str | None = None) -> tuple[None, None]:
        token_file = Path(tokenstore or "") / "garmin_tokens.json"
        if not token_file.exists():
            raise garminconnect.GarminConnectAuthenticationError("missing tokens")
        if self.factory.status_error is not None:
            raise self.factory.status_error
        return None, None

    def resume_login(self, client_state: Any, otp: str) -> tuple[None, None]:
        self.factory.resume_calls.append((client_state, otp))
        if self.factory.resume_errors:
            raise self.factory.resume_errors.pop(0)
        return None, None

    def get_full_name(self) -> str:
        return "Test User"


class _FakeClient:
    def __init__(self, factory: FakeGarminFactory) -> None:
        self.factory = factory

    def login(
        self,
        email: str,
        password: str,
        return_on_mfa: bool = False,
    ) -> tuple[str | None, Any]:
        self.factory.start_calls.append(
            {"email": email, "password": password, "return_on_mfa": return_on_mfa}
        )
        if self.factory.start_error is not None:
            raise self.factory.start_error
        return self.factory.start_result

    def dump(self, path: str) -> None:
        self.factory.dumped_paths.append(path)
        target = Path(path)
        target.mkdir(parents=True, exist_ok=True)
        (target / "garmin_tokens.json").write_text("{}", encoding="utf-8")


@pytest.fixture(autouse=True)
def _clear_sessions() -> Any:
    GarminAuthService.clear_sessions()
    yield
    GarminAuthService.clear_sessions()


@pytest.fixture
def factory(monkeypatch: pytest.MonkeyPatch) -> FakeGarminFactory:
    fake = FakeGarminFactory()
    monkeypatch.setattr(auth_module, "_garmin_class", lambda: fake)
    return fake


@pytest.fixture
def service(tmp_path: Path) -> GarminAuthService:
    settings = Settings(  # type: ignore[call-arg]
        garmin_token_dir=tmp_path / "garmin",
        data_dir=tmp_path / "data",
        log_dir=tmp_path / "logs",
        runtime_dir=tmp_path / "runtime",
    )
    return GarminAuthService(settings)


def _start_mfa(service: GarminAuthService, factory: FakeGarminFactory) -> str:
    result = service.login(email="user@example.com", password="secret")
    assert result.needs_otp is True
    assert result.error_code == "otp_required"
    assert result.auth_session_id
    assert factory.start_calls == [
        {"email": "user@example.com", "password": "secret", "return_on_mfa": True}
    ]
    return result.auth_session_id


def test_start_returns_otp_session_without_storing_credentials(
    service: GarminAuthService, factory: FakeGarminFactory
) -> None:
    session_id = _start_mfa(service, factory)

    session = GarminAuthService._sessions[session_id]
    assert session.api.kwargs == {"return_on_mfa": True}
    assert not hasattr(session.api, "password")
    assert "secret" not in repr(session.__dict__.keys())


def test_complete_otp_persists_tokens_and_verifies(
    service: GarminAuthService, factory: FakeGarminFactory
) -> None:
    session_id = _start_mfa(service, factory)

    result = service.login(auth_session_id=session_id, otp=" 123456 ")

    assert result.ok is True
    assert result.status.token_valid is True
    assert result.status.state == "connected"
    assert factory.resume_calls == [({"domain": "garmin.com", "flow": "portal"}, "123456")]
    assert factory.dumped_paths == [str(service.token_dir)]
    assert (service.token_dir / "garmin_tokens.json").is_file()
    assert session_id not in GarminAuthService._sessions


def test_invalid_otp_keeps_session_for_retry(
    service: GarminAuthService, factory: FakeGarminFactory
) -> None:
    session_id = _start_mfa(service, factory)
    factory.resume_errors = [
        garminconnect.GarminConnectAuthenticationError("MFA verification failed")
    ]

    failed = service.login(auth_session_id=session_id, otp="000000")
    assert failed.ok is False
    assert failed.error_code == "otp_invalid"
    assert session_id in GarminAuthService._sessions

    retried = service.login(auth_session_id=session_id, otp="123456")
    assert retried.ok is True
    assert session_id not in GarminAuthService._sessions


def test_mfa_network_error_keeps_session(
    service: GarminAuthService, factory: FakeGarminFactory
) -> None:
    session_id = _start_mfa(service, factory)
    factory.resume_errors = [
        garminconnect.GarminConnectAuthenticationError(
            "MFA verification failed: https://sso.garmin.com: connection error"
        )
    ]

    result = service.login(auth_session_id=session_id, otp="123456")

    assert result.error_code == "garmin_unavailable"
    assert session_id in GarminAuthService._sessions
    assert GarminAuthService._sessions[session_id].attempts == 0


def test_profile_failure_after_mfa_is_terminal(
    service: GarminAuthService, factory: FakeGarminFactory
) -> None:
    session_id = _start_mfa(service, factory)
    factory.resume_errors = [
        garminconnect.GarminConnectAuthenticationError("Failed to retrieve user settings")
    ]

    result = service.login(auth_session_id=session_id, otp="123456")

    assert result.error_code == "verify_failed"
    assert session_id not in GarminAuthService._sessions


def test_expired_session_is_rejected(
    service: GarminAuthService, factory: FakeGarminFactory
) -> None:
    session_id = _start_mfa(service, factory)
    GarminAuthService._sessions[session_id].created = time.monotonic() - 301

    result = service.login(auth_session_id=session_id, otp="123456")

    assert result.ok is False
    assert result.error_code == "otp_expired"
    assert session_id not in GarminAuthService._sessions
    assert factory.resume_calls == []


def test_otp_locked_after_three_failures(
    service: GarminAuthService, factory: FakeGarminFactory
) -> None:
    session_id = _start_mfa(service, factory)
    factory.resume_errors = [
        garminconnect.GarminConnectAuthenticationError("MFA verification failed")
        for _ in range(3)
    ]

    codes = [
        service.login(auth_session_id=session_id, otp=code).error_code
        for code in ("111111", "222222", "333333")
    ]

    assert codes == ["otp_invalid", "otp_invalid", "otp_locked"]
    assert session_id not in GarminAuthService._sessions


def test_invalid_credentials_returns_clear_error(
    service: GarminAuthService, factory: FakeGarminFactory
) -> None:
    factory.start_error = garminconnect.GarminConnectAuthenticationError("bad password")

    result = service.login(email="user@example.com", password="wrong")

    assert result.ok is False
    assert result.needs_otp is False
    assert result.error_code == "invalid_credentials"
    assert "mot de passe" in result.message
    assert GarminAuthService._sessions == {}


def test_rate_limit_is_reported(
    service: GarminAuthService, factory: FakeGarminFactory
) -> None:
    factory.start_error = garminconnect.GarminConnectTooManyRequestsError("429")

    result = service.login(email="user@example.com", password="secret")

    assert result.error_code == "rate_limited"
    assert result.status.state == "no_token"


def test_verify_failure_after_token_dump(
    service: GarminAuthService, factory: FakeGarminFactory
) -> None:
    session_id = _start_mfa(service, factory)
    factory.status_error = garminconnect.GarminConnectAuthenticationError("rejected")

    result = service.login(auth_session_id=session_id, otp="123456")

    assert result.ok is False
    assert result.error_code == "verify_failed"
    assert result.status.token_found is True
    assert result.status.token_valid is False


def test_login_without_mfa_persists_tokens(
    service: GarminAuthService, factory: FakeGarminFactory
) -> None:
    factory.start_result = (None, None)

    result = service.login(email="user@example.com", password="secret")

    assert result.ok is True
    assert result.needs_otp is False
    assert factory.dumped_paths == [str(service.token_dir)]
    assert service.status().token_valid is True


def test_legacy_single_call_completes_otp(
    service: GarminAuthService, factory: FakeGarminFactory
) -> None:
    result = service.login(email="user@example.com", password="secret", otp="123456")

    assert result.ok is True
    assert factory.resume_calls == [({"domain": "garmin.com", "flow": "portal"}, "123456")]


def test_http_login_otp_contract(
    service: GarminAuthService, factory: FakeGarminFactory
) -> None:
    from app.api import routes_garmin_auth as routes
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    app = FastAPI()
    app.include_router(routes.router)
    app.dependency_overrides[routes._get_garmin_auth] = lambda: service
    app.dependency_overrides[routes.verify_admin_token] = lambda: None
    client = TestClient(app)

    first = client.post(
        "/api/garmin/auth/login", json={"email": "user@example.com", "password": "secret"}
    )
    assert first.status_code == 200
    payload = first.json()
    assert payload["needs_otp"] is True
    assert payload["error_code"] == "otp_required"
    session_id = payload["auth_session_id"]
    assert session_id

    second = client.post(
        "/api/garmin/auth/login", json={"auth_session_id": session_id, "otp": "123456"}
    )
    assert second.status_code == 200
    assert second.json()["ok"] is True
    assert second.json()["status"]["token_valid"] is True


def test_session_step_requires_otp(
    service: GarminAuthService, factory: FakeGarminFactory
) -> None:
    session_id = _start_mfa(service, factory)

    result = service.login(auth_session_id=session_id, otp="   ")

    assert result.ok is False
    assert result.error_code == "otp_invalid"
    assert factory.resume_calls == []
    assert session_id in GarminAuthService._sessions
