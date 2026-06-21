"""Read-only measurement preview and history endpoints.

These endpoints NEVER write to Garmin. They provide a structured
preview of Withings measurements and their planned Garmin mapping
for the Dashboard UI.
"""

from datetime import UTC, datetime, timedelta

from app.config import Settings, get_settings
from app.models.sync import (
    DecisionPreview,
    DedupPreview,
    FieldMappingEntry,
    MeasurementPreviewResponse,
    RecentMeasurementItem,
    RecentMeasurementsResponse,
)
from app.services.deduplicator import Deduplicator
from app.services.garmin_auth_service import GarminAuthService
from app.services.garmin_client import GarminClient
from app.services.mapper import WithingsToGarminMapper
from app.services.withings_auth import WithingsAuthService
from app.services.withings_client import WithingsClient
from app.services.withings_parser import WithingsParser
from app.storage.sync_store import SyncStore
from app.storage.token_store import TokenStore
from fastapi import APIRouter, Depends, HTTPException, Query

router = APIRouter(prefix="/api/measurements", tags=["measurements"])


def _build_services(settings: Settings) -> tuple:
    token_store = TokenStore(settings.resolved_data_dir)
    sync_store = SyncStore(settings.resolved_data_dir)
    auth = WithingsAuthService(settings, token_store)
    wclient = WithingsClient(auth, settings)
    parser = WithingsParser(settings)
    mapper = WithingsToGarminMapper(settings)
    garmin = GarminClient(settings)
    dedup = Deduplicator(settings, sync_store)
    return auth, wclient, parser, mapper, garmin, dedup, sync_store


def _fmt_val(value, unit: str = "") -> str | None:
    """Format a numeric value for display."""
    if value is None:
        return None
    if isinstance(value, float):
        s = f"{value:.1f}"
    else:
        s = str(value)
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
    ignored_reason = "Ignoré volontairement : conversion Withings kg vers Garmin % non validée"

    fields = [
        ("Date", _fmt_dt(measurement.measured_at_local), candidate.date.isoformat() if candidate else None, "will_sync" if candidate else "absent", ""),
        ("Poids", _fmt_val(measurement.weight_kg, "kg"), _fmt_val(candidate.weight, "kg") if candidate else None, "will_sync" if candidate and candidate.weight else "absent", ""),
        ("Masse grasse", _fmt_val(measurement.fat_percent, "%"), _fmt_val(candidate.percent_fat, "%") if candidate else None, "will_sync" if candidate and candidate.percent_fat else "absent", ""),
        ("Masse musculaire", _fmt_val(measurement.muscle_mass_kg, "kg"), _fmt_val(candidate.muscle_mass, "kg") if candidate else None, "will_sync" if candidate and candidate.muscle_mass else "absent", ""),
        ("Masse osseuse", _fmt_val(measurement.bone_mass_kg, "kg"), _fmt_val(candidate.bone_mass, "kg") if candidate else None, "will_sync" if candidate and candidate.bone_mass else "absent", ""),
        ("IMC", _fmt_val(measurement.bmi), _fmt_val(candidate.bmi) if candidate else None, "will_sync" if candidate and candidate.bmi else "absent", ""),
        ("Métabolisme basal", _fmt_val(measurement.basal_met, "kcal"), _fmt_val(candidate.basal_met, "kcal") if candidate else None, "will_sync" if candidate and candidate.basal_met else "absent", ""),
        ("Âge métabolique", _fmt_val(measurement.metabolic_age, "ans"), _fmt_val(candidate.metabolic_age, "ans") if candidate else None, "will_sync" if candidate and candidate.metabolic_age else "absent", ""),
        ("Graisse viscérale", _fmt_val(measurement.visceral_fat_rating), _fmt_val(candidate.visceral_fat_rating) if candidate else None, "will_sync" if candidate and candidate.visceral_fat_rating else "absent", ""),
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

    # Hydration is explicitly ignored
    if measurement.hydration_mass_kg is not None:
        mapping.append(
            FieldMappingEntry(
                label="Hydratation",
                withings_value=_fmt_val(measurement.hydration_mass_kg, "kg"),
                garmin_value=None,
                status="ignored",
                message=ignored_reason,
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
                    message=ignored_reason,
                )
            )

    return mapping


@router.get("/latest", response_model=MeasurementPreviewResponse)
async def get_latest_measurement_preview(
    days: int = Query(default=30, ge=1, le=365),
    settings: Settings = Depends(get_settings),
) -> MeasurementPreviewResponse:
    """Preview the latest Withings measurement and its planned Garmin mapping.

    This is a READ-ONLY endpoint. It NEVER writes to Garmin.
    """
    auth, wclient, parser, mapper, garmin, dedup, sync_store = _build_services(settings)

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

    # ── Fetch measurements from Withings ────────────────────────
    end_dt = datetime.now(UTC)
    start_dt = end_dt - timedelta(days=days)

    try:
        raw_groups = await wclient.get_measurements(start_dt, end_dt)
    except Exception as exc:
        return MeasurementPreviewResponse(
            status="error",
            withings={"connected": True, "error": str(exc)},
            garmin={"connected": True},
        )

    parsed = parser.parse_measure_groups(raw_groups)
    if not parsed:
        return MeasurementPreviewResponse(
            status="no_measurement",
            withings={"connected": True, "raw_groups": len(raw_groups)},
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
    dedup_disabled = existing_count < 0
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
    if dedup_status in ("duplicate_exact_or_near", "duplicate_body_composition", "already_synced_by_garminsync"):
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
            "raw_groups": len(raw_groups),
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


@router.get("/recent", response_model=RecentMeasurementsResponse)
async def get_recent_measurements(
    days: int = Query(default=30, ge=1, le=365),
    settings: Settings = Depends(get_settings),
) -> RecentMeasurementsResponse:
    """Return recent Withings measurements for the Dashboard sparkline.

    This is a READ-ONLY endpoint. It NEVER writes to Garmin.
    """
    auth, wclient, parser, _mapper, _garmin, _dedup, _sync_store = _build_services(settings)

    withings_status = await auth.check_connection()
    if not withings_status.get("connected"):
        raise HTTPException(
            status_code=400,
            detail="Withings non connecté : impossible de récupérer les mesures.",
        )

    end_dt = datetime.now(UTC)
    start_dt = end_dt - timedelta(days=days)

    try:
        raw_groups = await wclient.get_measurements(start_dt, end_dt)
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Erreur de récupération des mesures Withings : {exc}",
        ) from exc

    parsed = parser.parse_measure_groups(raw_groups)
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
