# WISL — Singapore Defence Tech Hackathon

Multi-vendor drone telemetry: parse recorded logs, normalize to one JSON schema, store in SQLite, index incidents across missions, and replay them in 3D.

Target parser coverage: DJI, PX4/Auterion, ArduPilot, Elbit Hermes 900, Aeronautics Orbiter 4, aunav.NEO HD (Taurus UGV).
Hermes, Orbiter, and aunav parsers are format-coverage claims from sample logs, not hardware-validated flights.

## Layout

- [`sdth-telemetry/`](sdth-telemetry/README.md) — ingest API, deterministic canonical series, optional local Ollama enrichment, incident index, two-laptop demo scripts.
- [`sdth-ingestion pipeline/`](sdth-ingestion%20pipeline/README.md) — in-house parsers plus the controller directory watcher.
- [`sdth-replay/`](sdth-replay/README.md) — native C++ 3D replay.
- `sdth-telemetry/fixtures/demo/` — deterministic controller logs for the hackathon demo.

## Demo

The supported demo is a recorded raw-log workflow across two laptops over Tailscale, with a same-laptop fallback.
See the [two-laptop demo runbook](sdth-telemetry/docs/two-laptop-demo.md).

Laptop A drops a log into a watched directory.
Laptop B parses, normalizes, detects incidents, and opens the C++ replay.

## Deferred and unsupported

Live airframe or ground-control-station connections, edge VLM inference, microburst/EW/LPI capabilities, automated fleet fixes, operational accreditation, Azure deployment, and Orcrist integration are not part of this demo.
Tailscale only provides private transport between demo laptops.
