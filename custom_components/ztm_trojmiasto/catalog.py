"""Static catalog handling for stops and lines."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime
import re
import unicodedata

from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.util import dt as dt_util

from .api import ZtmTrojmiastoApiClient, ZtmTrojmiastoApiError
from .const import CATALOG_TTL, DOMAIN, MAX_STOP_MATCHES


def _normalize(value: str) -> str:
    """Normalize text for search."""
    normalized = unicodedata.normalize("NFKD", value)
    without_marks = "".join(
        character
        for character in normalized
        if not unicodedata.combining(character)
    )
    return without_marks.casefold().strip()


def _natural_key(value: str) -> tuple[object, ...]:
    """Create a natural sort key for route names."""
    parts = re.findall(r"\d+|\D+", value or "")
    return tuple(int(part) if part.isdigit() else part.casefold() for part in parts)


def _extract_collection(payload: dict, key: str) -> list[dict]:
    """Extract a collection from the dated CKAN payload."""
    if key in payload and isinstance(payload[key], list):
        return payload[key]

    for value in payload.values():
        if isinstance(value, dict) and key in value and isinstance(value[key], list):
            return value[key]

    raise ZtmTrojmiastoApiError(f"Collection {key} not found in payload")


@dataclass(frozen=True, slots=True)
class StopInfo:
    """Stop details used by the config flow."""

    stop_id: int
    code: str
    name: str
    description: str
    sub_name: str
    zone_name: str
    stop_type: str
    latitude: float | None
    longitude: float | None

    @property
    def label(self) -> str:
        """Friendly label for a selector."""
        base = self.description or self.name
        if self.sub_name:
            base = f"{base} {self.sub_name}"
        return f"{base} [{self.stop_id}]"


@dataclass(frozen=True, slots=True)
class RouteInfo:
    """Route details used by the config flow."""

    route_id: int
    short_name: str
    long_name: str
    route_type: str

    @property
    def label(self) -> str:
        """Friendly label for a selector."""
        type_label = self.route_type or "UNKNOWN"
        if self.long_name:
            return f"{self.short_name} | {type_label} | {self.long_name}"
        return f"{self.short_name} | {type_label}"


@dataclass(slots=True)
class ZtmTrojmiastoCatalog:
    """Static catalog cached in Home Assistant."""

    fetched_at: datetime
    stops_by_id: dict[int, StopInfo]
    routes_by_id: dict[int, RouteInfo]
    stop_routes: dict[int, tuple[int, ...]]

    def search_stops(self, query: str, limit: int = MAX_STOP_MATCHES) -> list[StopInfo]:
        """Search stops by id, name or description."""
        normalized_query = _normalize(query)
        if not normalized_query:
            return []

        matches: list[tuple[int, str, str, StopInfo]] = []
        query_tokens = normalized_query.split()

        for stop in self.stops_by_id.values():
            description = stop.description or stop.name
            searchable = " ".join(
                part
                for part in [
                    str(stop.stop_id),
                    stop.code,
                    stop.name,
                    description,
                    stop.sub_name,
                    stop.zone_name,
                ]
                if part
            )
            normalized_searchable = _normalize(searchable)
            if not all(token in normalized_searchable for token in query_tokens):
                continue

            normalized_description = _normalize(description)
            normalized_name = _normalize(stop.name)
            score = 4

            if normalized_query == str(stop.stop_id):
                score = 0
            elif normalized_description == normalized_query or normalized_name == normalized_query:
                score = 1
            elif normalized_description.startswith(normalized_query):
                score = 2
            elif normalized_name.startswith(normalized_query):
                score = 3

            matches.append((score, normalized_description, stop.sub_name, stop))

        matches.sort(key=lambda item: item[:3])
        return [match[3] for match in matches[:limit]]

    def routes_for_stop(self, stop_id: int) -> list[RouteInfo]:
        """Return all routes serving a stop."""
        route_ids = self.stop_routes.get(stop_id, ())
        routes = [
            self.routes_by_id[route_id]
            for route_id in route_ids
            if route_id in self.routes_by_id
        ]
        return sorted(routes, key=lambda route: _natural_key(route.short_name))


async def async_get_catalog(hass: HomeAssistant) -> ZtmTrojmiastoCatalog:
    """Return a cached static catalog."""
    domain_data = hass.data.setdefault(DOMAIN, {})
    lock = domain_data.setdefault("_catalog_lock", asyncio.Lock())

    async with lock:
        cached_catalog: ZtmTrojmiastoCatalog | None = domain_data.get("catalog")
        if (
            cached_catalog is not None
            and dt_util.utcnow() - cached_catalog.fetched_at < CATALOG_TTL
        ):
            return cached_catalog

        client = ZtmTrojmiastoApiClient(async_get_clientsession(hass))
        stops_payload, routes_payload, stops_in_trip_payload = await asyncio.gather(
            client.async_get_stops(),
            client.async_get_routes(),
            client.async_get_stops_in_trip(),
        )

        catalog = ZtmTrojmiastoCatalog(
            fetched_at=dt_util.utcnow(),
            stops_by_id=_build_stops_index(stops_payload),
            routes_by_id=_build_routes_index(routes_payload),
            stop_routes=_build_stop_routes_index(stops_in_trip_payload),
        )
        domain_data["catalog"] = catalog
        return catalog


def _build_stops_index(payload: dict) -> dict[int, StopInfo]:
    """Build stop index from the static file."""
    stops: dict[int, StopInfo] = {}

    for item in _extract_collection(payload, "stops"):
        stop_id = int(item["stopId"])
        stops[stop_id] = StopInfo(
            stop_id=stop_id,
            code=str(item.get("stopCode") or ""),
            name=str(item.get("stopName") or ""),
            description=str(item.get("stopDesc") or item.get("stopName") or ""),
            sub_name=str(item.get("subName") or ""),
            zone_name=str(item.get("zoneName") or ""),
            stop_type=str(item.get("type") or "UNKNOWN"),
            latitude=item.get("stopLat"),
            longitude=item.get("stopLon"),
        )

    return stops


def _build_routes_index(payload: dict) -> dict[int, RouteInfo]:
    """Build route index from the static file."""
    routes: dict[int, RouteInfo] = {}

    for item in _extract_collection(payload, "routes"):
        route_id = int(item["routeId"])
        routes[route_id] = RouteInfo(
            route_id=route_id,
            short_name=str(item.get("routeShortName") or route_id),
            long_name=str(item.get("routeLongName") or ""),
            route_type=str(item.get("routeType") or "UNKNOWN"),
        )

    return routes


def _build_stop_routes_index(payload: dict) -> dict[int, tuple[int, ...]]:
    """Build stop -> route mapping from the static file."""
    mapping: dict[int, set[int]] = {}

    for item in _extract_collection(payload, "stopsInTrip"):
        stop_id = int(item["stopId"])
        route_id = int(item["routeId"])
        mapping.setdefault(stop_id, set()).add(route_id)

    return {
        stop_id: tuple(sorted(route_ids))
        for stop_id, route_ids in mapping.items()
    }
