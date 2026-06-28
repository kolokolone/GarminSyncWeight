"""Garmin Connect client compatible with Taxuspt/garmin_mcp tokens.

Garmin authentication is delegated to ``garmin-mcp-auth`` from
https://github.com/Taxuspt/garmin_mcp. Runtime API calls use the same
``python-garminconnect`` library and token directory expected by that connector.
"""

from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from app.config import Settings
from app.models.garmin import GarminBodyComposition, GarminWeighIn
from app.services.garmin_auth_service import GarminAuthService
from app.storage.garmin_cache import GarminCacheStore

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
        self._cache_store = GarminCacheStore(settings.resolved_data_dir)

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
        """Fetch weigh-ins for a specific date (cached with 1 h TTL)."""
        if self._test_data:
            return self._test_weigh_ins(target_date)
        date_str = target_date.isoformat()
        cached = self._cache_store.get("weigh_in", date_str)
        if cached is not None:
            _log().debug("Cache HIT  weigh_ins %s  (%d entries)", date_str, len(cached))
            return [GarminWeighIn(**item) for item in cached]
        _log().debug("Cache MISS weigh_ins %s", date_str)
        raw = self._client().get_daily_weigh_ins(date_str)
        result = [
            self._parse_weigh_in(item, target_date)
            for item in self._extract_measurements(raw)
        ]
        self._cache_store.set("weigh_in", date_str, [r.model_dump(mode="json") for r in result])
        _log().debug("Cache SET  weigh_ins %s  (%d entries)", date_str, len(result))
        return result

    async def get_body_composition(
        self, start_date: date, end_date: date,
    ) -> list[GarminBodyComposition]:
        """Fetch body composition entries in a date range (cached per‑date, 1 h TTL).

        Dates already in cache are reused; only the sub‑range of uncached
        dates triggers an API call.  Returned list is deduplicated by date.
        """
        if self._test_data:
            return self._test_body_composition(start_date, end_date)

        # Check cache for every date in the range
        cached_by_date: dict[str, list[dict[str, Any]]] = {}
        dates_to_fetch: list[date] = []
        current = start_date
        while current <= end_date:
            date_str = current.isoformat()
            cached = self._cache_store.get("body_composition", date_str)
            if cached is not None:
                cached_by_date[date_str] = cached
            else:
                dates_to_fetch.append(current)
            current += timedelta(days=1)

        # Assemble cache hits first (preserve chronological order)
        result: list[GarminBodyComposition] = []
        for date_str in sorted(cached_by_date):
            for item in cached_by_date[date_str]:
                result.append(GarminBodyComposition(**item))

        if not dates_to_fetch:
            _log().debug("Cache FULL HIT  body_composition  %s … %s", start_date, end_date)
            return result

        # Fetch missing sub‑range from the API
        fetch_start = dates_to_fetch[0]
        fetch_end = dates_to_fetch[-1]
        _log().debug(
            "Cache PARTIAL MISS  body_composition  fetching %s … %s",
            fetch_start, fetch_end,
        )
        raw = self._client().get_body_composition(
            fetch_start.isoformat(), fetch_end.isoformat(),
        )
        parsed = [self._parse_body_composition(item) for item in self._extract_body_entries(raw)]

        # Cache each entry individually; skip dates already collected from cache
        for entry in parsed:
            entry_date_str = entry.date.isoformat()
            if entry_date_str not in cached_by_date:
                result.append(entry)
            self._cache_store.set(
                "body_composition",
                entry_date_str,
                [entry.model_dump(mode="json")],
            )

        _log().debug(
            "Cache SET  body_composition  %d new entries  total=%d",
            len(parsed), len(result),
        )
        return result

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
        """Write body composition to Garmin Connect using verified parameters.

        Wraps the raw garminconnect call with logging and safe error
        propagation so that callers (e.g. sync_engine) can distinguish
        between API failures and programming errors.

        On success the cache entry for the written date is invalidated so
        subsequent reads pull fresh data.
        """
        target = kwargs.copy()
        ts = target.pop("timestamp", None)  # positional first arg
        weight = target.pop("weight", None)
        _log().info("add_body_composition: timestamp=%s weight=%s extra=%s", ts, weight, target)
        try:
            client = self._client()
            result = client.add_body_composition(ts, weight, **target)
            _log().info("add_body_composition succeeded: %s", result)
            # Invalidate cache for the written date (ts is an ISO string)
            if ts:
                date_str = str(ts)[:10]
                self._cache_store.invalidate_date(date_str)
                _log().debug("Cache INVALIDATE %s  (post‑write)", date_str)
            return result  # type: ignore[return-value]
        except Exception as exc:
            _log().error("add_body_composition failed: %s | kwargs=%s", exc, kwargs)
            raise

    async def add_weigh_in_with_timestamps(self, **kwargs: Any) -> dict[str, Any]:
        """Write weigh-in with timestamps to Garmin Connect."""
        return self._client().add_weigh_in(**kwargs)

    async def add_weigh_in(self, **kwargs: Any) -> dict[str, Any]:
        """Write weigh-in to Garmin Connect.

        Invalidates the cache for the written date on success.
        """
        target = kwargs.copy()
        ts = target.pop("timestamp", None)
        weight = target.pop("weight", None)
        _log().info("add_weigh_in: timestamp=%s weight=%s extra=%s", ts, weight, target)
        try:
            result = self._client().add_weigh_in(**kwargs)
            if ts:
                date_str = str(ts)[:10]
                self._cache_store.invalidate_date(date_str)
                _log().debug("Cache INVALIDATE %s  (post‑weigh_in)", date_str)
            return result  # type: ignore[return-value]
        except Exception as exc:
            _log().error("add_weigh_in failed: %s | kwargs=%s", exc, kwargs)
            raise

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
