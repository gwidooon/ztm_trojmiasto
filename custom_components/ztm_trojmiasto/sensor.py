"""Sensors exposed by the integration."""

from __future__ import annotations

from datetime import datetime
import html
from typing import Any

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from .const import (
    ATTR_DEPARTURES,
    CONF_LINE_ID,
    CONF_LINE_NAME,
    CONF_LINE_TYPE,
    CONF_MAX_DEPARTURES,
    CONF_STOP_CODE,
    CONF_STOP_ID,
    CONF_STOP_NAME,
    CONF_STOP_TYPE,
    CONF_STOP_ZONE,
    DEFAULT_MAX_DEPARTURES,
    DOMAIN,
)
from .coordinator import DepartureInfo, ZtmTrojmiastoDataUpdateCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up ZTM Trojmiasto sensors."""
    coordinator: ZtmTrojmiastoDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        [
            ZtmTrojmiastoCountdownSensor(coordinator, entry),
            ZtmTrojmiastoBoardSensor(coordinator, entry),
        ]
    )


class ZtmTrojmiastoBaseSensor(
    CoordinatorEntity[ZtmTrojmiastoDataUpdateCoordinator],
    SensorEntity,
):
    """Shared base entity for both sensors."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: ZtmTrojmiastoDataUpdateCoordinator,
        entry: ConfigEntry,
    ) -> None:
        super().__init__(coordinator)
        self._entry = entry
        self._stop_id = int(entry.data[CONF_STOP_ID])
        self._line_id = entry.data.get(CONF_LINE_ID)
        self._line_name = entry.data.get(CONF_LINE_NAME)
        self._line_type = entry.data.get(CONF_LINE_TYPE)
        self._stop_type = entry.data.get(CONF_STOP_TYPE)

    @property
    def device_info(self) -> dict[str, Any]:
        """Return device metadata."""
        return {
            "identifiers": {(DOMAIN, self._entry.entry_id)},
            "name": self._entry.title,
            "manufacturer": "ZTM Trojmiasto",
            "model": "Realtime departures",
        }

    @property
    def icon(self) -> str:
        """Choose an icon based on transport type."""
        return _icon_for_type(self._line_type or self._stop_type)

    def _next_departure(self) -> DepartureInfo | None:
        """Return the next departure if available."""
        if not self.coordinator.data.departures:
            return None
        return self.coordinator.data.departures[0]

    def _departure_attributes(self) -> dict[str, Any]:
        """Build detailed attributes."""
        now = dt_util.utcnow()
        limit = self._entry.options.get(CONF_MAX_DEPARTURES, DEFAULT_MAX_DEPARTURES)
        departures = [
            _serialize_departure(departure, now)
            for departure in self.coordinator.data.departures[:limit]
        ]

        attributes: dict[str, Any] = {
            "stop_id": self._stop_id,
            "stop_name": self._entry.data.get(CONF_STOP_NAME),
            "stop_code": self._entry.data.get(CONF_STOP_CODE),
            "stop_zone": self._entry.data.get(CONF_STOP_ZONE),
            "line_id": self._line_id,
            "line": self._line_name,
            "line_type": self._line_type,
            "last_update": (
                self.coordinator.data.last_update.isoformat()
                if self.coordinator.data.last_update
                else None
            ),
            "departure_count": len(self.coordinator.data.departures),
            ATTR_DEPARTURES: departures,
            "markdown_table": _build_markdown_table(
                self.coordinator.data.departures[:limit],
                now,
            ),
        }

        next_departure = self._next_departure()
        if next_departure is not None:
            attributes["next_departure_at"] = next_departure.estimated_time.isoformat()
            attributes["next_headsign"] = next_departure.headsign
            attributes["next_status"] = next_departure.status
            attributes["next_countdown"] = next_departure.countdown_label(now)

        return attributes


