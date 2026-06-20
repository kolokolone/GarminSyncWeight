"""Tests for the deduplicator logic."""

from decimal import Decimal

from tests.conftest import make_body_composition, make_candidate, make_weigh_in


def test_new_candidate_empty_garmin(dedup) -> None:
    """No existing Garmin data → new_candidate."""
    candidate = make_candidate("2024-06-01")
    status = dedup.classify(candidate, [], [])
    assert status == "new_candidate"


def test_duplicate_same_day_same_weight(dedup) -> None:
    """Same day, weight within epsilon → duplicate_exact_or_near."""
    candidate = make_candidate("2024-06-01", Decimal("78.5"))
    weigh_ins = [make_weigh_in("2024-06-01", 78.5)]
    status = dedup.classify(candidate, weigh_ins, [])
    assert status == "duplicate_exact_or_near"


def test_possible_duplicate_small_weight_delta(dedup) -> None:
    """Same day, small weight diff (0.1 kg) within conflict epsilon → possible_duplicate."""
    candidate = make_candidate("2024-06-01", Decimal("78.5"))
    weigh_ins = [make_weigh_in("2024-06-01", 78.6)]
    status = dedup.classify(candidate, weigh_ins, [])
    assert status == "possible_duplicate"


def test_conflict_same_day_different_weight(dedup) -> None:
    """Same day, large weight diff (0.5 kg) → conflict_same_day."""
    candidate = make_candidate("2024-06-01", Decimal("78.5"))
    weigh_ins = [make_weigh_in("2024-06-01", 79.0)]
    status = dedup.classify(candidate, weigh_ins, [])
    assert status == "conflict_same_day"


def test_invalid_missing_weight(dedup) -> None:
    """No weight → invalid_missing_weight."""
    candidate = make_candidate("2024-06-01", None)
    status = dedup.classify(candidate, [], [])
    assert status == "invalid_missing_weight"


def test_invalid_outlier_too_low(dedup) -> None:
    """Weight below 20 kg → invalid_outlier."""
    candidate = make_candidate("2024-06-01", Decimal("15.0"))
    status = dedup.classify(candidate, [], [])
    assert status == "invalid_outlier"


def test_invalid_outlier_too_high(dedup) -> None:
    """Weight above 300 kg → invalid_outlier."""
    candidate = make_candidate("2024-06-01", Decimal("350.0"))
    status = dedup.classify(candidate, [], [])
    assert status == "invalid_outlier"


def test_duplicate_body_composition(dedup) -> None:
    """Existing body composition with same weight → duplicate_body_composition."""
    candidate = make_candidate("2024-06-01", Decimal("78.5"))
    body_comps = [make_body_composition("2024-06-01", 78.5)]
    status = dedup.classify(candidate, [], body_comps)
    assert status == "duplicate_body_composition"


def test_new_candidate_different_days(dedup) -> None:
    """Existing data on different day → new_candidate."""
    candidate = make_candidate("2024-06-02", Decimal("78.5"))
    weigh_ins = [make_weigh_in("2024-06-01", 78.5)]
    status = dedup.classify(candidate, weigh_ins, [])
    assert status == "new_candidate"
