"""Mapper: Withings ``BodyCompositionMeasurement`` → Garmin ``BodyCompositionCandidate``.

The mapper is intentionally conservative: fields are mapped ONLY when
the Withings source is confirmed reliable. All uncertain fields remain
``None`` with an explanation in ``mapping_warnings``.
"""

from datetime import date
from decimal import Decimal
from typing import Any

from app.config import Settings
from app.models.garmin import GarminBodyCompositionCandidate
from app.models.withings import BodyCompositionMeasurement

_logger = None


def _log() -> Any:
    global _logger
    if _logger is None:
        from app.logging_config import get_logger

        _logger = get_logger("sync")
    return _logger


class WithingsToGarminMapper:
    """Conservative mapper from Withings measurements to Garmin candidates."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def map(self, measurement: BodyCompositionMeasurement) -> GarminBodyCompositionCandidate:
        """Map a single Withings measurement to a Garmin candidate.

        Audit fields (mapped_fields, ignored_fields, null_fields, warnings)
        are populated for transparency.
        """
        mapped: dict[str, Any] = {}
        ignored: dict[str, Any] = {}
        null_fields: list[str] = []
        warnings: list[str] = []

        # ── Date & idempotency ─────────────────────────────────
        garmin_date: date = measurement.garmin_date
        idempotency_key = self._build_idempotency_key(measurement)

        # ── Weight (certain) ───────────────────────────────────
        weight: Decimal | None = None
        if measurement.weight_kg is not None and measurement.weight_kg > 0:
            weight = measurement.weight_kg
            mapped["weight"] = float(weight)
        else:
            null_fields.append("weight")
            warnings.append("Weight missing or zero — core field")

        # ── Fat percent (likely compatible) ────────────────────
        fat_percent: Decimal | None = None
        if measurement.fat_percent is not None:
            if Decimal("2") <= measurement.fat_percent <= Decimal("75"):
                fat_percent = measurement.fat_percent
                mapped["percent_fat"] = float(fat_percent)
            else:
                warnings.append(
                    f"Fat percent {measurement.fat_percent}% "
                    "outside plausible range 2-75% — set to null"
                )
                null_fields.append("percent_fat")
        else:
            null_fields.append("percent_fat")

        # ── Bone mass (likely compatible) ──────────────────────
        bone_mass: Decimal | None = None
        if measurement.bone_mass_kg is not None:
            if measurement.bone_mass_kg > 0:
                bone_mass = measurement.bone_mass_kg
                mapped["bone_mass"] = float(bone_mass)
            else:
                warnings.append(f"Bone mass {measurement.bone_mass_kg} <= 0 — set to null")
                null_fields.append("bone_mass")
        else:
            null_fields.append("bone_mass")

        # ── Muscle mass (likely compatible) ────────────────────
        muscle_mass: Decimal | None = None
        if measurement.muscle_mass_kg is not None:
            if measurement.muscle_mass_kg > 0:
                muscle_mass = measurement.muscle_mass_kg
                mapped["muscle_mass"] = float(muscle_mass)
            else:
                warnings.append(f"Muscle mass {measurement.muscle_mass_kg} <= 0 — set to null")
                null_fields.append("muscle_mass")
        else:
            null_fields.append("muscle_mass")

        # ── BMI (calculated, height-dependent) ─────────────────
        bmi: Decimal | None = None
        if measurement.bmi is not None:
            bmi = measurement.bmi
            mapped["bmi"] = float(bmi)
        elif (
            self._settings.user_height_m is not None
            and measurement.weight_kg is not None
            and measurement.weight_kg > 0
        ):
            height = Decimal(str(self._settings.user_height_m))
            bmi = (measurement.weight_kg / (height * height)).quantize(Decimal("0.1"))
            mapped["bmi"] = float(bmi)
        else:
            null_fields.append("bmi")
            if self._settings.user_height_m is not None:
                warnings.append("BMI could not be calculated — check weight/height")

        # ── Hydration percent (explicitly null — no auto-conversion) ─
        percent_hydration: Decimal | None = None
        if measurement.hydration_mass_kg is not None:
            ignored["hydration_mass_kg"] = float(measurement.hydration_mass_kg)
            warnings.append(
                "Hydration provided in kg, not mapped to percent_hydration — "
                "conversion formula not validated. Set to null."
            )
        null_fields.append("percent_hydration")

        basal_met = None
        if measurement.basal_met is not None:
            basal_met = measurement.basal_met
            mapped["basal_met"] = float(basal_met)
        else:
            null_fields.append("basal_met")

        metabolic_age = None
        if measurement.metabolic_age is not None:
            metabolic_age = int(measurement.metabolic_age)
            mapped["metabolic_age"] = metabolic_age
        else:
            null_fields.append("metabolic_age")

        visceral_fat_rating = None
        if measurement.visceral_fat_rating is not None:
            visceral_fat_rating = int(measurement.visceral_fat_rating)
            mapped["visceral_fat_rating"] = visceral_fat_rating
        else:
            null_fields.append("visceral_fat_rating")

        # ── Fields that are not supported or not directly provided ──
        null_fields.extend(["visceral_fat_mass", "active_met", "physique_rating"])
        warnings.append(
            "visceral_fat_mass, active_met, physique_rating: "
            "no reliable Withings source — set to null"
        )

        # ── Combine all warnings from measurement ──────────────
        warnings.extend(measurement.warnings)

        candidate = GarminBodyCompositionCandidate(
            date=garmin_date,
            measured_at_local=measurement.measured_at_local,
            weight=weight,
            percent_fat=fat_percent,
            percent_hydration=percent_hydration,
            visceral_fat_mass=None,
            bone_mass=bone_mass,
            muscle_mass=muscle_mass,
            basal_met=basal_met,
            active_met=None,
            physique_rating=None,
            metabolic_age=metabolic_age,
            visceral_fat_rating=visceral_fat_rating,
            bmi=bmi,
            source=measurement.source,
            source_measure_group_id=measurement.source_measure_group_id,
            source_device_id=measurement.source_device_id,
            idempotency_key=idempotency_key,
            mapped_fields=mapped,
            ignored_fields=ignored,
            null_fields=null_fields,
            mapping_warnings=warnings,
        )

        _log().info(
            "Mapped measurement %s → candidate for %s: %d mapped, %d null, %d warnings",
            measurement.source_measure_group_id,
            garmin_date,
            len(mapped),
            len(null_fields),
            len(warnings),
        )
        return candidate

    def _build_idempotency_key(self, measurement: BodyCompositionMeasurement) -> str:
        """Build a deterministic, stable idempotency key.

        Format: ``withings:{measure_group_id}:{garmin_date}:{weight_kg}``

        If measure_group_id is missing, fall back to a hash of
        source + timestamp + date + weight + device_id.
        """
        grp = measurement.source_measure_group_id or "nogroup"
        dt = measurement.garmin_date.isoformat()
        wt = f"{measurement.weight_kg:.2f}" if measurement.weight_kg else "noweight"
        dev = measurement.source_device_id or "nodevice"
        return f"withings:{grp}:{dt}:{wt}:{dev}"
