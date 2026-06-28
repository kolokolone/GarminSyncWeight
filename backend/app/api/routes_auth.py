"""OAuth2 authentication routes for Withings.

Endpoints:
  GET /api/withings/auth/start   — redirect to Withings authorization
  GET /api/withings/auth/callback — handle the OAuth callback
"""

from pathlib import Path
from urllib.parse import quote

from app.config import Settings, get_settings
from app.dependencies import verify_admin_token
from app.services.withings_auth import WithingsAuthService
from app.storage.token_store import TokenStore
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import RedirectResponse
from pydantic import BaseModel

router = APIRouter(prefix="/api/withings/auth", tags=["withings"])


class WithingsConfigRequest(BaseModel):
    """Local Withings OAuth configuration payload."""

    client_id: str
    client_secret: str
    redirect_uri: str | None = None
    scope: str = "user.metrics"


class WithingsConfigStatus(BaseModel):
    """Safe local Withings OAuth configuration status."""

    configured: bool
    client_id_set: bool
    client_secret_set: bool
    redirect_uri: str
    scope: str
    env_path: str


class WithingsConnectionStatus(BaseModel):
    connected: bool
    state: str
    message: str


def _get_auth(settings: Settings = Depends(get_settings)) -> WithingsAuthService:
    token_store = TokenStore(settings.resolved_data_dir)
    return WithingsAuthService(settings, token_store)


def _env_path() -> Path:
    return Path.cwd() / "config" / ".env"


def _quote_env_value(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def _upsert_env_values(path: Path, values: dict[str, str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    existing = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    keys = set(values)
    kept = [line for line in existing if line.split("=", 1)[0].strip() not in keys]
    for key, value in values.items():
        kept.append(f"{key}={_quote_env_value(value)}")
    path.write_text("\n".join(kept) + "\n", encoding="utf-8")


@router.get("/config", response_model=WithingsConfigStatus)
def auth_config_status(settings: Settings = Depends(get_settings)) -> WithingsConfigStatus:
    """Return safe Withings OAuth configuration status for the admin UI."""
    return WithingsConfigStatus(
        configured=bool(settings.withings_client_id and settings.withings_client_secret),
        client_id_set=bool(settings.withings_client_id),
        client_secret_set=bool(settings.withings_client_secret),
        redirect_uri=settings.withings_redirect_uri,
        scope=settings.withings_scope,
        env_path=str(_env_path()),
    )


@router.post("/config", response_model=WithingsConfigStatus)
def save_auth_config(
    payload: WithingsConfigRequest,
    _admin: None = Depends(verify_admin_token),
) -> WithingsConfigStatus:
    """Persist local Withings OAuth app credentials in .env.

    This endpoint is intended for localhost admin setup only. The client secret
    is written locally and never returned in the API response.
    """
    client_id = payload.client_id.strip()
    client_secret = payload.client_secret.strip()
    redirect_uri = (payload.redirect_uri or "http://127.0.0.1:8010/api/withings/auth/callback").strip()
    scope = (payload.scope or "user.metrics").strip()
    if not client_id or not client_secret:
        raise HTTPException(status_code=400, detail="Client ID et Client Secret Withings requis.")
    if "user.metrics" not in {item.strip() for item in scope.replace(" ", ",").split(",")}:
        raise HTTPException(
            status_code=400,
            detail="Le scope Withings user.metrics est obligatoire.",
        )
    _upsert_env_values(
        _env_path(),
        {
            "WITHINGS_CLIENT_ID": client_id,
            "WITHINGS_CLIENT_SECRET": client_secret,
            "WITHINGS_REDIRECT_URI": redirect_uri,
            "WITHINGS_SCOPE": scope,
        },
    )
    get_settings.cache_clear()
    settings = get_settings()
    return WithingsConfigStatus(
        configured=bool(settings.withings_client_id and settings.withings_client_secret),
        client_id_set=bool(settings.withings_client_id),
        client_secret_set=bool(settings.withings_client_secret),
        redirect_uri=settings.withings_redirect_uri,
        scope=settings.withings_scope,
        env_path=str(_env_path()),
    )


@router.get("/start")
def auth_start(
    settings: Settings = Depends(get_settings),
    auth: WithingsAuthService = Depends(_get_auth),
) -> RedirectResponse:
    """Redirect the user to Withings OAuth2 authorization page.

    The ``state`` parameter is generated and stored in memory for
    validation when the user returns via the callback.
    """
    if not auth.is_configured():
        message = quote(
            "Withings n'est pas configuré. Renseigne WITHINGS_CLIENT_ID et "
            "WITHINGS_CLIENT_SECRET dans .env, puis redémarre GarminSyncWeight."
        )
        return RedirectResponse(url=f"/withings?withings_auth=not_configured&message={message}")
    authorize_url, _state = auth.build_authorize_url()
    return RedirectResponse(url=authorize_url)


@router.get("/callback")
async def auth_callback(
    code: str = Query(default=""),
    state: str = Query(default=""),
    auth: WithingsAuthService = Depends(_get_auth),
) -> RedirectResponse:
    """Handle the OAuth2 callback from Withings.

    Exchanges the authorization code for tokens and stores them.
    """
    try:
        if not code:
            raise ValueError("Code OAuth Withings manquant.")
        if not state:
            raise ValueError("Paramètre state Withings manquant.")
        await auth.handle_callback(code, state)
        return RedirectResponse(url="/withings?withings_auth=success")
    except ValueError as exc:
        return RedirectResponse(url=f"/withings?withings_auth=error&message={str(exc)}")
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.post("/disconnect")
def auth_disconnect(
    auth: WithingsAuthService = Depends(_get_auth),
    _admin: None = Depends(verify_admin_token),
) -> dict:
    """Remove stored Withings token."""
    auth.clear_token()
    return {"ok": True, "message": "Withings token cleared."}


@router.get("/status", response_model=WithingsConnectionStatus)
async def auth_status(auth: WithingsAuthService = Depends(_get_auth)) -> WithingsConnectionStatus:
    """Return an active Withings connection status."""
    result = await auth.check_connection()
    return WithingsConnectionStatus(**result)


@router.post("/test", response_model=WithingsConnectionStatus)
async def auth_test(
    auth: WithingsAuthService = Depends(_get_auth),
    _admin: None = Depends(verify_admin_token),
) -> WithingsConnectionStatus:
    """Actively test the Withings API connection."""
    result = await auth.check_connection()
    return WithingsConnectionStatus(**result)
