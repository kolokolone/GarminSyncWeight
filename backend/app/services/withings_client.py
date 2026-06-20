"""HTTP client for the Withings Measure API (getmeas).

Uses a valid access token from ``WithingsAuthService`` to fetch
body-composition measurements.

See: https://developer.withings.com/api-reference/#operation/measure-getmeas
"""

from datetime import datetime
from typing import Any

import httpx
from app.config import Settings
from app.services.withings_auth import WithingsAuthService

WITHINGS_API_BASE = "https://wbsapi.withings.net"
MEASURE_ENDPOINT = f"{WITHINGS_API_BASE}/measure"

_logger = None


def _log() -> Any:
    global _logger
    if _logger is None:
        from app.logging_config import get_logger

        _logger = get_logger("withings")
    return _logger


class WithingsClient:
    """HTTP client for the Withings Measure API."""

    def __init__(self, auth_service: WithingsAuthService, settings: Settings) -> None:
        self._auth = auth_service
        self._settings = settings

    async def get_measurements(
        self,
        start_date: datetime,
        end_date: datetime,
    ) -> list[dict[str, Any]]:
        """Fetch Withings measure groups between *start_date* and *end_date*.

        Returns: the raw ``measuregrps`` list from the API response.
        """
        token = await self._auth.get_valid_access_token()
        params = {
            "action": "getmeas",
            "access_token": token,  # Will be redacted in logs
            "startdate": str(int(start_date.timestamp())),
            "enddate": str(int(end_date.timestamp())),
        }

        _log().info(
            "Fetching Withings measurements — startdate=%s enddate=%s",
            start_date.isoformat(),
            end_date.isoformat(),
        )

        async with httpx.AsyncClient() as client:
            resp = await client.get(MEASURE_ENDPOINT, params=params)
            resp.raise_for_status()
            body = resp.json()

        if body.get("status") != 0:
            error = body.get("error", "unknown")
            _log().error("Withings API error — status=%s error=%s", body.get("status"), error)
            raise RuntimeError(f"Withings API error (status {body.get('status')}): {error}")

        measure_groups = body.get("body", {}).get("measuregrps", [])
        _log().info("Retrieved %d measure groups from Withings", len(measure_groups))
        return measure_groups
