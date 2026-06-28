"""GET /api/status — health check and configuration overview (cached 60s).
GET /api/healthz — local Docker healthcheck (no external API calls)."""

from app.cache import get_cache
from app.config import Settings, get_settings
from app.models.sync import StatusResponse
from app.services.garmin_client import GarminClient
from app.services.withings_auth import WithingsAuthService
from app.storage.sync_store import SyncStore
from app.storage.token_store import TokenStore
from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

router = APIRouter(tags=["status"])

_STATUS_CACHE_TTL = 60  # seconds


@router.get("/api/healthz")
def healthz(settings: Settings = Depends(get_settings)) -> JSONResponse:
    """Local health check — no external API calls.

    Docker healthcheck uses this endpoint. It must NOT test Withings,
    Garmin, OAuth, tokens, or any external service. If those are down,
    the container should still report healthy.
    """
    ok = True
    dirs = {
        "data": settings.resolved_data_dir,
        "logs": settings.resolved_log_dir,
        "runtime": settings.resolved_runtime_dir,
        "reports": settings.reports_dir,
    }
    checks: dict[str, bool] = {}
    for name, path in dirs.items():
        exists = path.exists()
        checks[name] = exists
        if not exists:
            ok = False

    status_code = 200 if ok else 503
    return JSONResponse(
        content={"status": "healthy" if ok else "unhealthy", "checks": checks},
        status_code=status_code,
    )


def _get_auth(settings: Settings = Depends(get_settings)) -> WithingsAuthService:
    token_store = TokenStore(settings.resolved_data_dir)
    return WithingsAuthService(settings, token_store)


@router.get("/api/status", response_model=StatusResponse)
async def get_status(
    settings: Settings = Depends(get_settings),
    auth: WithingsAuthService = Depends(_get_auth),
) -> StatusResponse:
    cache = get_cache()
    cached = cache.get("status_response")
    if cached is not None:
        return cached
    """Return the application status and configuration overview.

    No secrets are exposed. Token presence is reported as boolean only.
    """
    withings_configured = auth.is_configured()
    withings_token = auth.has_token()
    withings_status = await auth.check_connection()
    garmin_status = await GarminClient(settings).check_connection()

    sync_store = SyncStore(settings.resolved_data_dir)
    last_sync = sync_store.last_sync_time()

    from app.services.report_builder import ReportBuilder

    report_builder = ReportBuilder(settings)
    latest_report = report_builder.latest_report_path()
    last_report = latest_report.name if latest_report else None

    if not withings_configured:
        state = "not_configured"
        message = (
            "Withings client ID not configured. "
            "Set WITHINGS_CLIENT_ID and WITHINGS_CLIENT_SECRET."
        )
    elif not withings_status.get("connected"):
        state = "needs_auth"
        message = withings_status.get("message", "Withings non connecté.")
    elif not garmin_status.get("connected"):
        state = "needs_auth"
        message = garmin_status.get("message", "Garmin non connecté.")
    else:
        state = "ready"
        message = "GarminSyncWeight prêt pour une synchronisation contrôlée."

    result = StatusResponse(
        app_name="GarminSyncWeight",
        version=settings.app_version,
        state=state,
        message=message,
        withings_configured=withings_configured,
        withings_token_present=withings_token,
        withings_connection_state=str(withings_status.get("state", "unknown")),
        garmin_connection_state=str(garmin_status.get("state", "unknown")),
        last_sync=last_sync,
        last_report=last_report,
    )
    cache.set("status_response", result, ttl_seconds=_STATUS_CACHE_TTL)
    return result
