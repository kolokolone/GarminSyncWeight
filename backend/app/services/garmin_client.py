"""Read-only client for Garmin Connect data via MCP endpoints.

In this first version, only read operations are implemented.
Write calls are stubbed and guarded by the sync engine's safeguard.

The actual Garmin MCP endpoint integration will be done via the
``garmin_mcp`` tool calls (get_weigh_ins, get_daily_weigh_ins,
get_body_composition).

For testing, this class can be mocked at the method level.
"""

from datetime import date
from decimal import Decimal
from typing import Any

from app.config import Settings
from app.models.garmin import GarminBodyComposition, GarminWeighIn

_logger = None


def _log() -> Any:
    global _logger
    if _logger is None:
        from app.logging_config import get_logger

        _logger = get_logger("garmin")
    return _logger


class GarminClient:
    """Read-only interface for fetching existing Garmin Connect data.

    In production, these methods will call the Garmin MCP endpoints.
    For now, the class operates in 'mock' mode returning empty lists
    so the pipeline can be tested end-to-end in dry-run mode.

    When the MCP bridge is connected, set ``use_mcp=True`` and
    implement the MCP calls in each method.
    """

    def __init__(self, settings: Settings, use_mcp: bool = False) -> None:
        self._settings = settings
        self._use_mcp = use_mcp
        self._mock_data: dict[str, Any] = {}

    def set_mock_data(
        self,
        weigh_ins: list[dict] | None = None,
        body_compositions: list[dict] | None = None,
    ) -> None:
        """Inject mock data for testing without MCP."""
        self._mock_data = {
            "weigh_ins": weigh_ins or [],
            "body_compositions": body_compositions or [],
        }

    async def get_daily_weigh_ins(self, target_date: date) -> list[GarminWeighIn]:
        """Fetch weigh-ins for a specific date from Garmin Connect."""
        if not self._use_mcp:
            return self._mock_weigh_ins(target_date)
        return await self._mcp_get_daily_weigh_ins(target_date)

    async def get_body_composition(
        self, start_date: date, end_date: date,
    ) -> list[GarminBodyComposition]:
        """Fetch body composition entries in a date range."""
        if not self._use_mcp:
            return self._mock_body_composition(start_date, end_date)
        return await self._mcp_get_body_composition(start_date, end_date)

    def can_read(self) -> bool:
        """Return True if Garmin read access is available."""
        return self._use_mcp or bool(
            self._mock_data.get("weigh_ins")
            or self._mock_data.get("body_compositions")
        )

    # ── Mock implementations (for testing) ─────────────────────

    def _mock_weigh_ins(self, target_date: date) -> list[GarminWeighIn]:
        """Filter mock weigh-ins by date."""
        results: list[GarminWeighIn] = []
        for raw in self._mock_data.get("weigh_ins", []):
            entry = GarminWeighIn(
                date=target_date,
                weight_kg=Decimal(str(raw["weight_kg"])) if "weight_kg" in raw else None,
                bmi=Decimal(str(raw["bmi"])) if "bmi" in raw else None,
                raw=raw,
            )
            results.append(entry)
        return results

    def _mock_body_composition(
        self, start_date: date, end_date: date,
    ) -> list[GarminBodyComposition]:
        """Filter mock body composition entries by date range."""
        results: list[GarminBodyComposition] = []
        for raw in self._mock_data.get("body_compositions", []):
            raw_date_str = raw.get("date", "")
            if not raw_date_str:
                continue
            try:
                raw_date = date.fromisoformat(raw_date_str)
            except ValueError:
                continue
            if start_date <= raw_date <= end_date:
                entry = GarminBodyComposition(
                    date=raw_date,
                    weight_kg=Decimal(str(raw["weight_kg"])) if "weight_kg" in raw else None,
                    percent_fat=Decimal(str(raw["percent_fat"])) if "percent_fat" in raw else None,
                    raw=raw,
                )
                results.append(entry)
        return results

    # ── MCP stubs (to be implemented when MCP bridge is active) ─

    async def _mcp_get_daily_weigh_ins(self, target_date: date) -> list[GarminWeighIn]:
        """Call Garmin MCP's get_daily_weigh_ins endpoint."""
        # TODO: Implement when MCP bridge is available
        _log().warning("MCP not connected — returning empty weigh-ins for %s", target_date)
        return []

    async def _mcp_get_body_composition(
        self, start_date: date, end_date: date,
    ) -> list[GarminBodyComposition]:
        """Call Garmin MCP's get_body_composition endpoint."""
        # TODO: Implement when MCP bridge is available
        _log().warning(
            "MCP not connected — returning empty body composition for %s to %s",
            start_date, end_date,
        )
        return []

    # ── Write stubs (guarded, never called in dry-run) ─────────

    _WRITE_DISABLED_MSG = (
        "Garmin writes are disabled in v1. "
        "Set ENABLE_GARMIN_WRITES=true to allow."
    )

    async def add_body_composition(self, **kwargs: Any) -> dict[str, Any]:
        """Write body composition to Garmin Connect.

        WARNING: This function must NEVER be called in dry-run mode.
        It is guarded by the sync engine's centralized write gate.
        """
        _log().warning(
            "Garmin write 'add_body_composition' called — this should not happen in dry-run!",
        )
        raise RuntimeError(self._WRITE_DISABLED_MSG)

    async def add_weigh_in_with_timestamps(self, **kwargs: Any) -> dict[str, Any]:
        """Write weigh-in with timestamps to Garmin Connect."""
        _log().warning(
            "Garmin write 'add_weigh_in_with_timestamps' called — "
            "this should not happen in dry-run!",
        )
        raise RuntimeError(self._WRITE_DISABLED_MSG)

    async def add_weigh_in(self, **kwargs: Any) -> dict[str, Any]:
        """Write weigh-in to Garmin Connect."""
        _log().warning(
            "Garmin write 'add_weigh_in' called — this should not happen in dry-run!",
        )
        raise RuntimeError(self._WRITE_DISABLED_MSG)
