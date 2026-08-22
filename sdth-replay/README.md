# SDTH Replay

CesiumJS 3D replay for recorded WISL flights.

Laptop B serves the viewer at `/replay/` from the telemetry API.
It draws WGS84 path samples on an ellipsoid globe with OpenStreetMap imagery, animates the UAV on the recorded clock, and overlays indexed incidents.

This is not a live airframe or GCS client.
No Cesium Ion token is required.
The default UAV is a small quadcopter (`public/assets/drone.glb`, CC BY 4.0, [amvlab/aircraft-models](https://github.com/amvlab/aircraft-models)).

## Run

Start the API on Laptop B, then open a browser:

```bash
cd sdth-telemetry
./scripts/demo-laptop-b.sh
```

Same-laptop ingest then replay:

```bash
cd sdth-telemetry
./scripts/demo-local.sh
```

Manual URL:

```text
http://localhost:8000/replay/?token=$INGEST_API_KEYS&latest=1
http://localhost:8000/replay/?token=$INGEST_API_KEYS&flights=<id1>,<id2>
```

Without flight ids, the page loads the bundled offline demo JSON.
The side panel lists ingested flights and files from `raw_telemetry-datasets/` on Laptop B.
Select a dataset to parse it and visualize the path.

## Tests

```bash
node --test tests/flight.test.mjs
```

From `sdth-telemetry/platform-api`:

```bash
pytest tests/test_replay_viewer.py
```

## Controls

Cesium camera: pinch to zoom, drag to orbit the UAV (including from below), Home to reset.
The globe uses real world elevation where available, drapes OSM imagery on that terrain, and plants OpenStreetMap trees near the flight.
Play/pause and speed buttons drive the Cesium clock.
Pick an ingested flight or a local dataset from the side panel.
