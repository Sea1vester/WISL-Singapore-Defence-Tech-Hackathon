# SDTH Telemetry Platform

Mac-first drone telemetry platform: ingest normalized JSON (via Tailscale), store in SQLite, translate to canonical JSON with local Ollama/DeepSeek.

## Progress

Pivoted from cloud-hosted to laptop-hosted for now. Azure requires credits and I cant register to Oracle.
The platform runs on my Mac via Docker; ya'll reach it over **Tailscale**.

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
- Do not send raw binary/logs to this endpoint - only normalized JSON.
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

Generate an incident report for a flight using the local LLM:

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

### 7. API reference

Full contract: `openapi/openapi.yaml`

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

## Azure (later)

Same `docker-compose.yml` deploys to an Azure VM in the final hackathon month. No code changes expected.
