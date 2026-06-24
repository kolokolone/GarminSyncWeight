"""Read-only measurement preview and history endpoints.

These endpoints NEVER write to Garmin. They provide a structured
preview of Withings measurements and their planned Garmin mapping
for the Dashboard UI.
"""

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

from app.cache import get_cache, stale_while_revalidate
from app.config import Settings, get_settings
from app.models.withings import BodyCompositionMeasurement
from app.models.sync import (
    DecisionPreview,
    DedupPreview,
    FieldMappingEntry,
    HistoryMeasurementItem,
    HistoryMeasurementsResponse,
    HistoryMeasurementsSummary,
    MeasurementPreviewResponse,
    RecentMeasurementItem,
    RecentMeasurementsResponse,
)
from app.services.deduplicator import Deduplicator
from app.services.garmin_client import GarminClient
from app.services.mapper import WithingsToGarminMapper
from app.services.withings_auth import WithingsAuthService
from app.services.withings_client import WithingsClient
from app.services.withings_parser import WithingsParser
from app.storage.measurement_store import WithingsMeasurementStore
from app.storage.sync_store import SyncStore
from app.storage.token_store import TokenStore
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api/measurements", tags=["measurements"])


def _build_services(settings: Settings) -> tuple:
    token_store = TokenStore(settings.resolved_data_dir)
    sync_store = SyncStore(settings.resolved_data_dir)
    meas_store = WithingsMeasurementStore(settings.resolved_data_dir)
    auth = WithingsAuthService(settings, token_store)
    wclient = WithingsClient(auth, settings)
    parser = WithingsParser(settings)
    mapper = WithingsToGarminMapper(settings)
    garmin = GarminClient(settings)
    dedup = Deduplicator(settings, sync_store)
    return auth, wclient, parser, mapper, garmin, dedup, sync_store, meas_store


def _fmt_val(value, unit: str = "") -> str | None:
    """Format a numeric value for display."""
    if value is None:
        return None
    s = f"{value:.1f}" if isinstance(value, float) else str(value)
    return f"{s} {unit}".strip() if unit else s


def _fmt_dt(dt) -> str:
    """Format a datetime for display."""
    if dt is None:
        return ""
    if isinstance(dt, str):
        return dt
    return dt.strftime("%d/%m/%Y · %H:%M")


def _build_field_mapping(
    measurement,
    candidate,
) -> list[FieldMappingEntry]:
    """Build the field mapping table from a measurement and its candidate."""
    mapping: list[FieldMappingEntry] = []

    def _row(label, wval, gval, status, msg):
        """One row of the field mapping."""
        return (label, wval, gval, status, msg)

    def _sync_status(val, cond):
        """'will_sync' if cond else 'absent'."""
        return "will_sync" if cond else "absent"

    c = candidate
    fields = [
        _row("Date", _fmt_dt(measurement.measured_at_local),
             c.date.isoformat() if c else None,
             "will_sync" if c else "absent", ""),
        _row("Poids", _fmt_val(measurement.weight_kg, "kg"),
             _fmt_val(c.weight, "kg") if c else None,
             _sync_status(c, c and c.weight), ""),
        _row("Masse grasse", _fmt_val(measurement.fat_percent, "%"),
             _fmt_val(c.percent_fat, "%") if c else None,
             _sync_status(c, c and c.percent_fat), ""),
        _row("Masse musculaire", _fmt_val(measurement.muscle_mass_kg, "kg"),
             _fmt_val(c.muscle_mass, "kg") if c else None,
             _sync_status(c, c and c.muscle_mass), ""),
        _row("Masse osseuse", _fmt_val(measurement.bone_mass_kg, "kg"),
             _fmt_val(c.bone_mass, "kg") if c else None,
             _sync_status(c, c and c.bone_mass), ""),
        _row("IMC", _fmt_val(measurement.bmi),
             _fmt_val(c.bmi) if c else None,
             _sync_status(c, c and c.bmi), ""),
    ]

    for label, withings_val, garmin_val, status, msg in fields:
        if not withings_val and not garmin_val:
            status = "absent"
            msg = "Non mesuré"
        mapping.append(
            FieldMappingEntry(
                label=label,
                withings_value=withings_val,
                garmin_value=garmin_val,
                status=status,
                message=msg,
            )
        )

    # Hydration
    if measurement.hydration_mass_kg is not None:
        if measurement.weight_kg is not None and measurement.weight_kg > 0:
            pct = (measurement.hydration_mass_kg / measurement.weight_kg) * 100
            mapping.append(
                FieldMappingEntry(
                    label="Hydratation",
                    withings_value=_fmt_val(round(pct, 1), "%"),
                    garmin_value=_fmt_val(round(pct, 1), "%"),
                    status="calculated",
                    message="Calculé (masse eau / poids)",
                )
            )
        else:
            mapping.append(
                FieldMappingEntry(
                    label="Hydratation",
                    withings_value=_fmt_val(measurement.hydration_mass_kg, "kg"),
                    garmin_value=None,
                    status="ignored",
                    message="Poids manquant, conversion kg→% impossible",
                )
            )

    # Fields from candidate warnings / ignored
    if candidate:
        for field_name, field_val in (candidate.ignored_fields or {}).items():
                mapping.append(
                FieldMappingEntry(
                    label=field_name.replace("_", " ").title(),
                    withings_value=_fmt_val(field_val),
                    garmin_value=None,
                    status="ignored",
                    message="Ignoré volontairement",
                )
            )

    return mapping


