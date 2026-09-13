# WISL — Singapore Defence Tech Hackathon

Multi-vendor drone telemetry: parse recorded logs, normalize to one JSON schema, store in SQLite, index incidents across missions, and replay them in 3D.
Targets both ends of the fleet: cheap, commercial-off-the-shelf drones (DJI, PX4/Auterion, ArduPilot — the flight stacks behind most budget and DIY/FPV builds), where fragmentation across brands is worse and fleets are far larger than a handful of named platforms, and expensive, small-fleet tactical platforms, where a single-airframe loss is costly enough to be worth reconstructing on its own.

Target parser coverage: DJI, PX4/Auterion, ArduPilot, Elbit Hermes 900, Aeronautics Orbiter 4, and aunav.NEO HD (Taurus UGV) — six brands across both fleet segments, on equal footing in the brand catalog.

## Current submission demo — 13 September 2026

Run `./sdth-telemetry/scripts/demo-console.sh`, then open <http://127.0.0.1:8010/demo/>. The new console provides raw upload, real processing status, incident evidence, recorded replay, deterministic operator queries, recurring patterns, reviewable bulletins and optional local-model analysis. See the [setup and demonstration runbook](docs/submission/demo-runbook.md).

The intended synthetic/SITL hazard corpus contains 90 exports across ten scenarios. The [bounded audit](docs/submission/corpus-validation.md) completed structural checks on 70/90 files; 20 exceeded its eight-second bound, and only 36/90 met scenario-detection expectations. A focused corrected DJI CSV evaluation passed ten original scenarios plus two supplemental missions (12/12). This is format-level software evidence, not hardware compatibility or operational validation. The audit exposed and fixed false altitude spikes from treating zero relative height as absent.

The [technical report](output/pdf/WISL_FinalReport_v1.pdf), [cited use-case research](docs/submission/research-brief.md), [two-minute video handoff](docs/submission/video-handoff.md), [three-minute pitch script](pitch-script.md) and [reserve Q&A](docs/submission/pitch-qa-kiv.md) accompany this build. Video recording and external submission remain outstanding. The older counts below describe prior work and are not the denominator of this submission audit.

## Layout

- [`sdth-telemetry/`](sdth-telemetry/README.md) — ingest API, deterministic canonical series, optional local Ollama enrichment, incident index, two-laptop demo scripts.
- [`sdth-ingestion pipeline/`](sdth-ingestion%20pipeline/README.md) — in-house parsers plus the controller directory watcher.
- [`sdth-replay/`](sdth-replay/README.md) — CesiumJS 3D replay served by the Laptop B API.
- [`sdth-vision/`](sdth-vision/README.md) — laptop sidecar for `camera_frame` ingest and `frame_census`. Not onboard inference.
- [`sdth-synth/`](sdth-synth/README.md) — generate new vendor-native logs from a kinematic core. Gold corpus stays frozen.
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
