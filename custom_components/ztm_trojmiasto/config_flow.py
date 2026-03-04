"""Config flow for ZTM Trojmiasto."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry, ConfigFlow, OptionsFlow
from homeassistant.core import callback

from .api import ZtmTrojmiastoApiError
from .catalog import RouteInfo, StopInfo, ZtmTrojmiastoCatalog, async_get_catalog
from .const import (
    ALL_LINES,
    CONF_INCLUDE_SCHEDULED,
    CONF_LINE_ID,
    CONF_LINE_LONG_NAME,
    CONF_LINE_NAME,
    CONF_LINE_TYPE,
    CONF_MAX_DEPARTURES,
    CONF_REFRESH_INTERVAL,
    CONF_STOP_CODE,
    CONF_STOP_ID,
    CONF_STOP_NAME,
    CONF_STOP_SEARCH,
    CONF_STOP_TYPE,
    CONF_STOP_ZONE,
    DEFAULT_INCLUDE_SCHEDULED,
    DEFAULT_MAX_DEPARTURES,
    DEFAULT_REFRESH_INTERVAL,
    DOMAIN,
    MAX_REFRESH_INTERVAL,
    MIN_REFRESH_INTERVAL,
)


class ZtmTrojmiastoConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for the integration."""

    VERSION = 1

    def __init__(self) -> None:
        self._catalog: ZtmTrojmiastoCatalog | None = None
        self._stop_matches: list[StopInfo] = []
        self._selected_stop: StopInfo | None = None

    async def async_step_user(self, user_input: dict[str, Any] | None = None):
        """Ask for a stop search phrase."""
        errors: dict[str, str] = {}

        if user_input is not None:
            try:
                self._catalog = await async_get_catalog(self.hass)
            except ZtmTrojmiastoApiError:
                errors["base"] = "cannot_connect"
            else:
                self._stop_matches = self._catalog.search_stops(user_input[CONF_STOP_SEARCH])
                if not self._stop_matches:
                    errors["base"] = "no_stops_found"
                elif len(self._stop_matches) == 1:
                    self._selected_stop = self._stop_matches[0]
                    return await self.async_step_select_line()
                else:
                    return await self.async_step_select_stop()

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_STOP_SEARCH): str,
                }
            ),
            errors=errors,
        )

    async def async_step_select_stop(self, user_input: dict[str, Any] | None = None):
        """Select a stop from search results."""
        if not self._stop_matches:
            return await self.async_step_user()

        if user_input is not None:
            selected_stop_id = int(user_input[CONF_STOP_ID])
            self._selected_stop = next(
                (stop for stop in self._stop_matches if stop.stop_id == selected_stop_id),
                None,
            )
            if self._selected_stop is None:
                return await self.async_step_user()
            return await self.async_step_select_line()

        options = {str(stop.stop_id): stop.label for stop in self._stop_matches}
        return self.async_show_form(
            step_id="select_stop",
            data_schema=vol.Schema({vol.Required(CONF_STOP_ID): vol.In(options)}),
        )

    async def async_step_select_line(self, user_input: dict[str, Any] | None = None):
        """Select a line served by the selected stop."""
        errors: dict[str, str] = {}

        if self._catalog is None:
            self._catalog = await async_get_catalog(self.hass)

        if self._selected_stop is None:
            return await self.async_step_user()

        routes = self._catalog.routes_for_stop(self._selected_stop.stop_id)
        if not routes:
            return self.async_show_form(
                step_id="select_line",
                data_schema=self._line_schema(routes),
                errors={"base": "no_lines_found"},
            )

        if user_input is not None:
            selected_value = user_input[CONF_LINE_ID]
            route = None
            if selected_value != ALL_LINES:
                route = next(
                    (
                        candidate
                        for candidate in routes
                        if candidate.route_id == int(selected_value)
                    ),
                    None,
                )
                if route is None:
                    return await self.async_step_select_line()

            unique_id = _build_unique_id(self._selected_stop.stop_id, route)
            await self.async_set_unique_id(unique_id)
            self._abort_if_unique_id_configured()

            data = {
                CONF_STOP_ID: self._selected_stop.stop_id,
                CONF_STOP_NAME: self._selected_stop.description or self._selected_stop.name,
                CONF_STOP_CODE: self._selected_stop.code,
                CONF_STOP_TYPE: self._selected_stop.stop_type,
                CONF_STOP_ZONE: self._selected_stop.zone_name,
                CONF_LINE_ID: None if route is None else route.route_id,
                CONF_LINE_NAME: "All lines" if route is None else route.short_name,
                CONF_LINE_LONG_NAME: "" if route is None else route.long_name,
                CONF_LINE_TYPE: self._selected_stop.stop_type if route is None else route.route_type,
            }
            options = {
                CONF_MAX_DEPARTURES: user_input[CONF_MAX_DEPARTURES],
                CONF_INCLUDE_SCHEDULED: user_input[CONF_INCLUDE_SCHEDULED],
                CONF_REFRESH_INTERVAL: user_input[CONF_REFRESH_INTERVAL],
            }

            return self.async_create_entry(
                title=_build_entry_title(self._selected_stop, route),
                data=data,
                options=options,
            )

        return self.async_show_form(
            step_id="select_line",
            data_schema=self._line_schema(routes),
            errors=errors,
        )

    def _line_schema(self, routes: list[RouteInfo]) -> vol.Schema:
        """Return schema for line selection step."""
        options = {ALL_LINES: "All lines"}
        options.update({str(route.route_id): route.label for route in routes})

        return vol.Schema(
            {
                vol.Required(CONF_LINE_ID): vol.In(options),
                vol.Required(
                    CONF_MAX_DEPARTURES,
                    default=DEFAULT_MAX_DEPARTURES,
                ): vol.All(vol.Coerce(int), vol.Range(min=1, max=10)),
                vol.Required(
                    CONF_INCLUDE_SCHEDULED,
                    default=DEFAULT_INCLUDE_SCHEDULED,
                ): bool,
                vol.Required(
                    CONF_REFRESH_INTERVAL,
                    default=DEFAULT_REFRESH_INTERVAL,
                ): vol.All(
                    vol.Coerce(int),
                    vol.Range(min=MIN_REFRESH_INTERVAL, max=MAX_REFRESH_INTERVAL),
                ),
            }
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        """Return the options flow."""
        return ZtmTrojmiastoOptionsFlow(config_entry)


class ZtmTrojmiastoOptionsFlow(OptionsFlow):
    """Handle options for an existing entry."""

    def __init__(self, config_entry: ConfigEntry) -> None:
        self._config_entry = config_entry

    async def async_step_init(self, user_input: dict[str, Any] | None = None):
        """Manage the integration options."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_MAX_DEPARTURES,
                        default=self._config_entry.options.get(
                            CONF_MAX_DEPARTURES,
                            DEFAULT_MAX_DEPARTURES,
                        ),
                    ): vol.All(vol.Coerce(int), vol.Range(min=1, max=10)),
                    vol.Required(
                        CONF_INCLUDE_SCHEDULED,
                        default=self._config_entry.options.get(
                            CONF_INCLUDE_SCHEDULED,
                            DEFAULT_INCLUDE_SCHEDULED,
                        ),
                    ): bool,
                    vol.Required(
                        CONF_REFRESH_INTERVAL,
                        default=self._config_entry.options.get(
                            CONF_REFRESH_INTERVAL,
                            DEFAULT_REFRESH_INTERVAL,
                        ),
                    ): vol.All(
                        vol.Coerce(int),
                        vol.Range(min=MIN_REFRESH_INTERVAL, max=MAX_REFRESH_INTERVAL),
                    ),
                }
            ),
        )


def _build_unique_id(stop_id: int, route: RouteInfo | None) -> str:
    """Build unique id for the config entry."""
    line_part = "all" if route is None else str(route.route_id)
    return f"{stop_id}:{line_part}"


def _build_entry_title(stop: StopInfo, route: RouteInfo | None) -> str:
    """Build a user friendly entry title."""
    stop_name = stop.description or stop.name
    if stop.sub_name:
        stop_name = f"{stop_name} {stop.sub_name}"
    if route is None:
        return f"{stop_name} - all lines"
    return f"{stop_name} - line {route.short_name}"
