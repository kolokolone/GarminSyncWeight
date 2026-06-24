"""Controlled synchronization routes (including SSE streaming)."""

import json
from datetime import UTC, datetime, timedelta

from app.cache import get_cache
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


def _table_exists(conn, table: str) -> bool:
    """Return True if *table* exists in the database."""
    try:
        row = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
            (table,),
        ).fetchone()
        return row is not None
    except Exception:
        return False


@router.get("/stats")
def sync_stats(settings: Settings = Depends(get_settings)) -> dict:
    """Aggregated sync statistics from SQLite (cumulative across all attempts).

    Cached for 60s since data only changes during a sync.
    """
    cache = get_cache()
    cached = cache.get("sync_stats")
    if cached is not None:
        return cached
    sync_store = SyncStore(settings.resolved_data_dir)
    conn = sync_store.conn

    # ── Sync attempt totals ──────────────────────────────────────
    attempt_row = conn.execute(
        """SELECT
               COUNT(*)                                              AS total_attempts,
               SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END) AS successful_attempts,
               SUM(CASE WHEN status = 'failed'     THEN 1 ELSE 0 END) AS failed_attempts
           FROM sync_attempts"""
    ).fetchone()

    # ── Aggregate summary JSON from completed attempts ───────────
    rows = conn.execute(
        """SELECT summary_json FROM sync_attempts
           WHERE status = 'completed' AND summary_json IS NOT NULL
           ORDER BY started_at DESC"""
    ).fetchall()

    cumul = {
        "synced_count": 0,
        "skipped_existing_count": 0,
        "conflicts_count": 0,
        "invalid_count": 0,
        "failed_count": 0,
        "candidates_count": 0,
    }
    for row in rows:
        s = json.loads(row["summary_json"])
        cumul["synced_count"]            += s.get("synced_count", 0)
        cumul["skipped_existing_count"]  += s.get("skipped_existing_count", 0)
        cumul["conflicts_count"]         += s.get("conflicts_count", 0)
        cumul["invalid_count"]           += s.get("invalid_count", 0)
        cumul["failed_count"]            += s.get("failed_count", 0)
        cumul["candidates_count"]        += s.get("candidates_count", 0)

    # ── Latest report summary ────────────────────────────────────
    latest_summary = None
    if rows:
        latest_summary = json.loads(rows[0]["summary_json"])

    # ── Last sync timestamp ──────────────────────────────────────
    last_sync_row = conn.execute(
        """SELECT started_at FROM sync_attempts
           WHERE status = 'completed'
           ORDER BY started_at DESC LIMIT 1"""
    ).fetchone()

    # ── Daily breakdown (last 30 days) ───────────────────────────
    thirty_days_ago = (datetime.now(UTC) - timedelta(days=30)).isoformat()
    daily_rows = conn.execute(
        """SELECT DATE(created_at) AS day, status, COUNT(*) AS count
           FROM sync_events
           WHERE created_at >= ?
           GROUP BY DATE(created_at), status
           ORDER BY day ASC""",
        (thirty_days_ago,),
    ).fetchall()

    days_map: dict[str, dict[str, int]] = {}
    for row in daily_rows:
        day = row["day"]
        if day not in days_map:
            days_map[day] = {}
        days_map[day][row["status"]] = row["count"]

    daily_breakdown = [
        {"date": day, **statuses} for day, statuses in sorted(days_map.items())
    ]

    # ── sync_jobs stats (normalised table) ─────────────────────────
    jobs_row = conn.execute(
        """SELECT
               COUNT(*)                                              AS total_jobs,
               SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END) AS successful_jobs,
               SUM(CASE WHEN status = 'failed'     THEN 1 ELSE 0 END) AS failed_jobs,
               SUM(candidates_synced)                                AS total_synced,
               SUM(candidates_skipped)                               AS total_skipped,
               SUM(candidates_conflict)                              AS total_conflicts,
               SUM(candidates_invalid)                               AS total_invalid,
               SUM(candidates_failed)                                AS total_failed
           FROM sync_jobs"""
    ).fetchone() if _table_exists(conn, "sync_jobs") else None

    # ── sync_candidates daily breakdown ────────────────────────────
    cand_daily = []
    if _table_exists(conn, "sync_candidates"):
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
            day = row["day"]
            if day not in cand_map:
                cand_map[day] = {}
            cand_map[day][row["decision"] or "unknown"] = row["count"]
        cand_daily = [
            {"date": day, **statuses} for day, statuses in sorted(cand_map.items())
        ]

    result = {
        "total_attempts":         attempt_row["total_attempts"],
        "successful_attempts":    attempt_row["successful_attempts"],
        "failed_attempts":        attempt_row["failed_attempts"],
        "cumulative":             cumul,
        "latest_summary":         latest_summary,
        "last_sync":              last_sync_row["started_at"] if last_sync_row else None,
        "daily_breakdown":        daily_breakdown,
    }
    # Append normalised-table stats if available
    if jobs_row:
        result["sync_jobs"] = {
            "total_jobs":         jobs_row["total_jobs"],
            "successful_jobs":    jobs_row["successful_jobs"],
            "failed_jobs":        jobs_row["failed_jobs"],
            "total_synced":       jobs_row["total_synced"] or 0,
            "total_skipped":      jobs_row["total_skipped"] or 0,
            "total_conflicts":    jobs_row["total_conflicts"] or 0,
            "total_invalid":      jobs_row["total_invalid"] or 0,
            "total_failed":       jobs_row["total_failed"] or 0,
        }
    if cand_daily:
        result["candidates_daily_breakdown"] = cand_daily
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
        import json
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
