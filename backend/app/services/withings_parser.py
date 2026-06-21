"""Parser for raw Withings ``getmeas`` API responses.

Converts the raw JSON structure into the canonical
``BodyCompositionMeasurement`` model.
"""

from datetime import UTC, datetime, timezone
from decimal import Decimal
from typing import Any

from app.config import Settings
from app.models.withings import BodyCompositionMeasurement

_logger = None


def _log() -> Any:
    global _logger
    if _logger is None:
        from app.logging_config import get_logger

        _logger = get_logger("withings")
    return _logger


# Withings measure type identifiers from the official Measure - Getmeas documentation.
MEASURE_TYPE_WEIGHT = 1  # kg
MEASURE_TYPE_FAT_FREE_MASS = 5  # kg
MEASURE_TYPE_FAT_RATIO = 6  # % (or ratio)
MEASURE_TYPE_FAT_MASS = 8  # kg
MEASURE_TYPE_MUSCLE_MASS = 76  # kg
MEASURE_TYPE_HYDRATION = 77  # kg water mass
MEASURE_TYPE_BONE_MASS = 88  # kg
MEASURE_TYPE_VISCERAL_FAT = 170  # unitless/rating-like value
MEASURE_TYPE_BASAL_MET = 226  # kcal
MEASURE_TYPE_METABOLIC_AGE = 227  # years


class WithingsParser:
    """Parses raw Withings measure groups into canonical measurements."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def parse_measure_groups(
        self,
        raw_groups: list[dict[str, Any]],
    ) -> list[BodyCompositionMeasurement]:
        """Parse a list of raw Withings measure groups.

        Each group can contain multiple measure types (weight, fat %, etc.).
        Groups are merged by ``grpid`` into a single measurement.
        """
        measurements: list[BodyCompositionMeasurement] = []
        for group in raw_groups:
            try:
                measurement = self._parse_single_group(group)
                if measurement is not None:
                    measurements.append(measurement)
            except Exception as exc:
                _log().warning("Failed to parse measure group %s: %s", group.get("grpid"), exc)

        _log().info("Parsed %d measurements from %d raw groups", len(measurements), len(raw_groups))
        return measurements

    def _parse_single_group(self, group: dict[str, Any]) -> BodyCompositionMeasurement | None:
        """Parse a single measure group into a BodyCompositionMeasurement."""
        raw_measures = group.get("measures", [])
        if not raw_measures:
            return None

        # ── Timestamp handling ─────────────────────────────────
        grpid = str(group.get("grpid", ""))
        raw_date = group.get("date")
        created_ts = group.get("created")

        # Prefer ``created``, fallback to ``date``
        ts = created_ts or raw_date
        if ts is None:
            _log().warning("Measure group %s has no timestamp — skipping", grpid)
            return None

        try:
            dt_utc = datetime.fromtimestamp(int(ts), tz=UTC)
        except (ValueError, OSError) as exc:
            _log().warning("Invalid timestamp %s in group %s: %s", ts, grpid, exc)
            return None

        # Derive local date using configured timezone
        tz_str = self._settings.app_timezone
        local_offset = self._get_utc_offset(tz_str)
        dt_local = dt_utc.astimezone(local_offset)
        garmin_date = dt_local.date()

        # ── Device & attribution ───────────────────────────────
        device_id = str(group.get("deviceid", "")) if group.get("deviceid") else None
        # ── Parse individual measures ──────────────────────────
        parsed: dict[int, Decimal] = {}
        for m in raw_measures:
            measure_type = m.get("type")
            value = m.get("value", 0)
            unit = m.get("unit", 0)
            real_value = Decimal(str(value)) * (Decimal(10) ** int(unit))
            parsed[int(measure_type)] = real_value

        # ── Build canonical model ──────────────────────────────
        warnings: list[str] = []
        weight_kg = parsed.get(MEASURE_TYPE_WEIGHT)
        fat_free_mass_kg = parsed.get(MEASURE_TYPE_FAT_FREE_MASS)
        fat_percent = parsed.get(MEASURE_TYPE_FAT_RATIO)
        fat_mass_kg = parsed.get(MEASURE_TYPE_FAT_MASS)
        muscle_mass_kg = parsed.get(MEASURE_TYPE_MUSCLE_MASS)
        hydration_mass_kg = parsed.get(MEASURE_TYPE_HYDRATION)
        bone_mass_kg = parsed.get(MEASURE_TYPE_BONE_MASS)
        visceral_fat = parsed.get(MEASURE_TYPE_VISCERAL_FAT)
        basal_met = parsed.get(MEASURE_TYPE_BASAL_MET)
        metabolic_age = parsed.get(MEASURE_TYPE_METABOLIC_AGE)

        # BMI — only if height is explicitly configured
        bmi: Decimal | None = None
        if self._settings.user_height_m is not None and weight_kg is not None:
            height = Decimal(str(self._settings.user_height_m))
            if height > 0:
                bmi = weight_kg / (height * height)
                bmi = bmi.quantize(Decimal("0.1"))

        # Hydration percent is NOT automatically computed from kg
        if hydration_mass_kg is not None:
            warnings.append(
                "hydration_mass_kg provided but percent_hydration not computed "
                "— conversion formula not validated"
            )

        # Log which measure types were found and which were ignored
        found_types = set(parsed.keys())
        known_types = {
            MEASURE_TYPE_WEIGHT,
            MEASURE_TYPE_FAT_FREE_MASS,
            MEASURE_TYPE_FAT_RATIO,
            MEASURE_TYPE_FAT_MASS,
            MEASURE_TYPE_MUSCLE_MASS,
            MEASURE_TYPE_HYDRATION,
            MEASURE_TYPE_BONE_MASS,
            MEASURE_TYPE_VISCERAL_FAT,
            MEASURE_TYPE_BASAL_MET,
            MEASURE_TYPE_METABOLIC_AGE,
        }
        unknown = found_types - known_types
        if unknown:
            warnings.append(f"Unknown measure types ignored: {sorted(unknown)}")

        return BodyCompositionMeasurement(
            source_measure_group_id=grpid or None,
            source_device_id=device_id,
            measured_at_utc=dt_utc,
            measured_at_local=dt_local,
            garmin_date=garmin_date,
            weight_kg=weight_kg,
            fat_percent=fat_percent,
            fat_mass_kg=fat_mass_kg,
            fat_free_mass_kg=fat_free_mass_kg,
            muscle_mass_kg=muscle_mass_kg,
            bone_mass_kg=bone_mass_kg,
            hydration_mass_kg=hydration_mass_kg,
            hydration_percent=None,
            bmi=bmi,
            visceral_fat_rating=int(visceral_fat) if visceral_fat is not None else None,
            basal_met=basal_met,
            metabolic_age=int(metabolic_age) if metabolic_age is not None else None,
            raw={"group": group, "parsed_measures": {str(k): str(v) for k, v in parsed.items()}},
            warnings=warnings,
        )

    @staticmethod
    def _get_utc_offset(tz_name: str) -> timezone:
        """Compute a UTC offset for a named timezone.

        This is a simplified offset for date derivation.
        For production, consider using ``zoneinfo`` (Python 3.9+).
        """
        try:
            import zoneinfo
            tz = zoneinfo.ZoneInfo(tz_name)
            return tz
        except (ImportError, KeyError, TypeError):
            _log().warning("Timezone '%s' not available, falling back to UTC", tz_name)
            return UTC
