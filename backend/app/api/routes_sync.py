"""Sync pipeline routes.

Endpoints:
  POST /api/sync/dry-run   — execute a dry-run with full report
  GET  /api/sync/reports/latest — retrieve the latest report

In v1, there is NO endpoint for actual Garmin writes.
"""

from app.config import Settings, get_settings
from app.models.sync import DryRunReport
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
    garmin = GarminClient(settings, use_mcp=False)
    dedup = Deduplicator(settings, sync_store)
    report = ReportBuilder(settings)
    return SyncEngine(settings, auth, wclient, parser, mapper, garmin, dedup, sync_store, report)


class DryRunRequest(BaseModel):
    """Request body for POST /api/sync/dry-run."""

    start_date: str
    end_date: str
    timezone: str | None = None


@router.post("/dry-run", response_model=DryRunReport)
async def dry_run(
    body: DryRunRequest,
    settings: Settings = Depends(get_settings),
) -> DryRunReport:
    """Run the full Withings→Garmin pipeline in dry-run mode.

    Fetches Withings data, parses, maps, deduplicates, and
    produces a detailed report. NO writes to Garmin.
    """
    engine = _build_engine(settings)
    try:
        report = await engine.run_dry_run(
            start_date=body.start_date,
            end_date=body.end_date,
            tz_name=body.timezone,
        )
        return report
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.get("/reports/latest")
def latest_report(
    settings: Settings = Depends(get_settings),
) -> dict:
    """Return the most recent dry-run report."""
    report_builder = ReportBuilder(settings)
    report = report_builder.load_latest()
    if report is None:
        raise HTTPException(status_code=404, detail="No reports found. Run a dry-run first.")
    return report


@router.get("/reports")
def list_reports(
    settings: Settings = Depends(get_settings),
) -> list[dict]:
    """List all available dry-run reports."""
    report_builder = ReportBuilder(settings)
    return report_builder.list_reports()