async def _fetch_withings_measurements(
    wclient: WithingsClient,
    parser: WithingsParser,
    store: WithingsMeasurementStore,
    start_dt: datetime,
    end_dt: datetime,
) -> tuple[list[BodyCompositionMeasurement], int]:
    """Get measurements — persistent store first, Withings API fallback.

    Returns ``(parsed_measurements, raw_groups_count)``.
    When served from the store *raw_groups_count* is the number of
    measurements returned (a best‑effort approximation).
    """
    start_date = start_dt.date()
    end_date = end_dt.date()
    if start_date <= end_date:
        parsed = store.get_measurements(start_date.isoformat(), end_date.isoformat())
        if parsed:
            return parsed, len(parsed)

    # Fallback to live API
    raw = await wclient.get_measurements(start_dt, end_dt)
    parsed = parser.parse_measure_groups(raw)
    if parsed:
        store.save_measurements(parsed)
    return parsed, len(raw)


async def _compute_latest_preview(
    days: int,
    settings: Settings,
) -> MeasurementPreviewResponse:
    """Full computation of the /latest preview (extracted for caching)."""
    auth, wclient, parser, mapper, garmin, dedup, sync_store, meas_store = _build_services(settings)

    # ── Check Withings ──────────────────────────────────────────
    withings_status = await auth.check_connection()
    if not withings_status.get("connected"):
        return MeasurementPreviewResponse(
            status="withings_not_connected",
            withings={"connected": False, "message": withings_status.get("message", "")},
            garmin={"connected": False, "message": ""},
        )

    # ── Check Garmin ────────────────────────────────────────────
    garmin_status = await garmin.check_connection()
    if not garmin_status.get("connected"):
        return MeasurementPreviewResponse(
            status="garmin_not_ready",
            withings={"connected": True, "message": "Withings connecté."},
            garmin={"connected": False, "message": garmin_status.get("message", "")},
        )

    # ── Fetch measurements (store‑first, API fallback) ──────────
    end_dt = datetime.now(UTC)
    start_dt = end_dt - timedelta(days=days)

    try:
        parsed, raw_groups_count = await _fetch_withings_measurements(
            wclient, parser, meas_store, start_dt, end_dt,
        )
    except Exception as exc:
        return MeasurementPreviewResponse(
            status="error",
            withings={"connected": True, "error": str(exc)},
            garmin={"connected": True},
        )

    if not parsed:
        return MeasurementPreviewResponse(
            status="no_measurement",
            withings={"connected": True, "raw_groups": raw_groups_count},
            garmin={"connected": True},
            technical={"lookback_days": days},
        )

    # Latest measurement
    latest = max(parsed, key=lambda m: m.measured_at_utc)

    # ── Map to Garmin ───────────────────────────────────────────
    candidate = mapper.map(latest)

    # ── Fetch existing Garmin data for dedup ────────────────────
    try:
        search_start = latest.garmin_date - timedelta(days=settings.garmin_lookback_days)
        search_end = latest.garmin_date + timedelta(days=settings.garmin_lookahead_days)
        garmin_weigh_ins = []
        current = search_start
        while current <= search_end:
            garmin_weigh_ins.extend(await garmin.get_daily_weigh_ins(current))
            current += timedelta(days=1)
        garmin_bc = await garmin.get_body_composition(search_start, search_end)
        existing_count = len(garmin_weigh_ins) + len(garmin_bc)
    except Exception:
        garmin_weigh_ins = []
        garmin_bc = []
        existing_count = -1

    # ── Dedup ───────────────────────────────────────────────────
    dedup_status = dedup.classify(candidate, garmin_weigh_ins, garmin_bc)

    # ── Build response ──────────────────────────────────────────
    device = latest.source_device_id or "Body Cardio+"
    latest_measurement_data = {
        "measured_at": latest.measured_at_local.isoformat() if latest.measured_at_local else None,
        "source": latest.source,
        "device": device,
        "weight_kg": float(latest.weight_kg) if latest.weight_kg else None,
        "fat_percent": float(latest.fat_percent) if latest.fat_percent else None,
        "muscle_mass_kg": float(latest.muscle_mass_kg) if latest.muscle_mass_kg else None,
        "bone_mass_kg": float(latest.bone_mass_kg) if latest.bone_mass_kg else None,
        "hydration_mass_kg": float(latest.hydration_mass_kg) if latest.hydration_mass_kg else None,
        "bmi": float(latest.bmi) if latest.bmi else None,
        "basal_metabolic_rate_kcal": float(latest.basal_met) if latest.basal_met else None,
        "metabolic_age": latest.metabolic_age,
        "visceral_fat_rating": latest.visceral_fat_rating,
    }

    # Garmin payload preview (what would be sent)
    garmin_payload = None
    if candidate:
        garmin_params = candidate.garmin_params()
        garmin_payload = {
            "method": candidate.garmin_write_method(),
            "date": candidate.date.isoformat(),
            "fields": garmin_params,
        }

    # Field mapping
    field_mapping = _build_field_mapping(latest, candidate)

    # Warnings
    warnings = list(candidate.mapping_warnings) if candidate else []
    if candidate and candidate.null_fields:
        for f in candidate.null_fields:
            label = f.replace("_", " ").title()
            if f not in ("percent_hydration", "visceral_fat_mass", "active_met", "physique_rating"):
                continue
            if label and f"null_fields: {f}" not in warnings:
                warnings.append(f"{label} : absent de la mesure Withings")

    # Dedup info
    dedup_map = {
        "new_candidate": ("new", "Aucune mesure Garmin proche détectée pour cette date."),
        "duplicate_exact_or_near": ("duplicate", "Mesure déjà présente dans Garmin (poids identique)."),
        "duplicate_body_composition": ("duplicate", "Composition corporelle déjà présente dans Garmin."),
        "possible_duplicate": ("duplicate", "Mesure Garmin proche détectée à vérifier."),
        "conflict_same_day": ("conflict", "Mesure Garmin différente le même jour."),
        "already_synced_by_garminsync": ("duplicate", "Déjà synchronisée via GarminSyncWeight."),
        "invalid_missing_weight": ("conflict", "Mesure Withings sans poids valide."),
        "invalid_outlier": ("conflict", "Poids aberrant (hors plage 20-300 kg)."),
    }
    dedup_status_str, dedup_msg = dedup_map.get(dedup_status, ("unchecked", "Non vérifié."))

    # Decision
    can_sync = dedup_status == "new_candidate"
    duplicate_stati = ("duplicate_exact_or_near", "duplicate_body_composition",
                       "already_synced_by_garminsync")
    if dedup_status in duplicate_stati:
        decision_msg = "Cette mesure semble déjà synchronisée."
        can_sync = False
    elif dedup_status in ("possible_duplicate", "conflict_same_day"):
        decision_msg = "Conflit détecté : vérifier avant d'écraser."
        can_sync = False
    elif dedup_status == "new_candidate":
        decision_msg = "Cette mesure peut être synchronisée."
        can_sync = True
    elif dedup_status in ("invalid_missing_weight", "invalid_outlier"):
        decision_msg = "Mesure invalide : poids manquant ou aberrant."
        can_sync = False
    else:
        decision_msg = "Non vérifié."
        can_sync = False

    return MeasurementPreviewResponse(
        status="ready",
        withings={
            "connected": True,
            "raw_groups": raw_groups_count,
            "parsed_count": len(parsed),
            "last_checked_at": datetime.now(UTC).isoformat(),
        },
        garmin={
            "connected": True,
            "write_available": True,
            "existing_count": existing_count,
            "last_checked_at": datetime.now(UTC).isoformat(),
        },
        latest_measurement=latest_measurement_data,
        garmin_payload_preview=garmin_payload,
        field_mapping=field_mapping,
        deduplication=DedupPreview(status=dedup_status_str, message=dedup_msg),
        decision=DecisionPreview(
            status="ready_to_sync" if can_sync else "blocked",
            can_sync=can_sync,
            message=decision_msg,
        ),
        warnings=warnings,
        technical={"lookback_days": days},
    )


