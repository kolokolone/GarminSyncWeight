"""Tests for the controlled synchronization pipeline."""

from datetime import UTC, datetime
from typing import Any

import pytest
from app.config import Settings
from app.services.deduplicator import Deduplicator
from app.services.garmin_client import GarminClient
from app.services.mapper import WithingsToGarminMapper
from app.services.report_builder import ReportBuilder
from app.services.sync_engine import SyncEngine
from app.services.withings_auth import WithingsAuthService
from app.services.withings_client import WithingsClient
from app.services.withings_parser import WithingsParser
from app.storage.sync_store import SyncStore
from app.storage.token_store import TokenStore


class ConnectedWithingsAuth(WithingsAuthService):
    async def check_connection(self) -> dict[str, Any]:
        return {"connected": True, "state": "connected", "message": "ok"}

    async def get_valid_access_token(self) -> str:
        return "token"


class ConnectedGarminClient(GarminClient):
    def __init__(self, settings: Settings, existing: list[dict] | None = None) -> None:
        super().__init__(settings, test_data={"weigh_ins": existing or [], "body_compositions": []})
        self.writes: list[dict[str, Any]] = []

    async def check_connection(self) -> dict[str, Any]:
        return {"connected": True, "state": "connected", "message": "ok"}

    async def add_body_composition(self, **kwargs: Any) -> dict[str, Any]:
        self.writes.append(kwargs)
        return {"status": "success", "id": "garmin-1"}


class StaticWithingsClient(WithingsClient):
    def __init__(
        self,
        auth_service: WithingsAuthService,
        settings: Settings,
        groups: list[dict],
    ) -> None:
        super().__init__(auth_service, settings)
        self.groups = groups

    async def get_measurements(
        self,
        start_date: datetime,
        end_date: datetime,
    ) -> list[dict[str, Any]]:
        return self.groups


def _group(weight: int = 7850, date_ts: int = 1717221600) -> dict[str, Any]:
    return {
        "grpid": 123,
        "date": date_ts,
        "created": date_ts,
        "category": 1,
        "deviceid": "scale-1",
        "measures": [
            {"type": 1, "value": weight, "unit": -2},
            {"type": 6, "value": 220, "unit": -1},
            {"type": 76, "value": 5500, "unit": -2},
            {"type": 88, "value": 280, "unit": -2},
        ],
    }


def _engine(settings: Settings, groups: list[dict], garmin: ConnectedGarminClient) -> SyncEngine:
    token_store = TokenStore(settings.resolved_data_dir)
    sync_store = SyncStore(settings.resolved_data_dir)
    auth = ConnectedWithingsAuth(settings, token_store)
    wclient = StaticWithingsClient(auth, settings, groups)
    parser = WithingsParser(settings)
    mapper = WithingsToGarminMapper(settings)
    dedup = Deduplicator(settings, sync_store)
    report = ReportBuilder(settings)
    return SyncEngine(settings, auth, wclient, parser, mapper, garmin, dedup, sync_store, report)


@pytest.mark.asyncio
async def test_sync_writes_new_measurement(settings: Settings) -> None:
    garmin = ConnectedGarminClient(settings)
    report = await _engine(settings, [_group()], garmin).run_sync("2024-06-01", "2024-06-01")
    assert report.mode == "sync"
    assert report.summary.synced_count == 1
    assert len(garmin.writes) == 1
    assert garmin.writes[0]["weight"] == 78.5
    assert garmin.writes[0]["percent_fat"] == 22.0


@pytest.mark.asyncio
async def test_sync_skips_existing_same_day_same_weight(settings: Settings) -> None:
    garmin = ConnectedGarminClient(settings, existing=[{"date": "2024-06-01", "weight_kg": "78.5"}])
    report = await _engine(settings, [_group()], garmin).run_sync("2024-06-01", "2024-06-01")
    assert report.summary.synced_count == 0
    assert report.summary.skipped_existing_count == 1
    assert garmin.writes == []


@pytest.mark.asyncio
async def test_sync_conflict_same_day_different_weight(settings: Settings) -> None:
    garmin = ConnectedGarminClient(settings, existing=[{"date": "2024-06-01", "weight_kg": "79.0"}])
    report = await _engine(settings, [_group()], garmin).run_sync("2024-06-01", "2024-06-01")
    assert report.summary.conflicts_count == 1
    assert garmin.writes == []


@pytest.mark.asyncio
async def test_sync_refuses_without_active_prerequisites(settings: Settings) -> None:
    class DisconnectedGarmin(ConnectedGarminClient):
        async def check_connection(self) -> dict[str, Any]:
            return {"connected": False, "state": "no_token", "message": "Garmin absent"}

    engine = _engine(settings, [_group()], DisconnectedGarmin(settings))
    with pytest.raises(RuntimeError, match="Garmin absent"):
        await engine.run_sync("2024-06-01", "2024-06-01")


def test_idempotency_event_blocks_only_confirmed_results(settings: Settings) -> None:
    store = SyncStore(settings.resolved_data_dir)
    key_failed = "withings:789:2024-06-02:78.50:scale-1"
    key_synced = "withings:789:2024-06-03:78.50:scale-1"
    assert store.event_exists(key_failed) is False
    store.save_candidate(
        idempotency_key=key_failed, date="2024-06-02", weight_kg="78.5",
        decision="failed", reason="Test failure",
    )
    assert store.event_exists(key_failed) is False
    store.save_candidate(
        idempotency_key=key_synced, date="2024-06-03", weight_kg="78.5",
        decision="synced", reason="Test sync",
    )
    assert store.event_exists(key_synced) is True
