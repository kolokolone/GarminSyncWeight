"""Pydantic models for local Garmin authentication API."""

from typing import Literal

from pydantic import BaseModel

GarminAuthState = Literal[
    "unknown", "no_token", "connected", "auth_invalid", "needs_otp", "error"
]


class GarminAuthStatus(BaseModel):
    """Current local Garmin authentication status."""

    state: GarminAuthState = "unknown"
    token_found: bool = False
    token_valid: bool = False
    token_dir: str = ""
    message: str = ""


class GarminLoginRequest(BaseModel):
    """Garmin login payload. Credentials are never persisted."""

    email: str | None = None
    password: str | None = None
    otp: str | None = None
    auth_session_id: str | None = None  # For step 2 of MFA flow


class GarminAuthResult(BaseModel):
    """Result of a Garmin auth attempt."""

    ok: bool = False
    assisted: bool = False
    needs_otp: bool = False
    message: str = ""
    command: list[str] | None = None
    status: GarminAuthStatus
    auth_session_id: str | None = None  # For step 2 of MFA flow
    error_code: str | None = None
    # Values: "invalid_credentials", "otp_required", "otp_invalid",
    #   "otp_expired", "timeout", "garmin_unavailable",
    #   "already_connected", "disconnected", "verify_failed"


class DisconnectRequest(BaseModel):
    """Explicit confirmation payload for token deletion."""

    confirm: bool = False


class DisconnectResult(BaseModel):
    """Result of Garmin local token deletion."""

    ok: bool = False
    message: str = ""