@router.get("/latest", response_model=MeasurementPreviewResponse)
async def get_latest_measurement_preview(
    days: int = Query(default=30, ge=1, le=365),
    settings: Settings = Depends(get_settings),
) -> MeasurementPreviewResponse:
    """Preview the latest Withings measurement and its planned Garmin mapping.

    This is a READ-ONLY endpoint. It NEVER writes to Garmin.

    Results are cached with stale-while-revalidate (30s fresh, 5min stale).
    """
    cache_key = f"latest:{days}"

    async def _fetch():
        return await _compute_latest_preview(days, settings)

    result = await stale_while_revalidate(
        cache_key, _fetch, ttl=30.0, stale_ttl=300.0,
    )
    return result


@router.get("/recent", response_model=RecentMeasurementsResponse)
async def get_recent_measurements(
    days: int = Query(default=30, ge=1, le=365),
    settings: Settings = Depends(get_settings),
) -> RecentMeasurementsResponse:
    """Return recent Withings measurements for the Dashboard sparkline.

    This is a READ-ONLY endpoint. It NEVER writes to Garmin.
    """
    auth, wclient, parser, _mapper, _garmin, _dedup, _sync_store, meas_store = _build_services(settings)

    withings_status = await auth.check_connection()
    if not withings_status.get("connected"):
        raise HTTPException(
            status_code=400,
            detail="Withings non connecté : impossible de récupérer les mesures.",
        )

    end_dt = datetime.now(UTC)
    start_dt = end_dt - timedelta(days=days)

    try:
        parsed, _ = await _fetch_withings_measurements(
            wclient, parser, meas_store, start_dt, end_dt,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Erreur de récupération des mesures Withings : {exc}",
        ) from exc

    sorted_parsed = sorted(parsed, key=lambda m: m.measured_at_utc)

    items = [
        RecentMeasurementItem(
            measured_at=m.measured_at_local.isoformat() if m.measured_at_local else "",
            weight_kg=float(m.weight_kg) if m.weight_kg else None,
            fat_percent=float(m.fat_percent) if m.fat_percent else None,
        )
        for m in sorted_parsed
    ]

    return RecentMeasurementsResponse(items=items)


