"""Tests for the dry-run pipeline.

Verifies that:
  - dry-run never calls Garmin write
  - reports are correctly built
  - pipeline handles missing tokens gracefully
"""


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


@pytest.fixture
def dry_run_engine(settings: Settings) -> SyncEngine:
    """Create a SyncEngine with mock services for dry-run testing."""
    token_store = TokenStore(settings.resolved_data_dir)
    sync_store = SyncStore(settings.resolved_data_dir)
    auth = WithingsAuthService(settings, token_store)
    wclient = WithingsClient(auth, settings)
    parser = WithingsParser(settings)
    mapper = WithingsToGarminMapper(settings)
    garmin = GarminClient(settings, use_mcp=False)
    dedup = Deduplicator(settings, sync_store)
    report = ReportBuilder(settings)
    return SyncEngine(settings, auth, wclient, parser, mapper, garmin, dedup, sync_store, report)


@pytest.mark.asyncio
async def test_dry_run_never_calls_write(dry_run_engine: SyncEngine, settings: Settings) -> None:
    """Dry-run must NEVER call any Garmin write method.

    The GarminClient write methods raise RuntimeError if called.
    """
    # Even without Withings data, dry-run should complete without errors
    report = await dry_run_engine.run_dry_run("2024-06-01", "2024-06-02")
    assert report.mode == "dry_run"
    # The write methods in GarminClient raise RuntimeError if called
    # Since we have no token and no mock data, we just verify the report is valid


@pytest.mark.asyncio
async def test_dry_run_with_mock_garmin_data(
    dry_run_engine: SyncEngine, settings: Settings,
) -> None:
    """Dry-run with mock Garmin data should not trigger writes."""
    # Inject mock data via GarminClient
    dry_run_engine._garmin.set_mock_data(
        weigh_ins=[{"date": "2024-06-01", "weight_kg": "78.5", "bmi": "24.0"}],
        body_compositions=[{"date": "2024-06-01", "weight_kg": "78.5", "percent_fat": "22.0"}],
    )
    report = await dry_run_engine.run_dry_run("2024-06-01", "2024-06-02")
    assert report.mode == "dry_run"
    # Verify no write was triggered (GarminClient raises on write calls)


@pytest.mark.asyncio
async def test_dry_run_report_structure(dry_run_engine: SyncEngine) -> None:
    """Verify the dry-run report contains expected sections."""
    report = await dry_run_engine.run_dry_run("2024-06-01", "2024-06-02")
    assert hasattr(report, "mode")
    assert hasattr(report, "period")
    assert hasattr(report, "withings")
    assert hasattr(report, "garmin")
    assert hasattr(report, "candidates")
    assert hasattr(report, "summary")
    assert report.period["start_date"] == "2024-06-01"
    assert report.period["end_date"] == "2024-06-02"


@pytest.mark.asyncio
async def test_execute_blocked_by_default(settings: Settings) -> None:
    """Even with explicit intent, Garmin writes must be blocked."""
    assert settings.enable_garmin_writes is False
    # The write guards in GarminClient should raise
    client = GarminClient(settings)
    with pytest.raises(RuntimeError, match="writes are disabled"):
        await client.add_body_composition(date="2024-06-01", weight=78.5)
    with pytest.raises(RuntimeError, match="writes are disabled"):
        await client.add_weigh_in_with_timestamps(weight=78.5)
    with pytest.raises(RuntimeError, match="writes are disabled"):
        await client.add_weigh_in(weight=78.5)


def test_no_delete_endpoint_available(settings: Settings) -> None:
    """Verify no delete method exists in GarminClient."""
    client = GarminClient(settings)
    # The client must NOT have a delete method
    assert not hasattr(client, "delete_weigh_ins")
    # All methods starting with 'delete' are forbidden
    for attr_name in dir(client):
        if "delete" in attr_name.lower():
            pytest.fail(f"GarminClient has a delete-related method: {attr_name}")
