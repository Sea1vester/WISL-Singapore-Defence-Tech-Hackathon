# SDTH Replay

CesiumJS 3D replay for recorded WISL flights.

The WISL console at `/demo/` embeds this viewer at `/replay/?embed=1`.
Bare `/replay/` redirects to the console.
It draws WGS84 path samples over cached terrain with OpenStreetMap imagery or an embedded tabletop treatment, animates the UAV on the recorded clock, and overlays indexed incidents.
When `camera_frame` visuals have `frame_census` rows, `#censusLine` shows `cars N · people M` from the nearest `recorded_at` on that clock.
That HUD is a laptop sidecar join, not an onboard detector.

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
http://localhost:8000/demo/
```

Open a recorded flight from the console Mission library.
The embed loads that flight's path. Without a flight id it uses the bundled offline demo JSON.

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
The embedded console defaults to **Tabletop**: a finite terrain model using cached Esri elevation, OpenStreetMap footprint geometry, painted facets and an understated focus effect. **Map** restores standard imagery over the same cached elevation. Both views disable cast shadows. Feature heights are illustrative and capped; the representative aircraft is enlarged. This is a replay visualisation, not an obstacle-clearance model. All 13 submission demo flights are covered by the three regional caches. Outside the cache bounds, the viewer explicitly reports flat, uncached terrain.

See [data sources and cache regeneration](public/assets/TABLETOP-SOURCES.md).
Play/pause and speed buttons drive the Cesium clock.
Pick a recorded flight from the console Mission library.
Census HUD updates with the clock when census rows exist for that flight.
