# WISL — Singapore Defence Tech Hackathon

Multi-vendor drone telemetry: parse raw logs, normalize to one JSON schema, store in SQLite, index incidents across missions.

Target platforms: DJI, PX4/Auterion, ArduPilot, Elbit Hermes 900, Aeronautics Orbiter 4, aunav.NEO HD (Taurus UGV).

## Layout

- [`sdth-telemetry/`](sdth-telemetry/README.md) — ingest API, L1→L2 translation (Ollama), query, incident index. Runs on a Mac via Docker; teammates use the HTTP API over Tailscale.
- [`sdth-ingestion pipeline/`](sdth-ingestion%20pipeline/README.md) — in-house parsers for the formats above, plus an edge log uploader.
- `raw_telemetry-datasets/` — sample logs used for parsers and tests.

## Progress

Done: vendor parsers (including Hermes / Orbiter / Taurus), L1 ingest, L2 canonical JSON, flight path export, per-flight LLM incident reports, SQLite incident index with cross-mission pattern detection and per-brand reliability stats.

Not done: Azure/cloud hosting (laptop + Tailscale for now), live ingest from the actual airframes.
