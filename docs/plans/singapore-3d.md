# Singapore 3D replay plan

Overnight task, ~4.5 hours wall-clock budget, on a NEW branch. Nobody is watching; work autonomously, commit in logical steps as you go, and write a final report. Constraints first:

- `git switch -c feature/singapore-3d` from current main (c5509cc). ALL work on that branch. Never touch main. Commit messages: plain, no Co-Authored-By or "Generated with" trailers. Push the branch (plain `git push -u origin feature/singapore-3d`, never force) after each milestone below.
- Hard stop: at 4h15m elapsed from when you start, stop new work, commit what's done, push, and write the report even if later milestones are unfinished. Put a timestamp in each commit body so I can see pacing.
- Don't modify sdth-synth (gitignored) except by adding YAML files under sdth-synth/scenarios/singapore/ — and copy those YAMLs also into `sdth-demo/fixtures/singapore/cards/` so they're tracked.
- No new runtime dependencies for the platform or replay. Node tooling in /tmp is fine (lerc as TABLETOP-SOURCES.md describes). Playwright is available in wisl-demo-record/node_modules for screenshots.
- Existing tests must stay green: platform pytest (197), parsers (30), `node --test sdth-replay/tests/*.test.mjs` (27), `node --test sdth-demo/test/*.test.mjs` (5).

## Goal

Make the 3D replay look realistic and to scale, over Singapore. Reference look: MapLibre-style view of Bukit Timah/Hillview with real-height 3D buildings, satellite option, pitched camera. We keep Cesium; we upgrade data + rendering rules.

First commit: save this whole brief verbatim as `docs/plans/singapore-3d.md` (heading "# Singapore 3D replay plan") so the plan is on the branch.

## Milestone 1 — Singapore flight logs (do first; everything else depends on it)

Three regions, homes chosen so flights are plausible:
- `lim-chu-kang`: home 1.4050, 103.7000 (Lim Chu Kang / Sungei Gedong training area, rural). 
- `hillview`: home 1.3628, 103.7672 (Hillview, near Dairy Farm / Bukit Timah slopes; dense HDB + condos).
- `seletar`: home 1.4165, 103.8655 (Seletar Aerospace Park, hangars, low buildings).

Write scenario cards under `sdth-synth/scenarios/singapore/` (and the tracked copy), modelled on `sdth-synth/scenarios/hazards/*.yaml` and `output/evidence/corpus-validation-v2/normal_control_v2.yaml`. Same YAML schema (see `sdth_synth/scenario.py` Scenario fields). Make the routes look like real missions, using multiple `cruise` phases (no generator change needed):
1. `sg_lck_survey_normal` (lim-chu-kang): lawnmower survey, 6 parallel legs ~350 m long, 60 m spacing, alt 60 m, speed 6–8 m/s, then rth+land. Normal control: `gps_degraded_at_s: null`, no other injections. Must produce ZERO incidents.
2. `sg_lck_survey_gps_weak` (lim-chu-kang, different seed, home offset ~150 m east): same survey shape, `gps_degraded_at_s` mid-flight for 25 s with the DJI GPS-weak `operator_warning_text` used in the existing cards.
3. `sg_seletar_perimeter_gps_weak` (seletar): perimeter patrol around the apron, 5 legs, alt 45 m, GPS-weak window. This is the recurrence partner for #2 (same warning text → Similar warnings finds it).
4. `sg_hillview_inspection_battery_critical` (hillview): short inspection route over the park/road (keep legs over green space, not over buildings), alt 50 m, `end_battery_pct` low enough to hit battery_critical (≤10%) before landing; look at how battery_critical.yaml does it.
5. `sg_hillview_inspection_dropout` (hillview): same route, `logger_gap_at_s` mid-flight for 18 s → telemetry_gap.
6. `sg_seletar_ends_airborne` (seletar): `end_airborne_at_s` → mission_incomplete.
Durations 4–7 minutes each at dt 1 s. Keep altitudes ≤ 60 m. Check `sdth_synth/core.py` for how phases move (north_m/east_m are targets relative to home) to lay out the legs.

