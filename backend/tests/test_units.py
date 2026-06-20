"""Tests for Withings value/unit conversion and parsing.

The Withings API encodes values as ``value * 10^unit``.
This test verifies the parser reconstructs the real value correctly.
"""

from decimal import Decimal

from app.services.withings_parser import WithingsParser


def test_value_unit_conversion_positive(parser: WithingsParser) -> None:
    """value=78500, unit=-3 → 78.5 kg."""
    raw = {
        "grpid": 1,
        "date": 1717200000,
        "created": 1717200000,
        "category": 1,
        "measures": [{"type": 1, "value": 78500, "unit": -3}],
    }
    results = parser.parse_measure_groups([raw])
    assert len(results) == 1
    assert results[0].weight_kg == Decimal("78.5")


def test_value_unit_conversion_negative_unit(parser: WithingsParser) -> None:
    """value=220, unit=-1 → 22.0 (fat percent)."""
    raw = {
        "grpid": 2,
        "date": 1717200000,
        "created": 1717200000,
        "category": 1,
        "measures": [{"type": 6, "value": 220, "unit": -1}],
    }
    results = parser.parse_measure_groups([raw])
    assert len(results) == 1
    assert results[0].fat_percent == Decimal("22.0")


def test_value_unit_conversion_zero(parser: WithingsParser) -> None:
    """value=0, unit=0 → Decimal('0')."""
    raw = {
        "grpid": 3,
        "date": 1717200000,
        "created": 1717200000,
        "category": 1,
        "measures": [{"type": 1, "value": 0, "unit": 0}],
    }
    results = parser.parse_measure_groups([raw])
    assert len(results) == 1
    assert results[0].weight_kg == Decimal("0")


def test_empty_measures_skipped(parser: WithingsParser) -> None:
    """A group with no measures array should be skipped."""
    raw = {
        "grpid": 4,
        "date": 1717200000,
        "created": 1717200000,
        "category": 1,
        "measures": [],
    }
    results = parser.parse_measure_groups([raw])
    assert len(results) == 0


def test_missing_timestamp_skipped(parser: WithingsParser) -> None:
    """A group without date/created should be skipped."""
    raw = {
        "grpid": 5,
        "measures": [{"type": 1, "value": 78500, "unit": -3}],
    }
    results = parser.parse_measure_groups([raw])
    assert len(results) == 0


def test_weight_only_fixture(parser: WithingsParser) -> None:
    """Parse the weight-only fixture and verify basic structure."""
    from tests.conftest import load_fixture

    data = load_fixture("withings_getmeas_weight_only.json")
    groups = data["body"]["measuregrps"]
    results = parser.parse_measure_groups(groups)
    assert len(results) == 2
    assert results[0].weight_kg == Decimal("78.5")
    assert results[1].weight_kg == Decimal("78.6")
    # No composition fields
    assert results[0].fat_percent is None
    assert results[0].muscle_mass_kg is None
    assert results[0].bone_mass_kg is None
    assert results[0].hydration_mass_kg is None


def test_body_composition_fixture(parser: WithingsParser) -> None:
    """Parse the body-composition fixture with multiple measure types."""
    from tests.conftest import load_fixture

    data = load_fixture("withings_getmeas_body_composition.json")
    groups = data["body"]["measuregrps"]
    results = parser.parse_measure_groups(groups)
    assert len(results) == 3

    # First group: full composition
    m1 = results[0]
    assert m1.weight_kg == Decimal("78.5")
    assert m1.fat_percent == Decimal("22.0")
    assert m1.fat_free_mass_kg == Decimal("61.0")
    assert m1.muscle_mass_kg == Decimal("55.0")
    assert m1.bone_mass_kg == Decimal("2.8")
    assert m1.hydration_mass_kg == Decimal("42.0")

    # Second group: two fat_percent entries (should use last/latest)
    m2 = results[1]
    assert m2.weight_kg == Decimal("78.6")
    assert m2.fat_percent is not None

    # Third group: weight < 20 kg outlier
    m3 = results[2]
    assert m3.weight_kg == Decimal("25.0")
    assert m3.fat_percent == Decimal("1.0")
