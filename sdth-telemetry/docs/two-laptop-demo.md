# Two-Laptop WISL Demo Runbook

> **Legacy / optional path.** The submitted demo runs on one laptop via `./sdth-telemetry/scripts/demo-console.sh` — see [`docs/submission/demo-runbook.md`](../../docs/submission/demo-runbook.md). This document describes the earlier Tailscale two-laptop workflow.

Laptop A simulates a controller by dropping a recorded raw log into a watched directory.
Laptop B receives the file, parses it, normalizes it, detects incidents, and opens the Cesium replay in a browser.
The checked fixtures are two DJI CSVs that both emit `operator_warning` (`GPS signal weak`).

Both laptops should be on the same Tailscale tailnet.
The API stays private to that tailnet. Do not expose it with Tailscale Funnel.

This demo uses recorded logs. It is not a live airframe or GCS connection.

## Before the demo

Laptop B needs Docker Desktop, Tailscale, `curl`, and optionally Ollama with `deepseek-r1:7b`.
Ollama is not required to turn vendor logs into canonical JSON.
Parsers and `persist_canonical_series` do that. Ollama only enriches the incident write-up.
Laptop A needs Tailscale, `curl`, Python 3, and the ingestion package on `PYTHONPATH`.
Share a dedicated demo API key out of band. Do not commit it.

On Laptop B, create `sdth-telemetry/.env`:

```dotenv
INGEST_API_KEYS=replace-with-a-long-demo-key
OLLAMA_BASE_URL=http://host.docker.internal:11434
OLLAMA_MODEL=deepseek-r1:7b
REDACT_OPERATOR_LOCATION=true
RETENTION_DAYS=30
```

Confirm both devices appear in `tailscale status`.

## Laptop B - processor and replay

```bash
cd sdth-telemetry
./scripts/demo-laptop-b.sh
```

The launcher starts Ollama if present, starts Docker Compose, waits for `/health`, prints the Tailscale URL for Laptop A, and opens `http://localhost:8000/demo/` on Laptop B.

The viewer is served by the API.
Laptop A does not open replay.

If a browser does not open, load:

```text
http://localhost:8000/demo/
```

## Laptop A - controller

```bash
cd sdth-telemetry
API_KEY='replace-with-the-demo-key' \
BASE_URL='http://100.x.y.z:8000' \
ONCE=1 \
./scripts/demo-laptop-a.sh fixtures/demo/controller_mission_alpha.csv
```

Repeat with `fixtures/demo/controller_mission_bravo.csv` to show the recurring GPS-warning pattern and then create a mitigation bulletin:

```bash
curl -X POST http://100.x.y.z:8000/v1/mitigation-bulletins \
  -H "Authorization: Bearer $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"signature":"operator_warning"}'
```

## Same-laptop fallback

If Tailscale or the second laptop is unavailable, stay on this machine:

```bash
cd sdth-telemetry
./scripts/demo-laptop-b.sh
```

Then ingest the recorded demo missions and open replay:

```bash
cd sdth-telemetry
./scripts/demo-local.sh
```

That uploads `fixtures/demo/controller_mission_alpha.csv` and `controller_mission_bravo.csv`, waits for parse/normalize/detect, generates the GPS-warning report and mitigation bulletin, then opens the Cesium replay.

Ollama is optional enrichment, not the JSON normalizer.
If Ollama is down, path replay and the deterministic incident report still work, and model enrichment is marked degraded.

The replay side panel can also list files from `raw_telemetry-datasets/` on this machine.
Select one to parse it and visualize it on the globe.

## What the demo proves

- Dropping a recorded controller log uploads once, even if the file is dropped again.
- Laptop B parses server-side, stores a full canonical series, and indexes geolocated incidents.
- Replay animates the GPS path on an OSM globe and places the GPS-warning marker.
- Live GPS logs use Cesium camera controls and a mission-failure banner when incidents exist.
- Two missions with the same `operator_warning` signature produce a reviewable mitigation bulletin, not a vehicle command.

## Explicitly out of scope

- Live MAVLink, QGroundControl, or Android controller plugins
- Onboard or edge VLM/YOLO
- Globe-projected boxes or landing-zone occupancy
- Microburst, EW, or LPI radio behavior
- Automated firmware or configuration push to a fleet
- Formal accreditation, sovereign-cloud assurance, or defense approval
- Azure hosting and Orcrist integration