class ZtmTrojmiastoCountdownSensor(ZtmTrojmiastoBaseSensor):
    """Numeric countdown sensor."""

    _attr_name = "Next departure"
    _attr_native_unit_of_measurement = UnitOfTime.MINUTES
    _attr_device_class = SensorDeviceClass.DURATION
    _attr_suggested_display_precision = 0

    def __init__(
        self,
        coordinator: ZtmTrojmiastoDataUpdateCoordinator,
        entry: ConfigEntry,
    ) -> None:
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{entry.entry_id}_countdown"

    @property
    def native_value(self) -> int | None:
        """Return minutes until the next departure."""
        next_departure = self._next_departure()
        if next_departure is None:
            return None
        return next_departure.countdown_minutes(dt_util.utcnow())

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return state attributes."""
        return self._departure_attributes()


class ZtmTrojmiastoBoardSensor(ZtmTrojmiastoBaseSensor):
    """String sensor with a compact board summary."""

    _attr_name = "Departures board"

    def __init__(
        self,
        coordinator: ZtmTrojmiastoDataUpdateCoordinator,
        entry: ConfigEntry,
    ) -> None:
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{entry.entry_id}_board"

    @property
    def native_value(self) -> str:
        """Return a compact summary of the next departures."""
        departures = self.coordinator.data.departures
        if not departures:
            return "No departures"

        now = dt_util.utcnow()
        parts: list[str] = []
        for departure in departures[:3]:
            label = departure.countdown_label(now)
            if self._line_id is None:
                parts.append(f"{departure.route_short_name} {label}")
            else:
                parts.append(label)
        return " | ".join(parts)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return state attributes."""
        return self._departure_attributes()


def _serialize_departure(departure: DepartureInfo, now) -> dict[str, Any]:
    """Convert a departure dataclass to sensor attributes."""
    return {
        "line": departure.route_short_name,
        "route_id": departure.route_id,
        "headsign": departure.headsign,
        "status": departure.status,
        "countdown_minutes": departure.countdown_minutes(now),
        "countdown": departure.countdown_label(now),
        "departure_at": departure.estimated_time.isoformat(),
        "scheduled_at": (
            departure.theoretical_time.isoformat()
            if departure.theoretical_time is not None
            else None
        ),
        "prediction_timestamp": (
            departure.timestamp.isoformat()
            if departure.timestamp is not None
            else None
        ),
        "delay_seconds": departure.delay_seconds,
        "vehicle_code": departure.vehicle_code,
        "vehicle_id": departure.vehicle_id,
        "vehicle_service": departure.vehicle_service,
    }


def _build_markdown_table(
    departures: tuple[DepartureInfo, ...] | list[DepartureInfo],
    now: datetime,
) -> str:
    """Build a Markdown table for the HA markdown card."""
    if not departures:
        return "<p>Brak odjazdow.</p>"

    rows = [
        (
            _escape_markdown_cell(departure.route_short_name),
            _escape_markdown_cell(departure.headsign or "-"),
            _format_departure_time(departure.estimated_time),
            departure.countdown_label(now),
            "RT" if departure.status == "REALTIME" else "Rozklad",
            _format_delay(departure.delay_seconds),
        )
        for departure in departures
    ]

    table = [
        "<table>",
        "<thead>",
        "<tr>",
        "<th>Linia</th>",
        "<th>Kierunek</th>",
        "<th>Odjazd</th>",
        "<th>Za ile</th>",
        "<th>Status</th>",
        "<th>Opoznienie</th>",
        "</tr>",
        "</thead>",
        "<tbody>",
    ]

    for line, headsign, departure_at, countdown, status, delay in rows:
        table.extend(
            [
                "<tr>",
                f"<td>{line}</td>",
                f"<td>{headsign}</td>",
                f"<td>{html.escape(departure_at)}</td>",
                f"<td>{html.escape(countdown)}</td>",
                f"<td>{html.escape(status)}</td>",
                f"<td>{html.escape(delay)}</td>",
                "</tr>",
            ]
        )

    table.extend(["</tbody>", "</table>"])
    return "\n".join(table)


def _format_departure_time(value: datetime) -> str:
    """Format time in local timezone for dashboard display."""
    return dt_util.as_local(value).strftime("%H:%M")


def _format_delay(delay_seconds: int | None) -> str:
    """Format delay column for the markdown table."""
    if delay_seconds is None:
        return "-"

    if delay_seconds == 0:
        return "0 min"

    minutes = abs(delay_seconds) // 60
    seconds = abs(delay_seconds) % 60
    sign = "+" if delay_seconds > 0 else "-"

    if minutes == 0:
        return f"{sign}{seconds}s"

    if seconds == 0:
        return f"{sign}{minutes} min"

    return f"{sign}{minutes} min {seconds}s"


def _escape_markdown_cell(value: str) -> str:
    """Escape markdown table cell content."""
    return html.escape(value.replace("\n", " ").strip())


def _icon_for_type(route_type: str | None) -> str:
    """Map transport type to an icon."""
    mapping = {
        "BUS": "mdi:bus-clock",
        "TRAM": "mdi:tram",
        "TROLLEYBUS": "mdi:bus-electric",
    }
    return mapping.get((route_type or "").upper(), "mdi:bus-clock")
