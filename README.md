# WISL — Singapore Defence Tech Hackathon

Multi-vendor drone telemetry: parse recorded logs, normalize to one JSON schema, store in SQLite, index incidents across missions, and replay them in 3D.
Targets both ends of the fleet: cheap, commercial-off-the-shelf drones (DJI, PX4/Auterion, ArduPilot — the flight stacks behind most budget and DIY/FPV builds), where fragmentation across brands is worse and fleets are far larger than a handful of named platforms, and expensive, small-fleet tactical platforms, where a single-airframe loss is costly enough to be worth reconstructing on its own.

Target parser coverage: DJI, PX4/Auterion, ArduPilot, Elbit Hermes 900, Aeronautics Orbiter 4, and aunav.NEO HD (Taurus UGV) — six brands across both fleet segments, on equal footing in the brand catalog.

## Start the local demo

Requirements: Python 3.11 or later. From this repository's root:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -e './sdth-telemetry/platform-api[dev]'
./sdth-telemetry/scripts/demo-console.sh
```

Once dependencies are installed, only the last command is needed. Open **<http://127.0.0.1:8010/demo/>**. In **Session**, enter the development key `dev-teammate-key-change-me`, or one key from your `INGEST_API_KEYS` setting. This launcher runs the API and one background ingestion worker locally; Redis is not needed. Stop it with Ctrl+C. Run it again to recover interrupted ingestion jobs.

### Use the replay workspace

1. Choose a stored record in the **Mission library** sidebar. Search filters the loaded records. On small screens, use **Flight library** to open the drawer. The last selected flight loads automatically when you return.
2. To add a record, choose **Import log**, then drop a file in **Logs & uploads**. For a quick start, use **Try the included synthetic GPS-warning log** in that tab. Its bytes are processed by the real pipeline; duplicate uploads reuse the existing record.
3. Wait for **Record normalized**. The replay fills the main view. **Tabletop** presents the recorded path above a low-poly terrain model with painted teal facets, solid map features and subtle tilt-shift focus; **Map** shows OpenStreetMap imagery on the cached elevation surface. Drag the scene to tilt/orbit and scroll to zoom. Shadows are disabled in both views. The enlarged aircraft model is for visibility. Use **Play/Pause**, **Restart**, playback-speed and timeline controls to inspect the recorded flight. The telemetry strip shows recorded altitude, battery and UTC; **Track speed** is derived from consecutive positions. The inset shows the recorded route.
4. Use the bar below the replay: **Mission analysis** contains observations and record queries, **Recurring patterns** compares stored signatures, and **Bulletins** holds reviewable follow-up. Switching these tabs keeps the replay on screen.
5. Click **Replay this observation** to pause at its recorded timestamp. Ask **What happened?**, **Where is the evidence?** or **Similar warnings** for deterministic evidence-backed answers.
6. Expand **Local AI analysis** inside Mission analysis for optional fleet interpretation. Its explanations are unverified hypotheses, even when the referenced evidence IDs are valid.

The bundled GPS-warning and dropout logs in `sdth-demo/fixtures/` are synthetic copies from the original corpus. Additional independent normal and GPS-warning fixtures are in `output/evidence/corpus-validation/supplemental/`. The term “jamming” in a simulator filename is not a causal diagnosis.

### Load the additional failure scenarios

With the demo running, load one CSV per audited synthetic mission:

```sh
.venv/bin/python sdth-telemetry/scripts/load_demo_failures.py
```

Then open **Flight library** and refresh. Entries beginning with **synthetic** include low battery, recording gaps, frozen reported positions, warning events and recordings that end airborne, plus a normal control. The loader checks each fixture against its audit checksum and verifies the real API's detector results. Set `INGEST_API_KEY` for a custom session key; use `--base-url http://127.0.0.1:8011` for another port. See the [validation report](docs/submission/corpus-validation.md) for supported conclusions and simulation limitations.

### Optional local model

With Ollama installed, run these in a separate terminal:

```sh
ollama pull deepseek-r1:7b
ollama serve
```

The download is needed once; skip `ollama serve` if it is already running. The launcher defaults to `http://127.0.0.1:11434` and `deepseek-r1:7b`. Set `OLLAMA_MODEL` or `OLLAMA_BASE_URL` before starting the demo to select another local installation. Parsing, replay, record queries and bulletins work without the model. Local inference does not make replay air-gapped: Cesium and map assets still require network access. The three bundled demo regions have local elevation and OpenStreetMap geometry caches, so terrain loading does not depend on an external request. Map imagery and the Cesium runtime still require network access. An upload outside those regions is labelled **Terrain uncached · flat globe**; no terrain is invented. See [map data and styling notes](sdth-replay/public/assets/TABLETOP-SOURCES.md).

### Runtime and evidence

The database is `data/demo-console.db`; raw uploads, reports and visuals also stay under `data/`. These runtime files are excluded from Git. `WISL_PYTHON=/absolute/path/to/python` selects another Python environment; `API_PORT=8011` selects another local port. See the [detailed runbook](docs/submission/demo-runbook.md) for the complete demonstration sequence.

The [corpus validation report](docs/submission/corpus-validation.md) separates the original 90 exports from later fixtures, field-level evidence gaps, processing timeouts and detector conclusions. Original exports represent ten generated scenarios, not 90 independent operational missions. The older counts below describe prior work and are not the denominator of the latest audit.

Submission handoffs: [technical report](output/pdf/WISL_FinalReport_v1.pdf), [cited use-case research](docs/submission/research-brief.md), [video script](docs/submission/video-handoff.md), [three-minute pitch](pitch-script.md) and [reserve Q&A](docs/submission/pitch-qa-kiv.md). The technical report reflects the current validation results. The video handoff uses the revised controls; rehearse the final demo before recording.

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

## Optional two-laptop setup

The local console above is the current demonstration entry point. An earlier recorded raw-log workflow can also run across two laptops over Tailscale, with a same-laptop fallback.
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
