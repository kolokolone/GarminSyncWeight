"""Garmin Connect client compatible with Taxuspt/garmin_mcp tokens.

Garmin authentication is delegated to ``garmin-mcp-auth`` from
https://github.com/Taxuspt/garmin_mcp. Runtime API calls use the same
``python-garminconnect`` library and token directory expected by that connector.
"""

from datetime import date
from decimal import Decimal
from typing import Any

from app.config import Settings
from app.models.garmin import GarminBodyComposition, GarminWeighIn
from app.services.garmin_auth_service import GarminAuthService

_logger = None


def _log() -> Any:
    global _logger
    if _logger is None:
        from app.logging_config import get_logger

        _logger = get_logger("garmin")
    return _logger


class GarminClient:
    """Read/write interface for Garmin Connect body data."""

    def __init__(self, settings: Settings, test_data: dict[str, Any] | None = None) -> None:
        self._settings = settings
        self._test_data: dict[str, Any] = test_data or {}
        self._api: Any | None = None

    def set_test_data(
        self,
        weigh_ins: list[dict] | None = None,
        body_compositions: list[dict] | None = None,
    ) -> None:
        """Inject deterministic data for tests only."""
        self._test_data = {
            "weigh_ins": weigh_ins or [],
            "body_compositions": body_compositions or [],
        }

    async def get_daily_weigh_ins(self, target_date: date) -> list[GarminWeighIn]:
        """Fetch weigh-ins for a specific date from Garmin Connect."""
        if self._test_data:
            return self._test_weigh_ins(target_date)
        raw = self._client().get_daily_weigh_ins(target_date.isoformat())
        return [self._parse_weigh_in(item, target_date) for item in self._extract_measurements(raw)]

    async def get_body_composition(
        self, start_date: date, end_date: date,
    ) -> list[GarminBodyComposition]:
        """Fetch body composition entries in a date range."""
        if self._test_data:
            return self._test_body_composition(start_date, end_date)
        raw = self._client().get_body_composition(start_date.isoformat(), end_date.isoformat())
        return [self._parse_body_composition(item) for item in self._extract_body_entries(raw)]

    async def check_connection(self) -> dict[str, Any]:
        """Verify Garmin token validity with an active command/API check."""
        status = GarminAuthService(self._settings).status()
        if not status.token_valid:
            return {"connected": False, "state": status.state, "message": status.message}
        try:
            client = self._client()
            if hasattr(client, "get_full_name"):
                client.get_full_name()
            return {
                "connected": True,
                "state": "connected",
                "message": "Connexion Garmin vérifiée.",
            }
        except Exception as exc:
            _log().error("Garmin active connection check failed: %s", exc)
            return {"connected": False, "state": "api_error", "message": str(exc)}

    # ── Test-data implementations ──────────────────────────────

    def _test_weigh_ins(self, target_date: date) -> list[GarminWeighIn]:
        """Filter injected test weigh-ins by date."""
        results: list[GarminWeighIn] = []
        for raw in self._test_data.get("weigh_ins", []):
            entry = GarminWeighIn(
                date=target_date,
                weight_kg=Decimal(str(raw["weight_kg"])) if "weight_kg" in raw else None,
                bmi=Decimal(str(raw["bmi"])) if "bmi" in raw else None,
                raw=raw,
            )
            results.append(entry)
        return results

    def _test_body_composition(
        self, start_date: date, end_date: date,
    ) -> list[GarminBodyComposition]:
        """Filter injected test body composition entries by date range."""
        results: list[GarminBodyComposition] = []
        for raw in self._test_data.get("body_compositions", []):
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

    async def add_body_composition(self, **kwargs: Any) -> dict[str, Any]:
        """Write body composition to Garmin Connect using verified parameters."""
        return self._client().add_body_composition(**kwargs)

    async def add_weigh_in_with_timestamps(self, **kwargs: Any) -> dict[str, Any]:
        """Write weigh-in with timestamps to Garmin Connect."""
        return self._client().add_weigh_in(**kwargs)

    async def add_weigh_in(self, **kwargs: Any) -> dict[str, Any]:
        """Write weigh-in to Garmin Connect."""
        return self._client().add_weigh_in(**kwargs)

    def _client(self) -> Any:
        if self._api is not None:
            return self._api
        try:
            from garminconnect import Garmin  # type: ignore[import-not-found]
        except Exception as exc:
            raise RuntimeError(
                "Le client Garmin n'est pas installé. Installe Taxuspt/garmin_mcp "
                "ou garminconnect, puis relance l'application."
            ) from exc
        api = Garmin()
        try:
            api.login(tokenstore=str(self._settings.garmin_token_path))
        except TypeError:
            api.login()
        self._api = api
        return api

    @staticmethod
    def _extract_measurements(raw: Any) -> list[dict[str, Any]]:
        if isinstance(raw, dict):
            data = (
                raw.get("measurements")
                or raw.get("dailyWeightSummaries")
                or raw.get("weighIns")
                or []
            )
            return data if isinstance(data, list) else []
        return raw if isinstance(raw, list) else []

    @staticmethod
    def _extract_body_entries(raw: Any) -> list[dict[str, Any]]:
        if isinstance(raw, dict):
            for key in ("bodyCompositions", "bodyComposition", "dateWeightList", "measurements"):
                value = raw.get(key)
                if isinstance(value, list):
                    return value
            return [raw]
        return raw if isinstance(raw, list) else []

    @staticmethod
    def _parse_weigh_in(raw: dict[str, Any], fallback_date: date) -> GarminWeighIn:
        raw_date = (
            raw.get("date")
            or raw.get("calendarDate")
            or raw.get("samplePk")
            or fallback_date.isoformat()
        )
        parsed_date = fallback_date
        if isinstance(raw_date, str):
            try:
                parsed_date = date.fromisoformat(raw_date[:10])
            except ValueError:
                parsed_date = fallback_date
        weight = raw.get("weight_kg") or raw.get("weightKg")
        if weight is None and raw.get("weight_grams") is not None:
            weight = Decimal(str(raw["weight_grams"])) / Decimal("1000")
        if weight is None and raw.get("weight") is not None:
            weight = raw.get("weight")
        return GarminWeighIn(date=parsed_date, weight_kg=weight, bmi=raw.get("bmi"), raw=raw)

    @staticmethod
    def _parse_body_composition(raw: dict[str, Any]) -> GarminBodyComposition:
        raw_date = raw.get("date") or raw.get("calendarDate") or raw.get("samplePk")
        parsed_date = date.today()
        if isinstance(raw_date, str):
            try:
                parsed_date = date.fromisoformat(raw_date[:10])
            except ValueError:
                parsed_date = date.today()
        weight = raw.get("weight_kg") or raw.get("weightKg")
        if weight is None and raw.get("weight_grams") is not None:
            weight = Decimal(str(raw["weight_grams"])) / Decimal("1000")
        return GarminBodyComposition(
            date=parsed_date,
            weight_kg=weight,
            percent_fat=raw.get("percent_fat") or raw.get("bodyFat") or raw.get("body_fat_percent"),
            percent_hydration=raw.get("percent_hydration") or raw.get("bodyWater"),
            bone_mass=raw.get("bone_mass") or raw.get("boneMass"),
            muscle_mass=raw.get("muscle_mass") or raw.get("muscleMass"),
            bmi=raw.get("bmi"),
            raw=raw,
        )