Generator script: `sdth-telemetry/scripts/generate_singapore_fixtures.py`, modelled on generate_v2_failure_fixtures.py. IMPORTANT: `sdth_synth/geo.py BANNED_HOMES_ALWAYS` includes Singapore centre and the gate radius is 50 km, so `validate_geography` will reject every Singapore home. Do NOT change the gate. Call `integrate(scenario, validate_home=False)` and record `"geography_gate": "bypassed: Singapore demo region, inside BANNED_HOMES_ALWAYS radius"` in the manifest. Still run `gate_generated_dir` (physical sanity) and fail if it fails. Emit `dji_csv` only. Output to `sdth-demo/fixtures/singapore/` with `manifest.json` (same shape as `sdth-demo/fixtures/manifest.json` entries: file, sha256, source, provenance, parser, region) plus `observed_detectors` per file measured the same way generate_perturbed_fixtures.py does. Report the observed_detectors table to me verbatim; #1 must be `{}`; if a card doesn't produce its intended incident, adjust the card (not the detectors) and say what you changed.

Wire into the console: `sdth-demo/demo.js` hardcodes the fixture list imported on Session connect. Replace the list with the six Singapore files, with titles: "Lim Chu Kang · Survey · Normal control", "Lim Chu Kang · Survey · GPS-weak", "Seletar · Perimeter · GPS-weak", "Hillview · Inspection · Battery critical", "Hillview · Inspection · Telemetry dropout", "Seletar · Recording ends airborne". Keep the "Try an example log with a GPS warning" button working (point it at #2). Keep the old UK CSVs on disk and tracked where they are (docs and load_demo_failures.py reference them) but they no longer auto-import. Also regenerate `sdth-demo/fixtures/perturbed/` from the Singapore normal-control and GPS-weak cards: add `--cards` args to generate_perturbed_fixtures.py so it can take the singapore cards (default stays the current behaviour), regenerate into `sdth-demo/fixtures/perturbed/` (the judges' unhappy-path set should be Singapore too), and report the new observed_detectors. Update `sdth-demo/fixtures/perturbed/README.md` if anything changes.

Update `sdth-telemetry/parsers/tests` / platform tests only if they reference the fixture list. Commit + push: "Add Singapore demo missions".

## Milestone 2 — Singapore map caches with real building heights and finer terrain

Use the existing pipeline in sdth-replay/scripts (cache-tabletop.cjs, build-tabletop-atlas.cjs) and TABLETOP-SOURCES.md. For each of the three regions, bounds = flight bounds padded to at least 1.2 km × 1.2 km around the home (hillview: extend north-west enough to include the Dairy Farm / Bukit Timah slope so terrain is visibly not flat). Overpass `out geom` for building, highway, landuse, natural, leisure, waterway ways (same set as the current caches) — save the raw responses under `sdth-replay/public/assets/osm-source/<region>.json` only if under 3 MB each; otherwise keep them in /tmp and note it. Hillview will be dense; if the cache exceeds what a single tabletop-<region>.json can hold, use the chunked layout north-wales uses (see tabletop-chunks/ and build-tabletop-atlas.cjs).

Elevation: the cache script samples a 49×49 grid; add a `--grid N` flag (default 49) and use 97 for all three Singapore regions. Register the three region names in `loadTabletopAtlas` in tabletop-context.mjs. The three UK regions stay.

Building heights: in tabletop.mjs `illustrativeBuildingHeight` currently clamps to [4, 24] m and estimates 3.1 m/level. Change to: explicit `height` tag wins; else `building:levels` × 3.0 (+ 1.5 m roof) ; else 8 m; clamp to [3, 200]. Respect `min_height` / `building:min_level` if present (extrude from base + min). Add a test in sdth-replay/tests/tabletop.test.mjs for: 40 levels → 121.5 m, explicit height=12.4 → 12.4, no tags → 8. Update the "capped at 24 m" sentence in TABLETOP-SOURCES.md.

Commit + push: "Cache Singapore map regions with real building heights".

## Milestone 3 — Map mode that actually loads, with terrain, buildings and satellite

In replay.js:
a) Map mode currently hides all tabletop primitives (`state.tabletop.setVisible(!mapVisible)`), so it's flat imagery on the globe. Split visibility: in Map mode keep the extruded buildings (walls + roofs) and hide only the ground slab, painted landuse facets, road ribbons and decorative seams. Look at how createStreamingTabletop groups primitives in tabletop-stream.mjs / tabletop.mjs and add a `setMapOverlay(true)` style method that toggles the right subsets. Terrain in Map mode already uses `createCachedTerrain` when the atlas covers the flight, confirm that's what happens for the Singapore regions and that the imagery is draped on it (not flat ellipsoid).
b) Satellite imagery: add a second imagery source through the tile proxy. In `sdth-telemetry/platform-api/app/tiles.py` add route `/tiles/sat/{z}/{x}/{y}.jpg` proxying Esri World Imagery `https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}` (note y before x), cached under `<tile_cache_dir>/sat/`, MAX_ZOOM 19; raise the OSM route's MAX_ZOOM to 19 too. Add a pytest for the sat route path/cache logic with the upstream call mocked (mirror whatever tests exist for the OSM route). In the replay HUD, replace the Tabletop/Map toggle with a three-way: Tabletop · Map · Satellite. Attribution: "Esri, Maxar, Earthstar Geographics, and the GIS User Community" must be shown when Satellite is active (Cesium credit).
c) Pre-warm: extend `sdth-replay/scripts/warm-tiles.cjs` to take region bounds from the atlas for the three Singapore regions and fetch both OSM (z13–18) and sat (z13–19) tiles through the local proxy into data/tiles. Run it (server must be up on 8010 via demo-console.sh; check for a stale server first, kill and restart since code changed). Report tile counts and total MB. data/ is gitignored, so also document the warm command in README where warm-tiles is mentioned.
d) Why Map didn't load before: with the tile cache empty and OSM slow/blocked, the proxy returns 502 and Cesium shows nothing. After pre-warm this is fixed for the demo regions; additionally make the proxy return a 1×1 transparent PNG with a `X-WISL-Tile: missing` header instead of 502 when upstream fails, so the scene still renders (terrain + buildings) without imagery. Log a warning once per zoom level, not per tile.

