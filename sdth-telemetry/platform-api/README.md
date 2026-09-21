# Platform API

FastAPI app in this directory: raw-log ingest, canonical L2 JSON, physics detectors, incidents, and the evidence query engine.

Run it with `./sdth-telemetry/scripts/demo-console.sh` from the repository root; see [`sdth-telemetry/README.md`](../README.md).
The legacy two-laptop runbook is [`docs/two-laptop-demo.md`](../docs/two-laptop-demo.md).

OpenAPI: [`openapi/openapi.yaml`](../openapi/openapi.yaml).

Raw logs enter at `POST /v1/logs/upload`.
Normalized batches still enter at `POST /v1/telemetry/ingest` (legacy structured-JSON route).