@router.get("/history", response_model=HistoryMeasurementsResponse)
async def get_measurement_history(
    days: int = Query(default=30, ge=1, le=365),
    include_garmin_status: bool = Query(default=True),
    settings: Settings = Depends(get_settings),
) -> HistoryMeasurementsResponse:
    """Return Withings measurements enriched with Garmin sync status.

    This endpoint fetches Withings measurements for the given period,
    maps them to Garmin candidates, then checks each against existing
    Garmin data (weigh-ins + body composition) and local sync history
    to determine real Garmin status.

    This is a READ-ONLY endpoint. It NEVER writes to Garmin.
    """
    auth, wclient, parser, mapper, garmin, dedup, sync_store, meas_store = _build_services(settings)

    withings_status = await auth.check_connection()
    if not withings_status.get("connected"):
        raise HTTPException(status_code=400, detail="Withings non connecté.")

    end_dt = datetime.now(UTC)
    start_dt = end_dt - timedelta(days=days)

    # ── Fetch Withings measurements (store‑first, API fallback) ─
    try:
        parsed, _ = await _fetch_withings_measurements(
            wclient, parser, meas_store, start_dt, end_dt,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Erreur de récupération des mesures Withings : {exc}",
        ) from exc
    if not parsed:
        return HistoryMeasurementsResponse(
            items=[],
            summary=HistoryMeasurementsSummary(
                count=0, checked_at=datetime.now(UTC).isoformat(),
            ),
        )

    # Sort descending: most recent first
    sorted_parsed = sorted(parsed, key=lambda m: m.measured_at_utc, reverse=True)

    # ── Map all to Garmin candidates ────────────────────────────
    candidates = []
    for m in sorted_parsed:
        try:
            c = mapper.map(m)
            candidates.append((m, c))
        except Exception:
            candidates.append((m, None))

    # ── Fetch Garmin data once (whole window) ───────────────────
    garmin_weigh_ins: list = []
    garmin_bc: list = []
    garmin_available = False
    if include_garmin_status:
        try:
            garmin_status_check = await garmin.check_connection()
            garmin_available = garmin_status_check.get("connected", False)
            if garmin_available:
                search_start = sorted_parsed[-1].garmin_date - timedelta(days=1)
                search_end = sorted_parsed[0].garmin_date + timedelta(days=1)
                current = search_start
                while current <= search_end:
                    garmin_weigh_ins.extend(await garmin.get_daily_weigh_ins(current))
                    current += timedelta(days=1)
                garmin_bc = await garmin.get_body_composition(search_start, search_end)
        except Exception:
            garmin_available = False

    # ── Build enriched items ────────────────────────────────────
    now_str = datetime.now(UTC).isoformat()
    items: list[HistoryMeasurementItem] = []
    counts = {"new": 0, "already_synced": 0, "conflict": 0, "failed": 0}

    for measurement, candidate in candidates:
        item = HistoryMeasurementItem(
            measured_at_local=(
                measurement.measured_at_local.isoformat()
                if measurement.measured_at_local else ""
            ),
            date=measurement.garmin_date.isoformat(),
            weight_kg=float(measurement.weight_kg) if measurement.weight_kg else None,
            fat_percent=float(measurement.fat_percent) if measurement.fat_percent else None,
            source_measure_group_id=measurement.source_measure_group_id,
            garmin_status="unchecked",
            decision="unchecked",
        )

        if candidate and garmin_available:
            dedup_status = dedup.classify(candidate, garmin_weigh_ins, garmin_bc)

            # Map dedup_status → garmin_status
            status_map = {
                "new_candidate": "new",
                "duplicate_exact_or_near": "already_present",
                "duplicate_body_composition": "already_present",
                "possible_duplicate": "possible_duplicate",
                "conflict_same_day": "conflict_same_day",
                "already_synced_by_garminsync": "already_synced_by_garminsync",
                "invalid_missing_weight": "failed",
                "invalid_outlier": "failed",
            }
            item.garmin_status = status_map.get(dedup_status, "unchecked")

            # Map dedup_status → decision
            duplicate_decisions = (
                "duplicate_exact_or_near", "duplicate_body_composition",
                "already_synced_by_garminsync",
            )
            conflict_decisions = ("possible_duplicate", "conflict_same_day")
            invalid_decisions = ("invalid_missing_weight", "invalid_outlier")

            if dedup_status == "new_candidate":
                item.decision = "ready_to_sync"
                counts["new"] += 1
            elif dedup_status in duplicate_decisions:
                item.decision = "already_synced"
                counts["already_synced"] += 1
            elif dedup_status in conflict_decisions:
                item.decision = "conflict"
                counts["conflict"] += 1
            elif dedup_status in invalid_decisions:
                item.decision = "failed"
                counts["failed"] += 1
            else:
                item.decision = "unchecked"

            # Check sync store for actual sync outcome
            if candidate.idempotency_key:
                cand = sync_store.get_candidate_by_key(candidate.idempotency_key)
                if cand:
                    item.sync_event_status = cand.get("decision")
                    item.last_error = cand.get("error_message")

            item.warning_count = len(candidate.mapping_warnings or [])

        elif candidate and not garmin_available:
            item.garmin_status = "unchecked"
            item.decision = "unchecked"

        items.append(item)

    return HistoryMeasurementsResponse(
        items=items,
        summary=HistoryMeasurementsSummary(
            count=len(items),
            new_count=counts["new"],
            already_synced_count=counts["already_synced"],
            conflict_count=counts["conflict"],
            failed_count=counts["failed"],
            checked_at=now_str,
        ),
    )


