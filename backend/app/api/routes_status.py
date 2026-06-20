"""GET /api/status — health check and configuration overview."""

from app.config import Settings, get_settings
from app.models.sync import StatusResponse
from app.services.withings_auth import WithingsAuthService
from app.storage.sync_store import SyncStore
from app.storage.token_store import TokenStore
from fastapi import APIRouter, Depends

router = APIRouter(tags=["status"])


def _get_auth(settings: Settings = Depends(get_settings)) -> WithingsAuthService:
    token_store = TokenStore(settings.resolved_data_dir)
    return WithingsAuthService(settings, token_store)


@router.get("/api/status", response_model=StatusResponse)
def get_status(
    settings: Settings = Depends(get_settings),
    auth: WithingsAuthService = Depends(_get_auth),
) -> StatusResponse:
    """Return the application status and configuration overview.

    No secrets are exposed. Token presence is reported as boolean only.
    """
    withings_configured = auth.is_configured()
    withings_token = auth.has_token()

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
    elif not withings_token:
        state = "needs_auth"
        message = "Withings OAuth2 token missing. Authenticate via /api/withings/auth/start."
    else:
        state = "ready"
        message = "GarminSyncWeight ready. Use POST /api/sync/dry-run to test the pipeline."

    return StatusResponse(
        app_name="GarminSyncWeight",
        version=settings.app_version,
        state=state,
        message=message,
        withings_configured=withings_configured,
        withings_token_present=withings_token,
        dry_run_default=settings.dry_run_default,
        write_enabled=settings.enable_garmin_writes,
        last_sync=last_sync,
        last_report=last_report,
    )
