# SDTH Telemetry Platform

Mac-first drone telemetry platform: ingest recorded vendor logs (via Tailscale), store in SQLite, normalize to canonical L2 JSON, index incidents, and serve Cesium replay.

Parsers and `persist_canonical_series` write canonical JSON.
Ollama/DeepSeek is optional enrichment for incident write-ups, not the normalizer.

## Progress

The platform runs on a laptop via Docker. Teammates reach the HTTP API over **Tailscale**.
Azure is not used. Tailscale is private transport, not accreditation.

The supported demo is recorded-log upload from Laptop A to Laptop B.
See [`docs/two-laptop-demo.md`](docs/two-laptop-demo.md).

The checked demo fixtures are `fixtures/demo/controller_mission_alpha.csv` and `controller_mission_bravo.csv`.
Both raise `operator_warning` with evidence `GPS signal weak`.
A second flight makes the signature show up on `/v1/incidents/patterns?min_flights=2`.

Vision is a sidecar: [`sdth-vision`](../sdth-vision/README.md) posts `camera_frame` visuals and `frame_census`.
The API does not run YOLO.

**Important:** nobody connects to SQLite directly.
Yall both use the HTTP API.
SQLite is DB behind the API.

---

## For Isaac

### 1. Join the tailnet

1. Install [Tailscale](https://tailscale.com/download) and sign in with an account. I'll invite you.
2. Confirm you can reach the API:

```bash
curl http://MyIPAddress/health
```

Expected: `{"status":"ok"}`

If that fails, ping me - the Docker stack may be down or your machine is not on the same tailnet. Ask me for my ip address

### 2. Credentials

I will share an **API key** out of band (not in this repo).
Use it on every request as either:

- `Authorization: Bearer <API_KEY>`, or
- `X-API-Key: <API_KEY>`

### 3. Ingest endpoint

**POST** `http://MyIPAddress:8000/v1/telemetry/ingest`

**Content-Type:** `application/json`

**Body shape** (see `fixtures/sample_l1.json` and `openapi/openapi.yaml`):

| Field | Required | Notes |
|-------|----------|-------|
| `flight_id` | yes | Stable UUID for this flight/session |
| `timestamp_utc` | yes | ISO-8601, e.g. `2026-07-11T10:00:00Z` |
| `source` | yes | Your parser name, e.g. `isaac-mavlink-parser` |
| `event_id` | recommended | Unique per batch; retries with the same id are deduplicated |
| `records` | yes | Array of normalized telemetry objects (flexible keys) |

**Example:**

```bash
curl -X POST http://100.109.81.33:8000/v1/telemetry/ingest \
  -H "Authorization: Bearer <API_KEY>" \
  -H "Content-Type: application/json" \
  -d @fixtures/sample_l1.json
```

**Response (202):**

```json
{
  "ingest_id": "...",
  "job_id": "...",
  "status": "accepted"
}
```

### 4. Optional: check translation status

Translation runs async (~15-40s per batch while Ollama is warm).

```bash
curl -H "Authorization: Bearer <API_KEY>" \
  http://100.109.81.33:8000/v1/ingest/<ingest_id>/status
```

Statuses: `pending` → `running` → `done` (or `failed` with an `error` field).

### 5. What you do not need to do

- Do not install SQLite or connect to the database file.
- Send normalized JSON to `/v1/telemetry/ingest`.
- Send supported raw logs as multipart field `file` to `/v1/logs/upload`.
- Field naming inside `records[]` can be negotiated; unknown fields are preserved under `sensors.extra` in L2.

---

## For Inessa 

### 1. Join the tailnet

install Tailscale and verify:

```bash
curl http://MyIPAddress/health
```

### 2. Credentials

Same API key as Isaac.

### 3. List flights

```bash
curl -H "Authorization: Bearer <API_KEY>" \
  http://MyIPAddress:8000/v1/flights
```

Returns flight summaries with `id`, `source`, `started_at`, etc.
Use `id` as `flight_id` in the next calls.

### 4. Get canonical records for a flight

```bash
curl -H "Authorization: Bearer <API_KEY>" \
  "http://MyIPAddress:8000/v1/flights/<flight_id>/records"
```

Each item has a `canonical_json` object (L2) with fixed fields:

- `position` (`lat`, `lon`, `alt_m`)
- `attitude` (`roll_deg`, `pitch_deg`, `yaw_deg`)
- `battery` (`percent`, `voltage_v`)
- `sensors` (extra fields from L1)
- `metadata`

**Time filters** (optional query params):

```bash
curl -H "Authorization: Bearer <API_KEY>" \
  "http://MyIPAddress:8000/v1/flights/<flight_id>/records?from=2026-07-11T10:00:00Z&to=2026-07-11T11:00:00Z"
```

Records only appear after the translation job is `done`.
If the list is empty, check ingest status with Isaac or ask Sylvester to confirm the worker is running.

### 5. Bulk export (JSONL)

One canonical JSON object per line - good for scripts or ML pipelines:

```bash
curl -H "Authorization: Bearer <API_KEY>" \
  http://MyIPAddress:8000/v1/export/flights/<flight_id>.jsonl \
  -o flight.jsonl
```

### 6. AI Analytics (Phase 4)

Generate an incident report for a flight using the local LLM.
The report is also stored in SQLite as an `llm_report` incident.

```bash
curl -X POST -H "Authorization: Bearer <API_KEY>" \
  http://MyIPAddress:8000/v1/flights/<flight_id>/incident-report
```

Ask natural language questions about the telemetry:

```bash
curl -X POST -H "Authorization: Bearer <API_KEY>" \
  -H "Content-Type: application/json" \
  -d '{"query": "Show me the battery drop rate"}' \
  http://MyIPAddress:8000/v1/flights/<flight_id>/chat
```

### 7. Incident index (SQLite)

Rule detectors run on L2-shaped JSON only (position, attitude, battery, sensors).
Vendor packets are never read directly.
Thresholds are physics/ops bands (low battery, altitude spike, GPS jump, attitude shock, telemetry gap).
The live demo signature is `operator_warning` from APP.warning keywords, not a battery incident.

Index a flight after ingest (also runs automatically when translation finishes):

```bash
curl -X POST -H "Authorization: Bearer <API_KEY>" \
  http://MyIPAddress:8000/v1/flights/<flight_id>/index-incidents
```

List incidents for a flight, recurring patterns across missions, and per-brand reliability:

```bash
curl -H "Authorization: Bearer <API_KEY>" \
  http://MyIPAddress:8000/v1/flights/<flight_id>/incidents

curl -H "Authorization: Bearer <API_KEY>" \
  http://MyIPAddress:8000/v1/incidents/patterns?min_flights=2

curl -H "Authorization: Bearer <API_KEY>" \
  http://MyIPAddress:8000/v1/reliability

curl -H "Authorization: Bearer <API_KEY>" \
  http://MyIPAddress:8000/v1/hardware/brands
```

Hardware brands currently in the log set, cheap/COTS first: DJI, PX4/Auterion, ArduPilot. Elbit Hermes 900, Aeronautics Orbiter 4, and aunav.NEO HD (Taurus UGV) remain supported as legacy entries, not the target segment.

### 8. API reference

Full contract: `openapi/openapi.yaml`

---

## Two-laptop demo

Use [`docs/two-laptop-demo.md`](docs/two-laptop-demo.md) for the Tailscale setup, Laptop A and Laptop B launchers, troubleshooting, and the same-laptop fallback.

The demo-facing workflow uses:

- `POST /v1/logs/upload` for a raw multipart upload.
- `GET /v1/uploads/{upload_id}` for raw-log processing status.
- `GET /v1/ingest/{ingest_id}/status` for normalized-ingest translation status.
- `GET /v1/flights/{flight_id}/path` for visualization-ready flight path data.
- `POST /v1/flights/{flight_id}/index-incidents` and `GET /v1/flights/{flight_id}/incidents` for incident analysis.
- `POST /v1/flights/{flight_id}/incident-report` for the local-LLM report.
- `POST /v1/flights/{flight_id}/visuals?kind=camera_frame` to store a JPEG against a flight.
- `POST /v1/flights/{flight_id}/census` and `GET /v1/flights/{flight_id}/census` for HUD counts.

The launchers assume these contracts even when the raw-upload backend is being implemented concurrently.
Their raw upload and status paths can be overridden with environment variables.

The demo is limited to recorded logs.
Live airframe/GCS connections, onboard or edge inference, globe-projected boxes, microburst/EW/LPI functionality, automated fleet fixes, accreditation, Azure, and Orcrist are explicitly deferred.

---

## Quick start (Sylvester)

### Prerequisites

- Docker Desktop
- Ollama on your Mac: `brew install ollama && ollama pull deepseek-r1:7b`
- Keep Ollama running (Docker worker calls `http://host.docker.internal:11434`)
- Tailscale (already set up)

### Run the stack

```bash
cd sdth-telemetry
cp .env.example .env
docker compose up --build
```

API listens on `http://0.0.0.0:8000` (reachable via Tailscale at `http://$(tailscale ip -4):8000`).

### Normalize raw telemetry → L1 JSON

Cloud-side parsers live in `parsers/`. Prefer the local venv (needs `pyulog` for Step 2):

```bash
cd sdth-telemetry
python3 -m venv .venv
.venv/bin/pip install -r parsers/requirements.txt
```

**Step 1 - DJI FlightRecord CSV**

```bash
PYTHONPATH=. .venv/bin/python -m parsers dji ../raw_telemetry-datasets/dji.csv -o normalized/dji_l1.json
```

**Step 2 - PX4 / Auterion ULog**

```bash
PYTHONPATH=. .venv/bin/python -m parsers ulg ../raw_telemetry-datasets/e0ad253a-a5f5-4883-ab96-56c397fe18ee.ulg -o normalized/e0ad_l1.json
# large logs: downsample
PYTHONPATH=. .venv/bin/python -m parsers ulg ../raw_telemetry-datasets/0ceef477-0523-4e67-9b0a-57310817f1cc.ulg -o normalized/0ceef_l1.json --stride 5
```

Local-NED-only logs (no GPS) are projected to lat/lon using PX4 SITL home by default (`--origin-lat/lon`).

**Step 3 - ArduPilot DataFlash / MAVLink**

```bash
PYTHONPATH=. .venv/bin/python -m parsers bin ../raw_telemetry-datasets/sample_crash_log.bin -o normalized/crash_l1.json
PYTHONPATH=. .venv/bin/python -m parsers tlog ../raw_telemetry-datasets/dronekit-la-testdata-master/flight.tlog -o normalized/flight_tlog_l1.json --stride 5
```

**Step 4 - Excel (.xlsx)**

Routes DJI FlightRecord sheets through the DJI mapper; otherwise expects generic `lat`/`lon`/`alt` columns. Legacy `.xls` is rejected (re-save as `.xlsx`).

```bash
PYTHONPATH=. .venv/bin/python -m parsers excel path/to/flight.xlsx -o normalized/excel_l1.json
PYTHONPATH=. .venv/bin/python -m parsers excel path/to/flight.xlsx -o normalized/excel_l1.json --sheet Sheet1
```

**Step 5 - Path handoff for 3D viz**

Stable contract: `{ contract_version, flight_id, source, frame, units, count, samples[{t, lat, lon, alt_m, ...}] }`.
The Cesium viewer on Laptop B consumes this from `GET /v1/flights/<id>/path` at `http://localhost:8000/replay/`.

Offline from L1 JSON:

```bash
PYTHONPATH=. .venv/bin/python -m parsers path normalized/dji_l1.json -o normalized/dji_path.json
PYTHONPATH=. .venv/bin/python -m parsers path normalized/dji_l1.json -o normalized/dji_path.json --stride 5
```

Live API (prefers L2 canonical; falls back to stored L1 so viz works before LLM translation finishes):

```bash
curl -H "Authorization: Bearer dev-teammate-key-change-me" \
  "http://localhost:8000/v1/flights/<flight_id>/path"

curl -H "Authorization: Bearer dev-teammate-key-change-me" \
  "http://localhost:8000/v1/flights/<flight_id>/path?stride=5&max_samples=5000&prefer=l1"
```

```bash
PYTHONPATH=. .venv/bin/python -m parsers detect ../raw_telemetry-datasets/dji.csv
PYTHONPATH=. .venv/bin/pytest parsers/tests -q
```

Then ingest the generated file (API running):

```bash
curl -X POST http://localhost:8000/v1/telemetry/ingest \
  -H "Authorization: Bearer dev-teammate-key-change-me" \
  -H "Content-Type: application/json" \
  -d @normalized/dji_l1.json
```

### Test ingest locally

Full E2E (ingest + poll translation + show canonical records):

```bash
./scripts/test-ingest.sh
```

Manual ingest:

```bash
curl -X POST http://localhost:8000/v1/telemetry/ingest \
  -H "Authorization: Bearer dev-teammate-key-change-me" \
  -H "Content-Type: application/json" \
  -d @fixtures/sample_l1.json
```

Check job status (use `ingest_id` from response):

```bash
curl -H "Authorization: Bearer dev-teammate-key-change-me" \
  http://localhost:8000/v1/ingest/<ingest_id>/status
```

List flights and records (local):

```bash
curl -H "Authorization: Bearer dev-teammate-key-change-me" \
  http://localhost:8000/v1/flights

curl -H "Authorization: Bearer dev-teammate-key-change-me" \
  http://localhost:8000/v1/flights/<flight_id>/records

curl -H "Authorization: Bearer dev-teammate-key-change-me" \
  "http://localhost:8000/v1/flights/<flight_id>/path"
```

## Architecture

| Component | Role |
|-----------|------|
| FastAPI (`api`) | Ingest + query endpoints |
| Redis | Translation job queue |
| Worker | Pulls jobs, calls Ollama, writes canonical JSON |
| SQLite (`/data/telemetry.db`) | Persistent storage |
| Ollama on Mac host | DeepSeek LLM inference |

## Local development (without Docker)

```bash
cd platform-api
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
redis-server &  # or brew services start redis
uvicorn app.main:app --host 0.0.0.0 --port 8000
python -m app.worker
```

Set `OLLAMA_BASE_URL=http://127.0.0.1:11434` when running outside Docker.

## Azure

Not used.
Same Compose file could run on a VM later.
That is not part of the demo.
