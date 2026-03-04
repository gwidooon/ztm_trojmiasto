"""HTTP client for ZTM Trojmiasto open data."""

from __future__ import annotations

from typing import Any

from aiohttp import ClientError, ClientSession


STOPS_URL = (
    "https://ckan.multimediagdansk.pl/dataset/"
    "c24aa637-3619-4dc2-a171-a23eec8f2172/resource/"
    "4c4025f0-01bf-41f7-a39f-d156d201b82b/download/stops.json"
)
ROUTES_URL = (
    "https://ckan.multimediagdansk.pl/dataset/"
    "c24aa637-3619-4dc2-a171-a23eec8f2172/resource/"
    "22313c56-5acf-41c7-a5fd-dc5dc72b3851/download/routes.json"
)
STOPS_IN_TRIP_URL = (
    "https://ckan.multimediagdansk.pl/dataset/"
    "c24aa637-3619-4dc2-a171-a23eec8f2172/resource/"
    "3115d29d-b763-4af5-93f6-763b835967d6/download/stopsintrip.json"
)
DEPARTURES_URL = "https://ckan2.multimediagdansk.pl/departures"


class ZtmTrojmiastoApiError(Exception):
    """Base integration error."""


class ZtmTrojmiastoApiClient:
    """Small API wrapper around official ZTM Trojmiasto resources."""

    def __init__(self, session: ClientSession) -> None:
        self._session = session

    async def async_get_departures(self, stop_id: int) -> dict[str, Any]:
        """Fetch realtime departures for a single stop."""
        return await self._async_get_json(DEPARTURES_URL, params={"stopId": stop_id})

    async def async_get_stops(self) -> dict[str, Any]:
        """Fetch stops catalog."""
        return await self._async_get_json(STOPS_URL)

    async def async_get_routes(self) -> dict[str, Any]:
        """Fetch routes catalog."""
        return await self._async_get_json(ROUTES_URL)

    async def async_get_stops_in_trip(self) -> dict[str, Any]:
        """Fetch stop-to-route mapping data."""
        return await self._async_get_json(STOPS_IN_TRIP_URL)

    async def _async_get_json(
        self,
        url: str,
        *,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Perform an HTTP GET and parse JSON."""
        try:
            async with self._session.get(
                url,
                params=params,
                raise_for_status=True,
                timeout=20,
            ) as response:
                payload = await response.json(content_type=None)
        except (ClientError, TimeoutError, ValueError) as err:
            raise ZtmTrojmiastoApiError(f"Unable to fetch {url}") from err

        if not isinstance(payload, dict):
            raise ZtmTrojmiastoApiError(f"Unexpected payload from {url}")

        return payload
