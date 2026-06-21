"""Pydantic models for the controlled sync pipeline."""

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
    "synced",
    "skipped_existing",
    "skipped_conflict",
    "failed",
    "invalid",
]

GarminWriteMethod = Literal[
    "add_body_composition", "add_weigh_in_with_timestamps", "add_weigh_in", "none",
]


# ── Sync report models ───────────────────────────────────────────


class SyncCandidate(BaseModel):
    """One candidate in a controlled sync report."""

    date: str
    measured_at_local: str | None = None
    source_measure_group_id: str | None = None
    mapped_fields: dict[str, Any] = {}
    ignored_fields: dict[str, Any] = {}
    null_fields: list[str] = []
    warnings: list[str] = []
    dedup_status: str = "unknown"
    decision: SyncEventStatus = "invalid"
    reason: str = ""
    garmin_call: dict[str, Any] = {}
    garmin_response: dict[str, Any] | None = None
    error_message: str | None = None
    idempotency_key: str = ""


class SyncSummary(BaseModel):
    """Summary statistics for a controlled sync report."""

    withings_raw_count: int = 0
    withings_parsed_count: int = 0
    garmin_existing_count: int = 0
    candidates_count: int = 0
    synced_count: int = 0
    skipped_existing_count: int = 0
    conflicts_count: int = 0
    invalid_count: int = 0
    failed_count: int = 0
    warnings_count: int = 0


class SyncReport(BaseModel):
    """Complete controlled sync report."""

    mode: str = "sync"
    period: dict[str, str] = {}
    prerequisites: dict[str, Any] = {}
    withings: dict[str, Any] = {}
    garmin: dict[str, Any] = {}
    candidates: list[SyncCandidate] = []
    summary: SyncSummary = SyncSummary()


# ── API response models ──────────────────────────────────────────


class StatusResponse(BaseModel):
    """Response from GET /api/status."""

    app_name: str = "GarminSyncWeight"
    version: str = ""
    state: Literal["not_configured", "needs_auth", "ready", "degraded", "error"] = "not_configured"
    message: str = ""
    withings_configured: bool = False
    withings_token_present: bool = False
    withings_connection_state: str = "unknown"
    garmin_connection_state: str = "unknown"
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


# ── Measurement preview models ────────────────────────────────────


class FieldMappingEntry(BaseModel):
    """One row in the Withings→Garmin field mapping table."""

    label: str
    withings_value: str | None = None
    garmin_value: str | None = None
    status: str = "unknown"  # will_sync | calculated | ignored | absent | conflict | unsupported
    message: str = ""


class DedupPreview(BaseModel):
    """Deduplication preview for a measurement."""

    status: str = "unknown"  # new | duplicate | conflict | unchecked
    message: str = ""


class DecisionPreview(BaseModel):
    """Sync decision preview."""

    status: str = "unknown"
    can_sync: bool = False
    message: str = ""


class MeasurementPreviewResponse(BaseModel):
    """Read-only preview of the latest Withings measurement and its Garmin mapping.

    This endpoint NEVER writes to Garmin. It is a pure read-only preview.
    """

    # ready | withings_not_connected | garmin_not_ready | no_measurement | error
    status: str = "error"
    withings: dict[str, Any] = {}
    garmin: dict[str, Any] = {}
    latest_measurement: dict[str, Any] | None = None
    garmin_payload_preview: dict[str, Any] | None = None
    field_mapping: list[FieldMappingEntry] = []
    deduplication: DedupPreview = DedupPreview()
    decision: DecisionPreview = DecisionPreview()
    warnings: list[str] = []
    technical: dict[str, Any] = {}


class RecentMeasurementItem(BaseModel):
    """One item in the /api/measurements/recent response."""

    measured_at: str = ""
    weight_kg: float | None = None
    fat_percent: float | None = None


class RecentMeasurementsResponse(BaseModel):
    """Response from GET /api/measurements/recent."""

    items: list[RecentMeasurementItem] = []
