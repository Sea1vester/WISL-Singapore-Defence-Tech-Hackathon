# WISL — Singapore Defence Tech Hackathon

Multi-vendor drone telemetry: parse recorded logs, normalize to one JSON schema, store in SQLite, index incidents across missions, and replay them in 3D.
Focused on cheap, commercial-off-the-shelf drone fleets (DJI, PX4/Auterion, ArduPilot — the flight stacks behind most budget and DIY/FPV builds), where fragmentation across brands is worse and fleets are far larger than a handful of named platforms.

Target parser coverage: DJI, PX4/Auterion, ArduPilot.
Elbit Hermes 900, Aeronautics Orbiter 4, and aunav.NEO HD (Taurus UGV) remain supported as legacy format-coverage claims from sample logs, not hardware-validated flights, but are no longer the project's headline target.

## Layout

- [`sdth-telemetry/`](sdth-telemetry/README.md) — ingest API, deterministic canonical series, optional local Ollama enrichment, incident index, two-laptop demo scripts.
- [`sdth-ingestion pipeline/`](sdth-ingestion%20pipeline/README.md) — in-house parsers plus the controller directory watcher.
- [`sdth-replay/`](sdth-replay/README.md) — CesiumJS 3D replay served by the Laptop B API.
- [`sdth-vision/`](sdth-vision/README.md) — laptop sidecar for `camera_frame` ingest and `frame_census`. Not onboard inference.
- `sdth-telemetry/fixtures/demo/` — two DJI CSV fixtures for the hackathon demo.
- `isaac-3d/` — leftover OpenGL visualizer. The supported replay is Cesium.

## What we actually ran

Counts are files the parsers accept.
The live demo uses a subset.

- DJI CSV: 2 controller fixtures (`controller_mission_alpha.csv`, `controller_mission_bravo.csv`). Recurring `operator_warning` (GPS signal weak).
- PX4 ULog: 3 recorded `.ulg` under `raw_telemetry-datasets/`, with pytest on the sample ULog.
- ArduPilot: 2 DataFlash `.bin` plus 1 MAVLink `.tlog`.
- Vision: VisDrone2019-DET stills (6471 train / 548 val / 1610 test-dev). Images, not flight logs. Fine-tune is still `dry_run: true`; mAP is null.

VisDrone is not a fourth log format and is not ingest validation through `/v1/logs/upload`.

## Demo

The supported demo is a recorded raw-log workflow across two laptops over Tailscale, with a same-laptop fallback.
See the [two-laptop demo runbook](sdth-telemetry/docs/two-laptop-demo.md).

Laptop A drops a log into a watched directory.
Laptop B parses, normalizes, detects incidents, and opens the Cesium replay in a browser.

The checked demo is GPS-weak `operator_warning` on those two CSVs, then a mitigation bulletin at `min_flights=2`.
Replay can show a census HUD (`cars N · people M`) when camera frames and `frame_census` are attached.
That join is on the Cesium clock from a laptop sidecar, not an onboard detector.

## Deferred and unsupported

Live airframe or ground-control-station connections, onboard or edge VLM/YOLO, globe-projected boxes, landing-zone occupancy, microburst/EW/LPI capabilities, automated fleet fixes, operational accreditation, Azure deployment, and Orcrist integration are not part of this demo.
Tailscale only provides private transport between demo laptops.
YOLOv8n stays COCO-pretrained until someone runs `finetune_detector` without `--dry-run`.
