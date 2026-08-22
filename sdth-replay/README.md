# SDTH Replay

Native C++ 3D replay for recorded WISL flights.

The viewer is an offline-capable raylib app. It maps WGS84 path samples into a
local East-North-Up frame, animates a UAV along the recorded timestamps, and
places incident markers from the telemetry API or bundled demo JSON.

This is not a live airframe or GCS client.

## Build

```bash
cmake -S . -B build
cmake --build build --target sdth-replay sdth_replay_tests
ctest --test-dir build --output-on-failure
```

## Run

Offline fallback (no API required):

```bash
./build/sdth-replay
```

Live API, including the latest ingested flight:

```bash
./build/sdth-replay --latest --api http://localhost:8000 --token "$INGEST_API_KEYS"
```

Specific flights or local path JSON:

```bash
./build/sdth-replay --file assets/demo_path.json --incidents assets/demo_incidents.json
./build/sdth-replay --flight <flight-id> --api http://100.x.y.z:8000 --token "$INGEST_API_KEYS"
```

## Controls

- Space: play or pause
- Timeline bar: scrub
- Speed buttons: 0.25x to 4x
- Right mouse: orbit
- Shift + right mouse: pan
- Wheel: zoom
- F: follow UAV
- R: reset camera
- [ and ]: switch among loaded flights

## What the panel shows

Upload or demo status, flight metadata, battery, current event, detected
incidents, and the evidence-backed report when the API has one.
