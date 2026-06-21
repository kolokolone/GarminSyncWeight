"""Shared test fixtures and configuration."""

import json
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest
from app.config import Settings
from app.models.garmin import GarminBodyComposition, GarminBodyCompositionCandidate, GarminWeighIn
from app.services.deduplicator import Deduplicator
from app.services.mapper import WithingsToGarminMapper
from app.services.withings_parser import WithingsParser
from app.storage.sync_store import SyncStore

_FIXTURES_DIR = Path(__file__).parent / "fixtures"


# ── Settings ────────────────────────────────────────────────────


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(  # type: ignore[call-arg]
        withings_client_id="test_client_id",
        withings_client_secret="test_client_secret",
        app_timezone="Europe/Paris",
        data_dir=tmp_path / "data",
        log_dir=tmp_path / "logs",
        runtime_dir=tmp_path / "runtime",
        user_height_m=1.75,
        weight_duplicate_epsilon_kg=0.05,
        weight_conflict_epsilon_kg=0.2,
    )


@pytest.fixture
def settings_no_height(tmp_path: Path) -> Settings:
    return Settings(  # type: ignore[call-arg]
        withings_client_id="test_client_id",
        withings_client_secret="test_client_secret",
        app_timezone="Europe/Paris",
        data_dir=tmp_path / "data_no_height",
        log_dir=tmp_path / "logs_no_height",
        runtime_dir=tmp_path / "runtime_no_height",
        user_height_m=None,
    )


# ── Parser ──────────────────────────────────────────────────────


@pytest.fixture
def parser(settings: Settings) -> WithingsParser:
    return WithingsParser(settings)


@pytest.fixture
def parser_no_height(settings_no_height: Settings) -> WithingsParser:
    return WithingsParser(settings_no_height)


# ── Mapper ──────────────────────────────────────────────────────


@pytest.fixture
def mapper(settings: Settings) -> WithingsToGarminMapper:
    return WithingsToGarminMapper(settings)


@pytest.fixture
def mapper_no_height(settings_no_height: Settings) -> WithingsToGarminMapper:
    return WithingsToGarminMapper(settings_no_height)


# ── Deduplicator ────────────────────────────────────────────────


@pytest.fixture
def sync_store(settings: Settings) -> SyncStore:
    store = SyncStore(settings.resolved_data_dir)
    yield store
    store.close()


@pytest.fixture
def dedup(settings: Settings, sync_store: SyncStore) -> Deduplicator:
    return Deduplicator(settings, sync_store)


# ── Test data helpers ──────────────────────────────────────────


def load_fixture(name: str) -> dict:
    path = _FIXTURES_DIR / name
    return json.loads(path.read_text(encoding="utf-8"))


def make_weigh_in(date_str: str, weight_kg: float) -> GarminWeighIn:
    return GarminWeighIn(
        date=date.fromisoformat(date_str),
        weight_kg=Decimal(str(weight_kg)),
    )


def make_body_composition(date_str: str, weight_kg: float) -> GarminBodyComposition:
    return GarminBodyComposition(
        date=date.fromisoformat(date_str),
        weight_kg=Decimal(str(weight_kg)),
    )


def make_candidate(
    date_str: str,
    weight_kg: Decimal | None = Decimal("78.5"),
    idempotency_key: str = "withings:test:2024-06-01:78.50:nodevice",
) -> GarminBodyCompositionCandidate:
    return GarminBodyCompositionCandidate(
        date=date.fromisoformat(date_str),
        weight=weight_kg,
        idempotency_key=idempotency_key,
    )
