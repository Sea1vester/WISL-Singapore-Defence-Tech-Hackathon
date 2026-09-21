# SDTH Replay

CesiumJS 3D replay for recorded WISL flights.

The WISL console at `/demo/` embeds this viewer at `/replay/?embed=1`.
Bare `/replay/` redirects to the console.
It draws WGS84 path samples over cached terrain with OpenStreetMap imagery or an embedded tabletop treatment, animates the UAV on the recorded clock, and overlays indexed incidents.

This is not a live airframe or GCS client.
No Cesium Ion token is required.
The default UAV is a small quadcopter (`public/assets/drone.glb`, CC BY 4.0, [amvlab/aircraft-models](https://github.com/amvlab/aircraft-models)).

## Run

From the repository root:

```bash
./sdth-telemetry/scripts/demo-console.sh
```

Then open the console:

```text
http://127.0.0.1:8010/demo/
```

Legacy launchers: `sdth-telemetry/scripts/demo-laptop-b.sh`, `sdth-telemetry/scripts/demo-local.sh`.

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
The embedded console defaults to **Tabletop**: a finite terrain model using cached Esri elevation, OpenStreetMap footprint geometry, painted facets and an understated focus effect. **Map** restores standard imagery over the same cached elevation. Both views disable cast shadows. Feature heights are illustrative and capped; the representative aircraft is enlarged. This is a replay visualisation, not an obstacle-clearance model. All 14 bundled demo fixtures are covered by the three regional caches. Outside the cache bounds, the viewer explicitly reports flat, uncached terrain.

See [data sources and cache regeneration](public/assets/TABLETOP-SOURCES.md).
Play/pause and speed buttons drive the Cesium clock.
Pick a recorded flight from the console Mission library.
