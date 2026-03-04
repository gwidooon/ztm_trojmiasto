# ZTM Trojmiasto Departures for Home Assistant

Custom Home Assistant integration for realtime bus and tram departures from the official ZTM Trojmiasto open data API.

The integration lets you:

- search and pick a stop during config flow,
- choose one line or track all lines from that stop,
- expose a numeric countdown sensor for tiles/widgets,
- expose a board-style summary sensor with the next departures in attributes,
- install the repository directly through HACS as a custom integration.

## Data source

Official ZTM Gdansk / Trojmiasto open data resources:

- realtime departures: `https://ckan2.multimediagdansk.pl/departures?stopId={stopId}`
- stops catalog: `stops.json`
- routes catalog: `routes.json`
- stop-route mapping: `stopsintrip.json`

## Installation with HACS

1. Push this repository to GitHub.
2. In HACS open `Integrations -> Custom repositories`.
3. Add your repository URL and select category `Integration`.
4. Install `ZTM Trojmiasto Departures`.
5. Restart Home Assistant.
6. Open `Settings -> Devices & Services -> Add Integration`.
7. Search for `ZTM Trojmiasto Departures`.

## Configuration flow

1. Search for a stop by name or stop id.
2. Pick the exact stop when more than one match is found.
3. Choose a line or `All lines`.
4. Set refresh interval and how many departures should be exposed in attributes.

Each config entry creates two sensors:

- `Next departure` - numeric countdown in minutes,
- `Departures board` - compact string summary plus structured departure attributes.

## Dashboard example

Example Lovelace card snippet is available in [docs/dashboard.yaml](./docs/dashboard.yaml).

The most useful entity for a tile widget is the `Next departure` sensor. The `Departures board` sensor is useful for an entities card or a markdown card.

Example Markdown card:

```yaml
type: markdown
title: Odjazdy
content: |
  {{ state_attr('sensor.twoja_encja_departures_board', 'markdown_table') }}
```

## Project structure

```text
.
├── custom_components/
│   └── ztm_trojmiasto/
│       ├── __init__.py
│       ├── api.py
│       ├── catalog.py
│       ├── config_flow.py
│       ├── const.py
│       ├── coordinator.py
│       ├── manifest.json
│       ├── sensor.py
│       ├── strings.json
│       └── translations/
│           ├── en.json
│           └── pl.json
├── docs/
│   └── dashboard.yaml
├── .github/workflows/
├── hacs.json
└── README.md
```

Home Assistant loads only the integration files from `custom_components/ztm_trojmiasto`. Documentation, examples and repository automation are kept outside that directory.

## Entities

### Next departure

State:

- number of minutes until the next departure.

Main attributes:

- `next_departure_at`
- `next_headsign`
- `next_status`
- `departures`
- `markdown_table`

### Departures board

State examples:

- `4 min | 17 min | 34 min` for a single line,
- `6 3 min | 12 9 min | N3 14 min` when tracking all lines at a stop.

The `departures` attribute contains a list of structured objects with:

- line number,
- destination,
- realtime/scheduled status,
- countdown,
- predicted departure time,
- schedule time,
- delay in seconds,
- vehicle metadata when available.

The `markdown_table` attribute contains a ready-to-render Markdown table for the Home Assistant Markdown card.

## Local development

Copy `custom_components/ztm_trojmiasto` into your Home Assistant config directory and restart HA.

## Notes

- Repository URL is set to `https://github.com/gwidooon/ztm_trojmiasto`.
- To change the tracked stop or line, remove the entry and add it again. The options flow only changes refresh and display settings.
