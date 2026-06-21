"""Pydantic models for Garmin Connect data structures.

Includes the candidate model produced by the mapper before writing,
and models for existing Garmin weigh-in / body-composition data.
"""

from datetime import date, datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, field_validator


class GarminWeighIn(BaseModel):
    """A daily weigh-in entry from Garmin Connect (get_daily_weigh_ins)."""

    date: date
    weight_kg: Decimal | None = None
    bmi: Decimal | None = None
    timestamp_local: datetime | None = None
    raw: dict[str, Any] = {}

    @field_validator("weight_kg", "bmi", mode="before")
    @classmethod
    def coerce_decimal(cls, value: object) -> object:
        if value is None:
            return None
        return Decimal(str(value))


class GarminBodyComposition(BaseModel):
    """A body-composition entry from Garmin Connect (get_body_composition)."""

    date: date
    weight_kg: Decimal | None = None
    percent_fat: Decimal | None = None
    percent_hydration: Decimal | None = None
    visceral_fat_mass: Decimal | None = None
    bone_mass: Decimal | None = None
    muscle_mass: Decimal | None = None
    basal_met: Decimal | None = None
    physique_rating: int | None = None
    metabolic_age: int | None = None
    visceral_fat_rating: int | None = None
    bmi: Decimal | None = None
    raw: dict[str, Any] = {}

    @field_validator(
        "weight_kg",
        "percent_fat",
        "percent_hydration",
        "visceral_fat_mass",
        "bone_mass",
        "muscle_mass",
        "basal_met",
        "bmi",
        mode="before",
    )
    @classmethod
    def coerce_decimal(cls, value: object) -> object:
        if value is None:
            return None
        return Decimal(str(value))


class GarminBodyCompositionCandidate(BaseModel):
    """A candidate for writing to Garmin Connect produced by the mapper.

    Includes full audit metadata: which fields mapped, which were
    ignored, which were absent, and why.
    """

    date: date
    measured_at_local: datetime | None = None

    weight: Decimal | None = None
    percent_fat: Decimal | None = None
    percent_hydration: Decimal | None = None
    visceral_fat_mass: Decimal | None = None
    bone_mass: Decimal | None = None
    muscle_mass: Decimal | None = None
    basal_met: Decimal | None = None
    active_met: Decimal | None = None
    physique_rating: int | None = None
    metabolic_age: int | None = None
    visceral_fat_rating: int | None = None
    bmi: Decimal | None = None

    source: str = "withings"
    source_measure_group_id: str | None = None
    source_device_id: str | None = None
    idempotency_key: str

    # ── Audit fields ──────────────────────────────────────────
    mapped_fields: dict[str, Any] = {}
    ignored_fields: dict[str, Any] = {}
    null_fields: list[str] = []
    mapping_warnings: list[str] = []

    def has_weight(self) -> bool:
        return self.weight is not None and self.weight > 0

    def has_composition(self) -> bool:
        return any(
            x is not None
            for x in [
                self.percent_fat,
                self.percent_hydration,
                self.visceral_fat_mass,
                self.bone_mass,
                self.muscle_mass,
                self.basal_met,
                self.physique_rating,
                self.metabolic_age,
                self.visceral_fat_rating,
                self.bmi,
            ]
        )

    def garmin_write_method(self) -> str:
        """Determine the target Garmin API method based on available data."""
        if self.has_weight() and self.has_composition():
            return "add_body_composition"
        if self.has_weight() and self.measured_at_local is not None:
            return "add_weigh_in_with_timestamps"
        if self.has_weight():
            return "add_weigh_in"
        return "invalid"

    def garmin_params(self) -> dict[str, object]:
        """Return the parameters that would be passed to the Garmin API."""
        weight_val = float(self.weight) if self.weight else 0.0
        ts = self.measured_at_local.isoformat() if self.measured_at_local else self.date.isoformat()
        base: dict[str, object] = {"timestamp": ts, "weight": weight_val}
        if self.garmin_write_method() == "add_body_composition":
            def _f(v: object) -> float | None:
                return float(v) if v is not None else None

            comp = {
                "percent_fat": _f(self.percent_fat),
                "percent_hydration": _f(self.percent_hydration),
                "visceral_fat_mass": _f(self.visceral_fat_mass),
                "bone_mass": _f(self.bone_mass),
                "muscle_mass": _f(self.muscle_mass),
                "basal_met": float(self.basal_met) if self.basal_met is not None else None,
                "active_met": float(self.active_met) if self.active_met is not None else None,
                "physique_rating": self.physique_rating,
                "metabolic_age": self.metabolic_age,
                "visceral_fat_rating": self.visceral_fat_rating,
                "bmi": float(self.bmi) if self.bmi is not None else None,
            }
            base.update({k: v for k, v in comp.items() if v is not None})
        return base
