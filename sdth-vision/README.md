# SDTH Vision Sidecar

Laptop-side camera frames and ground-object census for recorded flights.
This package does not sit on the ingest critical path and is not an onboard detector.

VisDrone2019-DET stills are a fine-tune set.
They are not telemetry and they are not VisDrone VID.

Checked-in eval at `artifacts/finetune_eval.json` is `dry_run: true` with `mAP50: null`.
YOLOv8n stays COCO-pretrained until someone trains without `--dry-run`.
Do not check `.pt` weights into git.

## What it does

1. Convert VisDrone DET boxes to YOLO labels (`visdrone_det_to_yolo`).
2. Run `detect_frame` (optional; needs `ultralytics`).
3. Build a census blob: 10 VisDrone class counts plus HUD roll-ups (`census`).
4. POST JPEGs as `kind=camera_frame` via `/v1/flights/{id}/visuals` (`ingest_camera_frames`).
5. POST the census via `/v1/flights/{id}/census` (`attach_census`).

Replay joins the nearest `recorded_at` on the Cesium clock and renders `#censusLine` as `cars N · people M`.

HUD roll-ups:

- `cars = car + van + truck + bus`
- `people = pedestrian + people`

Stored classes (ignored class 0 dropped): pedestrian, people, bicycle, car, van, truck, tricycle, awning-tricycle, bus, motor.

## Install

```bash
cd sdth-vision
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"
```

Optional GPU train/infer extra:

```bash
.venv/bin/pip install -e ".[train]"
```

## Tests

```bash
cd sdth-vision
.venv/bin/pytest -q
```

## Fine-tune CLI

```bash
finetune_detector --train-images path/to/images --dry-run --eval-json artifacts/finetune_eval.json
```

`--dry-run` writes a data YAML and smoke metrics without training.
That is the checked-in state.

## Out of scope

- Globe-projected boxes (needs camera intrinsics on the log)
- Multi-object tracking / MOT unzip
- Landing-zone occupancy (census plus altitude from L2; not wired)
- Edge or airframe inference
