"""Local Garmin authentication routes for the admin UI."""

from app.config import Settings, get_settings
from app.models.auth import (
    DisconnectRequest,
    DisconnectResult,
    GarminAuthResult,
    GarminAuthStatus,
    GarminLoginRequest,
)
from app.services.garmin_auth_service import GarminAuthService
from fastapi import APIRouter, Depends

router = APIRouter(prefix="/api/garmin/auth", tags=["garmin-auth"])


def _get_garmin_auth(settings: Settings = Depends(get_settings)) -> GarminAuthService:
    return GarminAuthService(settings)


@router.get("/status", response_model=GarminAuthStatus)
def status(auth: GarminAuthService = Depends(_get_garmin_auth)) -> GarminAuthStatus:
    """Return Garmin local token status."""
    return auth.status()


@router.post("/login", response_model=GarminAuthResult)
def login(
    payload: GarminLoginRequest,
    auth: GarminAuthService = Depends(_get_garmin_auth),
) -> GarminAuthResult:
    """Start or complete Garmin MCP authentication."""
    return auth.login(payload.email, payload.password, payload.otp)


@router.post("/verify", response_model=GarminAuthStatus)
def verify(auth: GarminAuthService = Depends(_get_garmin_auth)) -> GarminAuthStatus:
    """Verify Garmin token validity."""
    return auth.status()


@router.post("/reauthenticate", response_model=GarminAuthResult)
def reauthenticate(auth: GarminAuthService = Depends(_get_garmin_auth)) -> GarminAuthResult:
    """Return assisted Garmin auth command for reauthentication."""
    return auth.login()


@router.post("/disconnect", response_model=DisconnectResult)
def disconnect(
    payload: DisconnectRequest,
    auth: GarminAuthService = Depends(_get_garmin_auth),
) -> DisconnectResult:
    """Delete local Garmin token files with explicit confirmation."""
    return auth.disconnect(payload.confirm)
