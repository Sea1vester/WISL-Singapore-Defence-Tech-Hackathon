# WISL — Singapore Defence Tech Hackathon

Multi-vendor drone telemetry: parse recorded logs, normalize to one JSON schema, store in SQLite, index incidents across missions, and replay them in 3D. Focused on cheap, commercial-off-the-shelf drone fleets (DJI, PX4/Auterion, ArduPilot — the flight stacks behind most budget and DIY/FPV builds), where fragmentation across brands is worse and fleets are far larger than a handful of named platforms.

Target parser coverage: DJI, PX4/Auterion, ArduPilot. Elbit Hermes 900, Aeronautics Orbiter 4, and aunav.NEO HD (Taurus UGV) remain supported as legacy format-coverage claims from sample logs, not hardware-validated flights, but are no longer the project's headline target.

## Layout

- [`sdth-telemetry/`](sdth-telemetry/README.md) — ingest API, deterministic canonical series, optional local Ollama enrichment, incident index, two-laptop demo scripts.
- [`sdth-ingestion pipeline/`](sdth-ingestion%20pipeline/README.md) — in-house parsers plus the controller directory watcher.
- [`sdth-replay/`](sdth-replay/README.md) - CesiumJS 3D replay served by the Laptop B API.
- `sdth-telemetry/fixtures/demo/` — deterministic controller logs for the hackathon demo.

## Demo

The supported demo is a recorded raw-log workflow across two laptops over Tailscale, with a same-laptop fallback.
See the [two-laptop demo runbook](sdth-telemetry/docs/two-laptop-demo.md).

Laptop A drops a log into a watched directory.
Laptop B parses, normalizes, detects incidents, and opens the Cesium replay in a browser.

## Deferred and unsupported

Live airframe or ground-control-station connections, edge VLM inference, microburst/EW/LPI capabilities, automated fleet fixes, operational accreditation, Azure deployment, and Orcrist integration are not part of this demo.
Tailscale only provides private transport between demo laptops.
