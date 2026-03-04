"""Coordinator for realtime departures."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
import logging
import math

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .api import ZtmTrojmiastoApiClient, ZtmTrojmiastoApiError
from .const import (
    CONF_INCLUDE_SCHEDULED,
    CONF_LINE_ID,
    CONF_REFRESH_INTERVAL,
    CONF_STOP_ID,
    DEFAULT_INCLUDE_SCHEDULED,
    DEFAULT_REFRESH_INTERVAL,
    DOMAIN,
)


@dataclass(frozen=True, slots=True)
class DepartureInfo:
    """Normalized departure object."""

    route_id: int
    route_short_name: str
    headsign: str
    status: str
    estimated_time: datetime
    theoretical_time: datetime | None
    timestamp: datetime | None
    delay_seconds: int | None
    vehicle_code: int | None
    vehicle_id: int | None
    vehicle_service: str | None

    def countdown_minutes(self, now: datetime) -> int:
        """Return minutes remaining until departure."""
        seconds = int((self.estimated_time - now).total_seconds())
        if seconds <= 0:
            return 0
        return math.ceil(seconds / 60)

    def countdown_label(self, now: datetime) -> str:
        """Return a human readable countdown label."""
        countdown = self.countdown_minutes(now)
        if countdown == 0:
            return "now"
        return f"{countdown} min"


@dataclass(frozen=True, slots=True)
class ZtmTrojmiastoData:
    """Coordinator payload."""

    last_update: datetime | None
    departures: tuple[DepartureInfo, ...]


class ZtmTrojmiastoDataUpdateCoordinator(DataUpdateCoordinator[ZtmTrojmiastoData]):
    """Manage data retrieval from ZTM Trojmiasto."""

    config_entry: ConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        api: ZtmTrojmiastoApiClient,
        entry: ConfigEntry,
    ) -> None:
        self.api = api
        self.config_entry = entry
        self.stop_id = int(entry.data[CONF_STOP_ID])
        self.line_id = entry.data.get(CONF_LINE_ID)
        self.include_scheduled = entry.options.get(
            CONF_INCLUDE_SCHEDULED,
            DEFAULT_INCLUDE_SCHEDULED,
        )

        refresh_interval = entry.options.get(
            CONF_REFRESH_INTERVAL,
            DEFAULT_REFRESH_INTERVAL,
        )

        super().__init__(
            hass,
            logger=logging.getLogger(__package__),
            name=f"{DOMAIN}_{entry.entry_id}",
            update_interval=timedelta(seconds=refresh_interval),
        )

    async def _async_update_data(self) -> ZtmTrojmiastoData:
        """Fetch the latest departures."""
        try:
            payload = await self.api.async_get_departures(self.stop_id)
        except ZtmTrojmiastoApiError as err:
            raise UpdateFailed(str(err)) from err

        if not payload:
            return ZtmTrojmiastoData(last_update=None, departures=tuple())

        departures_payload = payload.get("departures")
        if departures_payload is None and str(self.stop_id) in payload:
            payload = payload[str(self.stop_id)]
            departures_payload = payload.get("departures", [])

        if not isinstance(departures_payload, list):
            raise UpdateFailed("Unexpected departures payload")

        now = dt_util.utcnow()
        cutoff = now - timedelta(seconds=90)
        departures: list[DepartureInfo] = []

        for item in departures_payload:
            route_id = item.get("routeId")
            if route_id is None:
                continue

            route_id = int(route_id)
            if self.line_id is not None and route_id != int(self.line_id):
                continue

            status = str(item.get("status") or "").upper()
            if not self.include_scheduled and status != "REALTIME":
                continue

            estimated_time = _parse_datetime(item.get("estimatedTime"))
            if estimated_time is None or estimated_time < cutoff:
                continue

            departures.append(
                DepartureInfo(
                    route_id=route_id,
                    route_short_name=str(item.get("routeShortName") or route_id),
                    headsign=str(item.get("headsign") or ""),
                    status=status or "UNKNOWN",
                    estimated_time=estimated_time,
                    theoretical_time=_parse_datetime(item.get("theoreticalTime")),
                    timestamp=_parse_datetime(item.get("timestamp")),
                    delay_seconds=item.get("delayInSeconds"),
                    vehicle_code=item.get("vehicleCode"),
                    vehicle_id=item.get("vehicleId"),
                    vehicle_service=item.get("vehicleService"),
                )
            )

        departures.sort(key=lambda departure: departure.estimated_time)
        return ZtmTrojmiastoData(
            last_update=_parse_datetime(payload.get("lastUpdate")),
            departures=tuple(departures),
        )


def _parse_datetime(value: object) -> datetime | None:
    """Parse an ISO datetime returned by the API."""
    if not value or not isinstance(value, str):
        return None
    parsed = dt_util.parse_datetime(value)
    if parsed is None:
        return None
    if parsed.tzinfo is None:
        return dt_util.as_utc(parsed)
    return parsed.astimezone(dt_util.UTC)
