"""HTTP client for the Withings Measure API (getmeas).

Uses a valid access token from ``WithingsAuthService`` to fetch
body-composition measurements.

See: https://developer.withings.com/api-reference/#operation/measure-getmeas
"""

from datetime import datetime
from typing import Any

import httpx
from app.config import Settings
from app.services.withings_auth import WithingsApiError, WithingsAuthService

WITHINGS_API_BASE = "https://wbsapi.withings.net"
MEASURE_ENDPOINT = f"{WITHINGS_API_BASE}/measure"
BODY_COMPOSITION_MEASURE_TYPES = "1,5,6,8,76,77,88,170,226,227"

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
            "meastypes": BODY_COMPOSITION_MEASURE_TYPES,
            "category": "1",
            "startdate": str(int(start_date.timestamp())),
            "enddate": str(int(end_date.timestamp())),
        }

        _log().info(
            "Fetching Withings measurements — startdate=%s enddate=%s",
            start_date.isoformat(),
            end_date.isoformat(),
        )

        measure_groups: list[dict[str, Any]] = []
        offset: int | None = None
        updatetime: int | None = None
        async with httpx.AsyncClient(timeout=30) as client:
            while True:
                request_data = dict(params)
                if offset is not None:
                    request_data["offset"] = str(offset)
                resp = await client.post(
                    MEASURE_ENDPOINT,
                    data=request_data,
                    headers={"Authorization": f"Bearer {token}"},
                )
                resp.raise_for_status()
                body = resp.json()

                if body.get("status") == 100:
                    return []
                if body.get("status") != 0:
                    error = body.get("error", "unknown")
                    _log().error(
                        "Withings API error — status=%s error=%s",
                        body.get("status"),
                        error,
                    )
                    raise WithingsApiError(
                        f"Withings API error (status {body.get('status')}): {error}"
                    )

                response_body = body.get("body", {})
                updatetime = response_body.get("updatetime", updatetime)
                measure_groups.extend(response_body.get("measuregrps", []))
                if not response_body.get("more"):
                    break
                offset = int(response_body.get("offset", 0))

        _log().info(
            "Retrieved %d measure groups from Withings — updatetime=%s",
            len(measure_groups), updatetime,
        )
        return measure_groups
