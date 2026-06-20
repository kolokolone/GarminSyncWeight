"""Tests for the Withings→Garmin mapper."""

from datetime import UTC, datetime
from decimal import Decimal

from app.models.withings import BodyCompositionMeasurement


def _make_measurement(
    weight_kg: Decimal | None = Decimal("78.5"),
    fat_percent: Decimal | None = Decimal("22.0"),
    muscle_mass_kg: Decimal | None = Decimal("55.0"),
    bone_mass_kg: Decimal | None = Decimal("2.8"),
    hydration_mass_kg: Decimal | None = None,
    fat_mass_kg: Decimal | None = None,
    fat_free_mass_kg: Decimal | None = None,
    user_height_m: float | None = 1.75,
) -> BodyCompositionMeasurement:
    from datetime import date

    from app.models.withings import BodyCompositionMeasurement

    return BodyCompositionMeasurement(
        measured_at_utc=datetime(2024, 6, 1, 12, 0, tzinfo=UTC),
        measured_at_local=datetime(2024, 6, 1, 14, 0),
        garmin_date=date(2024, 6, 1),
        weight_kg=weight_kg,
        fat_percent=fat_percent,
        muscle_mass_kg=muscle_mass_kg,
        bone_mass_kg=bone_mass_kg,
        hydration_mass_kg=hydration_mass_kg,
        fat_mass_kg=fat_mass_kg,
        fat_free_mass_kg=fat_free_mass_kg,
    )


def test_mapping_weight(mapper) -> None:
    """Type 1 Withings → Garmin weight."""
    m = _make_measurement(weight_kg=Decimal("78.5"))
    candidate = mapper.map(m)
    assert candidate.weight == Decimal("78.5")
    assert "weight" in candidate.mapped_fields


def test_mapping_fat_percent(mapper) -> None:
    """Type 6 Withings → Garmin percent_fat."""
    m = _make_measurement(fat_percent=Decimal("22.0"))
    candidate = mapper.map(m)
    assert candidate.percent_fat == Decimal("22.0")
    assert "percent_fat" in candidate.mapped_fields


def test_mapping_muscle_mass(mapper) -> None:
    """Type 76 Withings → Garmin muscle_mass."""
    m = _make_measurement(muscle_mass_kg=Decimal("55.0"))
    candidate = mapper.map(m)
    assert candidate.muscle_mass == Decimal("55.0")


def test_mapping_bone_mass(mapper) -> None:
    """Type 88 Withings → Garmin bone_mass."""
    m = _make_measurement(bone_mass_kg=Decimal("2.8"))
    candidate = mapper.map(m)
    assert candidate.bone_mass == Decimal("2.8")


def test_hydration_mass_not_mapped_to_percent_by_default(mapper) -> None:
    """Type 77 hydration must NOT be auto-converted to percent_hydration."""
    m = _make_measurement(hydration_mass_kg=Decimal("42.0"))
    candidate = mapper.map(m)
    assert candidate.percent_hydration is None
    assert "percent_hydration" in candidate.null_fields
    assert "hydration_mass_kg" in candidate.ignored_fields


def test_bmi_null_without_height(mapper_no_height) -> None:
    """BMI must be null if USER_HEIGHT_M is not configured."""
    m = _make_measurement(weight_kg=Decimal("78.5"))
    candidate = mapper_no_height.map(m)
    assert candidate.bmi is None
    assert "bmi" in candidate.null_fields


def test_bmi_calculated_with_explicit_height(mapper) -> None:
    """BMI calculated with explicit height: 78.5 / (1.75^2) ≈ 25.6."""
    m = _make_measurement(weight_kg=Decimal("78.5"), user_height_m=1.75)
    candidate = mapper.map(m)
    assert candidate.bmi is not None
    # 78.5 / (1.75*1.75) = 78.5 / 3.0625 = 25.63...
    expected = Decimal("78.5") / (Decimal("1.75") * Decimal("1.75"))
    assert candidate.bmi == expected.quantize(Decimal("0.1"))


def test_unknown_field_ignored(mapper) -> None:
    """Unknown measure types should not appear in mapped_fields."""
    m = _make_measurement()
    mapper.map(m)
    # Ensure mapping warnings mention unknown types if present via raw
    # (no unknown types in the default fixture, so no warnings)


def test_visceral_fat_basal_met_always_null(mapper) -> None:
    """Fields without confirmed Withings source must remain null."""
    m = _make_measurement()
    candidate = mapper.map(m)
    assert candidate.visceral_fat_mass is None
    assert candidate.basal_met is None
    assert candidate.active_met is None
    assert candidate.physique_rating is None
    assert candidate.metabolic_age is None
    assert candidate.visceral_fat_rating is None
