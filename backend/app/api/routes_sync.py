"""Controlled synchronization routes."""

from app.config import Settings, get_settings
from app.models.sync import SyncReport
from app.services.deduplicator import Deduplicator
from app.services.garmin_client import GarminClient
from app.services.mapper import WithingsToGarminMapper
from app.services.report_builder import ReportBuilder
from app.services.sync_engine import SyncEngine
from app.services.withings_auth import WithingsAuthService
from app.services.withings_client import WithingsClient
from app.services.withings_parser import WithingsParser
from app.storage.sync_store import SyncStore
from app.storage.token_store import TokenStore
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

router = APIRouter(prefix="/api/sync", tags=["sync"])


def _build_engine(settings: Settings) -> SyncEngine:
    token_store = TokenStore(settings.resolved_data_dir)
    sync_store = SyncStore(settings.resolved_data_dir)
    auth = WithingsAuthService(settings, token_store)
    wclient = WithingsClient(auth, settings)
    parser = WithingsParser(settings)
    mapper = WithingsToGarminMapper(settings)
    garmin = GarminClient(settings)
    dedup = Deduplicator(settings, sync_store)
    report = ReportBuilder(settings)
    return SyncEngine(settings, auth, wclient, parser, mapper, garmin, dedup, sync_store, report)


class SyncRequest(BaseModel):
    """Request body for POST /api/sync/run."""

    start_date: str
    end_date: str
    timezone: str | None = None


@router.post("/run", response_model=SyncReport)
async def run_sync(
    body: SyncRequest,
    settings: Settings = Depends(get_settings),
) -> SyncReport:
    """Run the guarded Withings→Garmin synchronization."""
    engine = _build_engine(settings)
    try:
        return await engine.run_sync(
            start_date=body.start_date,
            end_date=body.end_date,
            tz_name=body.timezone,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("", response_model=SyncReport)
async def run_sync_short(
    body: SyncRequest,
    settings: Settings = Depends(get_settings),
) -> SyncReport:
    """Alias for clients that post directly to /api/sync."""
    return await run_sync(body, settings)


@router.get("/reports/latest")
def latest_report(settings: Settings = Depends(get_settings)) -> dict:
    """Return the most recent sync report."""
    report_builder = ReportBuilder(settings)
    report = report_builder.load_latest()
    if report is None:
        raise HTTPException(status_code=404, detail="No sync reports found.")
    return report


@router.get("/reports")
def list_reports(settings: Settings = Depends(get_settings)) -> list[dict]:
    """List available sync reports."""
    report_builder = ReportBuilder(settings)
    return report_builder.list_reports()