# ── Manual measurement ──────────────────────────────────────────

_MANUAL_FILE = "manual_measurements.json"


def _manual_path(settings: Settings) -> Path:
    return settings.resolved_data_dir / _MANUAL_FILE


def _load_manual(settings: Settings) -> list[dict]:
    p = _manual_path(settings)
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            return []
    return []


def _save_manual(settings: Settings, data: list[dict]) -> None:
    _manual_path(settings).write_text(
        json.dumps(data, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )


class ManualMeasurementRequest(BaseModel):
    """Request body for POST /api/measurements/manual."""

    date: str = Field(..., description="Date YYYY-MM-DD")
    weight_kg: float | None = Field(default=None, ge=20, le=300)
    fat_percent: float | None = Field(default=None, ge=5, le=70)
    muscle_mass_kg: float | None = None
    bone_mass_kg: float | None = None
    note: str | None = None


@router.post("/manual")
async def add_manual_measurement(
    body: ManualMeasurementRequest,
    settings: Settings = Depends(get_settings),
) -> dict:
    """Add a manual weight measurement (stored locally)."""
    settings.ensure_directories()

    manual = _load_manual(settings)
    entry = {
        "id": len(manual) + 1,
        "date": body.date,
        "weight_kg": body.weight_kg,
        "fat_percent": body.fat_percent,
        "muscle_mass_kg": body.muscle_mass_kg,
        "bone_mass_kg": body.bone_mass_kg,
        "note": body.note or "",
        "created_at": datetime.now(UTC).isoformat(),
    }
    manual.append(entry)
    _save_manual(settings, manual)
    return {"status": "ok", "entry": entry}


@router.get("/manual")
def list_manual_measurements(
    settings: Settings = Depends(get_settings),
) -> list[dict]:
    """List manually added measurements."""
    return _load_manual(settings)


@router.delete("/manual/{entry_id}")
def delete_manual_measurement(
    entry_id: int,
    settings: Settings = Depends(get_settings),
) -> dict:
    """Delete a manual measurement by ID."""
    manual = _load_manual(settings)
    before = len(manual)
    manual = [e for e in manual if e.get("id") != entry_id]
    if len(manual) == before:
        raise HTTPException(status_code=404, detail="Entrée non trouvée.")
    _save_manual(settings, manual)
    return {"status": "deleted"}
