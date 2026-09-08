# Platform API

FastAPI app in this directory: ingest, canonical L2 JSON, physics detectors, incidents, visuals, and `frame_census`.

Run it from [`sdth-telemetry/README.md`](../README.md) (Docker Compose or local uvicorn).
The two-laptop demo runbook is [`docs/two-laptop-demo.md`](../docs/two-laptop-demo.md).

OpenAPI: [`openapi/openapi.yaml`](../openapi/openapi.yaml).

Raw logs enter at `POST /v1/logs/upload`.
Normalized batches still enter at `POST /v1/telemetry/ingest`.
Camera frames are `POST /v1/flights/{id}/visuals` with `kind=camera_frame`.
Census is `POST`/`GET /v1/flights/{id}/census`.
Detection itself lives in [`sdth-vision`](../../sdth-vision/README.md), not in this worker.
