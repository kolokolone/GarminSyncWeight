"""Pydantic models for sync pipeline status, reports, and events."""

from typing import Any, Literal

from pydantic import BaseModel

# ── Sync event status constants ──────────────────────────────────

DedupStatus = Literal[
    "new_candidate",
    "duplicate_exact_or_near",
    "possible_duplicate",
    "duplicate_body_composition",
    "conflict_same_day",
    "invalid_missing_weight",
    "invalid_date",
    "invalid_outlier",
    "already_synced_by_garminsync",
]

SyncEventStatus = Literal[
    "dry_run_new_candidate",
    "dry_run_duplicate",
    "dry_run_possible_duplicate",
    "dry_run_conflict",
    "dry_run_invalid",
    "written",
    "skipped_duplicate",
    "skipped_conflict",
    "skipped_invalid",
    "write_failed",
]

GarminWriteMethod = Literal[
    "add_body_composition", "add_weigh_in_with_timestamps", "add_weigh_in", "none",
]


# ── Dry-run report models ────────────────────────────────────────


class DryRunCandidate(BaseModel):
    """One candidate in a dry-run report."""

    date: str
    measured_at_local: str | None = None
    source_measure_group_id: str | None = None
    mapped_fields: dict[str, Any] = {}
    ignored_fields: dict[str, Any] = {}
    null_fields: list[str] = []
    warnings: list[str] = []
    dedup_status: str = "unknown"
    decision: Literal["would_write", "skip"] = "skip"
    garmin_call: dict[str, Any] = {}
    idempotency_key: str = ""


class DryRunSummary(BaseModel):
    """Summary statistics for a dry-run report."""

    would_write_count: int = 0
    skipped_duplicates_count: int = 0
    possible_duplicates_count: int = 0
    conflicts_count: int = 0
    invalid_count: int = 0
    warnings_count: int = 0


class DryRunReport(BaseModel):
    """Complete dry-run report."""

    mode: str = "dry_run"
    period: dict[str, str] = {}
    withings: dict[str, Any] = {}
    garmin: dict[str, Any] = {}
    candidates: list[DryRunCandidate] = []
    summary: DryRunSummary = DryRunSummary()


# ── API response models ──────────────────────────────────────────


class StatusResponse(BaseModel):
    """Response from GET /api/status."""

    app_name: str = "GarminSyncWeight"
    version: str = ""
    state: Literal["not_configured", "needs_auth", "ready", "degraded", "error"] = "not_configured"
    message: str = ""
    withings_configured: bool = False
    withings_token_present: bool = False
    dry_run_default: bool = True
    write_enabled: bool = False
    last_sync: str | None = None
    last_report: str | None = None


class LogEntry(BaseModel):
    """A single log entry."""

    timestamp: str = ""
    level: str = ""
    logger: str = ""
    message: str = ""


class LogResult(BaseModel):
    """Response from GET /api/logs."""

    service: str
    lines: list[str]
    truncated: bool = False
