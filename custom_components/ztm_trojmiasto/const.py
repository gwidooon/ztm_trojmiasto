"""Constants for the ZTM Trojmiasto integration."""

from __future__ import annotations

from datetime import timedelta

from homeassistant.const import Platform

DOMAIN = "ztm_trojmiasto"
NAME = "ZTM Trojmiasto Departures"

PLATFORMS: list[Platform] = [Platform.SENSOR]

CONF_STOP_SEARCH = "stop_search"
CONF_STOP_ID = "stop_id"
CONF_STOP_NAME = "stop_name"
CONF_STOP_CODE = "stop_code"
CONF_STOP_TYPE = "stop_type"
CONF_STOP_ZONE = "stop_zone"
CONF_LINE_ID = "line_id"
CONF_LINE_NAME = "line_name"
CONF_LINE_TYPE = "line_type"
CONF_LINE_LONG_NAME = "line_long_name"
CONF_INCLUDE_SCHEDULED = "include_scheduled"
CONF_MAX_DEPARTURES = "max_departures"
CONF_REFRESH_INTERVAL = "refresh_interval"

DEFAULT_MAX_DEPARTURES = 5
DEFAULT_INCLUDE_SCHEDULED = True
DEFAULT_REFRESH_INTERVAL = 20

MIN_REFRESH_INTERVAL = 20
MAX_REFRESH_INTERVAL = 120
MAX_STOP_MATCHES = 25

ALL_LINES = "__all__"
CATALOG_TTL = timedelta(hours=12)

ATTR_DEPARTURES = "departures"
