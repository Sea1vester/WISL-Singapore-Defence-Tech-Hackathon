# Two-Laptop WISL Demo Runbook

Laptop A simulates a controller by dropping a recorded raw log into a watched directory.
Laptop B receives the file, parses it, normalizes it, detects incidents, and opens the C++ replay.

Both laptops should be on the same Tailscale tailnet.
The API stays private to that tailnet. Do not expose it with Tailscale Funnel.

This demo uses recorded logs. It is not a live airframe or GCS connection.

## Before the demo

Laptop B needs Docker Desktop, Tailscale, `curl`, and optionally Ollama with `deepseek-r1:7b`.
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

The launcher starts Ollama if present, starts Docker Compose, waits for `/health`, prints the Tailscale URL for Laptop A, and launches `sdth-replay --latest`.

If cmake is missing, the API still starts. Build the replay later from `sdth-replay/README.md`, or use the bundled offline JSON:

```bash
./sdth-replay/build/sdth-replay --file sdth-replay/assets/demo_path.json --incidents sdth-replay/assets/demo_incidents.json
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

If Tailscale or the second laptop is unavailable:

```bash
cd sdth-telemetry
LAUNCH_REPLAY=0 ./scripts/demo-laptop-b.sh
```

```bash
cd sdth-telemetry
API_KEY='replace-with-the-demo-key' \
BASE_URL='http://localhost:8000' \
ONCE=1 \
./scripts/demo-laptop-a.sh fixtures/demo/controller_mission_alpha.csv
```

Then open replay locally:

```bash
./sdth-replay/build/sdth-replay --latest --api http://localhost:8000 --token "$API_KEY"
```

Ollama can also be unavailable. Detection, path replay, and the deterministic incident report still work. Model enrichment is marked degraded.

## What the demo proves

- Dropping a recorded controller log uploads once, even if the file is dropped again.
- Laptop B parses server-side, stores a full canonical series, and indexes geolocated incidents.
- Replay animates the GPS path and places the GPS-warning marker.
- Two missions with the same signature produce a reviewable mitigation bulletin, not a vehicle command.

## Explicitly out of scope

- Live MAVLink, QGroundControl, or Android controller plugins
- Edge VLM / camera visual tags
- Microburst, EW, or LPI radio behavior
- Automated firmware or configuration push to a fleet
- Formal accreditation, sovereign-cloud assurance, or defense approval
- Azure hosting and Orcrist integration