Commit + push: "Make Map mode load with terrain, buildings and satellite imagery".

## Milestone 4 — True scale

a) Drone model: currently `maximumScale: 24`, `minimumPixelSize` 24–28. Add a HUD toggle "1:1 / Enlarged". In 1:1 mode: `scale: 1`, `maximumScale: 1`, `minimumPixelSize: 0`, and show a small billboard ring marker (existing point graphics) so the aircraft position stays findable. Enlarged mode = current values. Default to 1:1 when the camera is within 400 m of the aircraft, Enlarged otherwise (compute once per second, not per frame). Check `public/assets/drone.glb` real size: log its bounding sphere radius once at load and report it; a Mini 4 Pro is ~0.35 m across, so if the glb is not roughly that size, apply a fixed correction scale so 1:1 means real size.
b) Camera: default framing on flight load should be a pitched (-35°) view that fits the flight bounds with ~15% margin, looking roughly north, not a top-down or a far-away globe view. Check what it does now and fix if needed.
c) Scale legend: a small bar in the HUD corner showing 100 m / 50 m / 20 m adjusted to the current camera distance (Cesium: compute metres-per-pixel at screen centre from camera height and FOV). Plain DOM, styled like the existing HUD.
d) Ground reference: confirm the aircraft's rendered altitude is rebased above local ground at the home position using the cached terrain (TABLETOP-SOURCES says it already is). Verify with the hillview flight that the drone is not underground or floating on the slope.

Add/adjust `sdth-replay/tests/flight.test.mjs` for any pure functions you introduce (metres-per-pixel, scale-mode selection). Commit + push: "Render the aircraft at true scale with a scale legend".

## Milestone 5 — Verify visually and document

- Screenshots with Playwright (headless Chromium, 1600×1000) of `http://127.0.0.1:8010/replay/?flight=<id>` for each Singapore flight in each of Tabletop / Map / Satellite, paused ~40% into the flight, camera default. Cesium needs WebGL: launch Chromium with `--use-gl=swiftshader --enable-unsafe-swiftshader --ignore-gpu-blocklist`; if WebGL still fails, say so and take the screenshots you can. Save to `output/evidence/singapore-3d/<flight>-<mode>.png`. Also one screenshot of the console `/demo/` with the Hillview mission loaded. These are for my review; keep them (they're small PNGs, commit them).
- Update docs where mission names or regions are mentioned: README.md (demo walkthrough + "three bundled demo regions" sentences), docs/submission/demo-runbook.md step names, docs/demo-flow.md, docs/talk-track.md, docs/code-check.md (UK mission names → Singapore titles; "three demo regions" → six regions, three in Singapore). Keep edits to name/region substitutions and the new Satellite/1:1 toggles; don't rewrite prose.
- Run all four test suites. Report counts.

Final report to me: per-milestone status, commit list with timestamps, observed_detectors tables (singapore + perturbed), tile counts, glb size finding, screenshot paths, anything you skipped and why, and any place where you had to deviate from this brief. Leave the demo server running on 8010 on the feature branch when you finish.
