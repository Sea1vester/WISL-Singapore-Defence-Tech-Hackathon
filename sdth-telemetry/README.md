# SDTH Telemetry Platform

FastAPI platform for recorded drone logs: raw-log upload, SQLite storage, canonical L2 projection, deterministic incident detectors, an evidence query engine, comprehensive PDF reports, and optional local-model (Ollama) analysis.

Parsers and `persist_canonical_series` write canonical JSON.
Ollama/DeepSeek is optional enrichment for incident write-ups, not the normalizer.

## Run locally

From the repository root (Python 3.11+):

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -e './sdth-telemetry/platform-api[dev]'
./sdth-telemetry/scripts/demo-console.sh
```

The launcher opens the console at <http://127.0.0.1:8010/demo/>, runs the API and one background ingestion worker on loopback, and uses SQLite. Redis is not needed for this path.

Azure is not used.

### Legacy: Docker Compose + two-laptop

An earlier setup ran the stack under Docker Compose with a Redis queue and served a second laptop over Tailscale. That path still works but is not the submitted demo; see [`docs/two-laptop-demo.md`](docs/two-laptop-demo.md).

## Raw-log path

- `POST /v1/logs/upload` — multipart raw upload (field `file`), SHA-256 integrity header, extension/size gate.
- `GET /v1/uploads/{upload_id}` — processing status.

The registry accepts thirteen extensions: `.bin`, `.csv`, `.hex`, `.hermes`, `.json`, `.ros`, `.stanag`, `.syslog`, `.tlog`, `.ulg`, `.ulog`, `.xlsx`, `.xml`.

SHA-256 de-duplication is global: a repeated digest returns the existing upload rather than a second raw object.

## Canonical L2

Parsed L1 records are projected into a validated canonical L2 series:

- `flight_id`, `timestamp_utc` (ISO-8601 UTC)
- `position`: `lat`, `lon`, `alt_m` (missing coordinates projected from a reference origin and marked `frame: local_ned`)
- `attitude`: `roll`, `pitch`, `yaw` in degrees
- `battery`: state-of-charge percent and `voltage_v`
- `sensors`, `metadata` sub-objects (`source`, `frame`, `value_origin`)
- Operator home coordinates are redacted before persistence. Canonical JSONL is exportable.

## Detectors

Deterministic detectors run on L2 only:

| Detector type | Monitored condition | Demonstration threshold |
|---|---|---|
| `battery_low` / `battery_critical` | Low remaining state of charge | 20% warn / 10% critical |
| `battery_plunge` | Sudden capacity drop | 15 percentage points in 60 s |
| `telemetry_gap` | Telemetry silence / dropout | 15 s silence |
| `attitude_shock` | Attitude tumbling / shock | 40° warn / 70° critical |
| `gps_jump` | Implied horizontal / vertical velocity jump | 120 m/s air, 15 m/s ground; 25 m step or 20 m/s vertical |
| `last_known_position` | Frozen vehicle track | ~30 s unchanging pose |
| `mission_incomplete` | Incomplete flight termination | Mode check / end-of-log status |
| `operator_warning` | In-flight telemetry warning text | Keyword match on GPS, failsafe, motor, compass, return-to-home, link-lost text |

## API surface

- Ingest: `POST /v1/logs/upload`, `GET /v1/uploads/{id}`, `POST /v1/telemetry/ingest` (legacy structured-JSON route), `GET /v1/ingest/{id}/status`
- Flights and records: `GET /v1/flights`, `GET /v1/flights/{id}`, `GET /v1/flights/{id}/records`, `GET /v1/flights/{id}/path`, `GET /v1/export/flights/{id}.jsonl`
- Incidents and fleet: `POST /v1/flights/{id}/index-incidents`, `GET /v1/flights/{id}/incidents`, `GET /v1/incidents/patterns`, `GET /v1/reliability`, `GET /v1/hardware/brands`, `POST`/`GET /v1/mitigation-bulletins`, `POST`/`GET /v1/flights/{id}/incident-report`
- Console demo: `GET /v1/demo/status`, `POST /v1/demo/query`, `POST /v1/demo/analysis`
- Comprehensive report: `POST /v1/flights/{id}/comprehensive-report`, `GET /v1/comprehensive-reports/{id}/file`

Full contract: `openapi/openapi.yaml`.

## Parsers CLI

Parsers also run standalone (needs `parsers/requirements.txt`, including `pyulog`):

```bash
cd sdth-telemetry
PYTHONPATH=. python -m parsers dji ../raw_telemetry-datasets/dji.csv -o normalized/dji_l1.json
PYTHONPATH=. python -m parsers ulg ../raw_telemetry-datasets/<file>.ulg -o normalized/ulg_l1.json --stride 5
PYTHONPATH=. python -m parsers bin ../raw_telemetry-datasets/sample_crash_log.bin -o normalized/crash_l1.json
PYTHONPATH=. python -m parsers tlog ../raw_telemetry-datasets/flight.tlog -o normalized/tlog_l1.json
PYTHONPATH=. python -m parsers excel path/to/flight.xlsx -o normalized/excel_l1.json
PYTHONPATH=. python -m parsers path normalized/dji_l1.json -o normalized/dji_path.json
PYTHONPATH=. python -m parsers detect ../raw_telemetry-datasets/dji.csv
```

Local-NED-only logs are projected to lat/lon using a reference origin (`--origin-lat/lon`). The `path` command emits the stable replay contract consumed by `GET /v1/flights/{id}/path`.

## Tests

```bash
cd platform-api && pytest
cd .. && pytest parsers/tests
```
