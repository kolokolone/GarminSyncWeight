"""Pydantic models for Withings data structures.

Raw API response parsing and canonical body-composition measurement.
"""

from datetime import date, datetime
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, field_validator


class WithingsRawMeasure(BaseModel):
    """A single measure entry from a Withings ``measuregrp``.

    Parsed from the raw ``measures`` array inside each group.
    """

    measure_group_id: str | None = None
    date_utc: datetime
    date_local: datetime
    timezone: str
    category: int | None = None
    attrib: int | None = None
    device_id: str | None = None
    raw_measures: list[dict[str, Any]] = []
    raw_group: dict[str, Any] = {}


class BodyCompositionMeasurement(BaseModel):
    """Canonical internal representation of a single body-composition measurement.

    All fields are nullable except ``source`` and the timestamp trio.
    Fields are set to ``None`` when the source data is missing or unreliable.
    """

    source: Literal["withings"] = "withings"
    source_measure_group_id: str | None = None
    source_device_id: str | None = None
    measured_at_utc: datetime
    measured_at_local: datetime
    garmin_date: date

    # ── Weight & composition ──────────────────────────────────
    weight_kg: Decimal | None = None
    fat_percent: Decimal | None = None
    fat_mass_kg: Decimal | None = None
    fat_free_mass_kg: Decimal | None = None
    muscle_mass_kg: Decimal | None = None
    bone_mass_kg: Decimal | None = None
    hydration_mass_kg: Decimal | None = None
    hydration_percent: Decimal | None = None
    bmi: Decimal | None = None

    # ── Extended (only from Withings when explicitly confirmed) ─
    visceral_fat_mass: Decimal | None = None
    basal_met: Decimal | None = None
    active_met: Decimal | None = None
    physique_rating: int | None = None
    metabolic_age: int | None = None
    visceral_fat_rating: int | None = None

    # ── Audit trail ───────────────────────────────────────────
    raw: dict[str, Any] = {}
    warnings: list[str] = []

    @field_validator(
        "weight_kg", "fat_percent", "fat_mass_kg", "fat_free_mass_kg",
        "muscle_mass_kg", "bone_mass_kg", "hydration_mass_kg",
        "hydration_percent", "bmi", "visceral_fat_mass", "basal_met",
        "active_met", mode="before",
    )
    @classmethod
    def none_if_empty(cls, value: object) -> object:
        if value == "" or value is None:
            return None
        return value

    def has_weight(self) -> bool:
        return self.weight_kg is not None and self.weight_kg > 0

    def has_composition(self) -> bool:
        """Return True if at least one body composition field is present beyond weight."""
        return any(
            x is not None
            for x in [
                self.fat_percent,
                self.fat_mass_kg,
                self.fat_free_mass_kg,
                self.muscle_mass_kg,
                self.bone_mass_kg,
                self.hydration_mass_kg,
            ]
        )
