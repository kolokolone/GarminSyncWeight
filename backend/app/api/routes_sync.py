"""Controlled synchronization routes (including SSE streaming)."""

import json
from datetime import UTC, datetime, timedelta

from app.cache import get_cache
from app.config import Settings, get_settings
from app.dependencies import verify_admin_token
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
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
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
    _admin: None = Depends(verify_admin_token),
) -> SyncReport:
    """Run the guarded Withings→Garmin synchronization."""
    engine = _build_engine(settings)
    try:
        report = await engine.run_sync(
            start_date=body.start_date,
            end_date=body.end_date,
            tz_name=body.timezone,
        )
        # Invalidate cache after successful sync so next read is fresh
        get_cache().invalidate_all()
        return report
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("", response_model=SyncReport)
async def run_sync_short(
    body: SyncRequest,
    settings: Settings = Depends(get_settings),
    _admin: None = Depends(verify_admin_token),
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


@router.get("/stats")
def sync_stats(settings: Settings = Depends(get_settings)) -> dict:
    """Aggregated sync statistics from SQLite (cumulative across all jobs).

    Cached for 60s since data only changes during a sync.
    """
    cache = get_cache()
    cached = cache.get("sync_stats")
    if cached is not None:
        return cached
    sync_store = SyncStore(settings.resolved_data_dir)
    conn = sync_store.conn

    # ── sync_jobs aggregations ──────────────────────────────────────
    jobs_row = conn.execute(
        """SELECT
               COUNT(*)                                              AS total_jobs,
               SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END) AS successful_jobs,
               SUM(CASE WHEN status = 'failed'     THEN 1 ELSE 0 END) AS failed_jobs,
               SUM(candidates_synced)                                AS total_synced,
               SUM(candidates_skipped)                               AS total_skipped,
               SUM(candidates_conflict)                              AS total_conflicts,
               SUM(candidates_invalid)                               AS total_invalid,
               SUM(candidates_failed)                                AS total_failed,
               SUM(candidates_total)                                 AS total_candidates,
               MAX(started_at)                                       AS last_sync_at
           FROM sync_jobs"""
    ).fetchone()

    # ── sync_candidates daily breakdown (last 30 days) ─────────────
    thirty_days_ago = (datetime.now(UTC) - timedelta(days=30)).isoformat()
    cand_rows = conn.execute(
        """SELECT DATE(created_at) AS day, decision, COUNT(*) AS count
           FROM sync_candidates
           WHERE created_at >= ?
           GROUP BY DATE(created_at), decision
           ORDER BY day ASC""",
        (thirty_days_ago,),
    ).fetchall()
    cand_map: dict[str, dict[str, int]] = {}
    for row in cand_rows:
        d = row["day"]
        if d not in cand_map:
            cand_map[d] = {}
        cand_map[d][row["decision"] or "unknown"] = row["count"]
    candidates_daily = [
        {"date": day, **statuses} for day, statuses in sorted(cand_map.items())
    ]

    result = {
        "total_jobs":               jobs_row["total_jobs"] or 0,
        "successful_jobs":          jobs_row["successful_jobs"] or 0,
        "failed_jobs":              jobs_row["failed_jobs"] or 0,
        "total_candidates":         jobs_row["total_candidates"] or 0,
        "total_synced":             jobs_row["total_synced"] or 0,
        "total_skipped":            jobs_row["total_skipped"] or 0,
        "total_conflicts":          jobs_row["total_conflicts"] or 0,
        "total_invalid":            jobs_row["total_invalid"] or 0,
        "total_failed":             jobs_row["total_failed"] or 0,
        "last_sync":                jobs_row["last_sync_at"],
        "candidates_daily_breakdown": candidates_daily,
    }
    cache.set("sync_stats", result, ttl_seconds=60)
    return result


# ── SSE streaming endpoint ──────────────────────────────────────

async def _sse_sync_generator(
    start_date: str, end_date: str, tz_name: str | None, settings: Settings,
):
    """Async generator that runs sync and yields SSE `data:` lines."""
    engine = _build_engine(settings)
    lines: list[str] = []

    def on_progress(payload: str) -> None:
        lines.append(f"data: {payload}\n\n")

    try:
        report = await engine.run_sync(
            start_date=start_date,
            end_date=end_date,
            tz_name=tz_name,
            progress_callback=on_progress,
        )
        # After streaming, send the full report as a final event
        payload = json.dumps({"type": "report", "report": report.model_dump(mode="json")})
        lines.append(f"data: {payload}\n\n")
    except ValueError as exc:
        lines.append(f"data: {json.dumps({'type': 'error', 'message': str(exc)})}\n\n")
    except RuntimeError as exc:
        lines.append(f"data: {json.dumps({'type': 'error', 'message': str(exc)})}\n\n")
    except Exception as exc:
        err = json.dumps({"type": "error", "message": f"Erreur interne: {exc}"})
        lines.append(f"data: {err}\n\n")
    finally:
        # Invalidate cache after sync attempt
        get_cache().invalidate_all()

    for line in lines:
        yield line


@router.get("/stream")
async def sync_stream(
    start_date: str = Query(..., description="Start date YYYY-MM-DD"),
    end_date: str = Query(..., description="End date YYYY-MM-DD"),
    timezone: str | None = Query(default=None, description="IANA timezone name"),
    settings: Settings = Depends(get_settings),
    _admin: None = Depends(verify_admin_token),
) -> StreamingResponse:
    """SSE endpoint: runs sync and streams progress events in real-time.

    Events:
      - ``{"type":"start", ...}``
      - ``{"type":"parsed", ...}``
      - ``{"type":"garmin_fetched", ...}``
      - ``{"type":"candidate", ...}`` — one per measurement
      - ``{"type":"complete", ...}``
      - ``{"type":"error", ...}``
      - ``{"type":"report", "report": {...}}`` — final SyncReport
    """
    return StreamingResponse(
        _sse_sync_generator(start_date, end_date, timezone, settings),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
