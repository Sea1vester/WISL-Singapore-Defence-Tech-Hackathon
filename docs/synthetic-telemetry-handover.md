# WISL synthetic telemetry handover

Feed this file to an implementation agent as the spec.
Do not invent a second architecture.
Do not let an LLM write numeric telemetry rows.

Each sentence in this document is a requirement unless it is labeled as context.

## One-line job

Build `sdth-synth/`, a generator that creates **new** vendor-native drone logs.
Gold files in `raw_telemetry-datasets/` stay frozen.
The generator simulates a physically consistent flight, dresses it in every format the existing parser registry already accepts, then keeps the file only if it is realistic and not a clone.

## Locked product decisions

These came from the plan review.
Do not reopen them unless the human says so.

- Purpose of v1: **demo theater**. Cesium replay must look like a real flight, including a GPS-weak `operator_warning`. Parser round-trip and labeled events are still required, but visual believability is the headline.
- Formats in v1: **all registry formats**. Not DJI-only.
- Engine: **hybrid**. Kinematic core plus DJI/text skins. PX4 ULog and ArduPilot DataFlash/tlog come from SITL, not from an LLM and not from a hand-rolled binary writer unless SITL is proven unavailable and a writer round-trips the existing parsers.
- SITL path (locked 2026-09-11): **install PX4 SITL and ArduPilot SITL**. Do not fall back to L1-only or a homemade encoder unless the human reopens this.
- Novelty: **new geography**. New serials, new GUIDs, new homes, relative-path DTW so a time-shifted gold log cannot pass, and a default operating area that is not a gold home and not the demo origin `1.3521, 103.8198`.

## What you must not do

- Do not overwrite, jitter, resample, or time-shift files under `raw_telemetry-datasets/`.
- Do not fit envelopes on already-synthetic junk (`autonomous_*.csv`, `SurveilDrone-Net23.csv`, `uav_navigation_dataset.csv`, the 8-row demo fixtures).
- Do not prompt an LLM to emit latitudes, speeds, voltages, quaternions, or CSV rows.
- Do not copy `RECOVER.*` serials, `DETAILS.guid`, or gold home coordinates into emitted files.
- Do not put this generator inside `sdth-telemetry/parsers/`. Parsers are the consumer and the realism oracle.
- Do not teach detectors new rules to make fake data pass. If generated data trips a detector incorrectly, fix the generator.

## Repo context

This is WISL for the Singapore Defence Tech Hackathon.
The product parses recorded vendor logs, normalizes to canonical L2 JSON, stores SQLite behind an HTTP API, indexes incidents, and replays in Cesium.

Relevant trees:

- `sdth-telemetry/parsers/` - the registry that must accept generated files (`registry.py`, `detect.py`, `dji_csv.py`, `px4_ulg.py`, `ardupilot.py`, `excel.py`).
- `sdth-telemetry/platform-api/app/canonical_series.py` - L1 record to L2 canonical.
- `sdth-telemetry/platform-api/app/schemas.py` - `CANONICAL_JSON_SCHEMA`.
- `sdth-telemetry/platform-api/app/detectors.py` - rule-based incidents on L2. `operator_warning` fires from warning/tip text that matches `WARNING_KEYWORDS` (includes `"gps"`).
- `sdth-telemetry/fixtures/demo/controller_mission_alpha.csv` - 8-row staircase. Negative example. Parses. Looks fake. GPS-weak at t=3. The demo story should survive, the staircase should not.
- `sdth-ingestion pipeline/` - edge uploader watches a directory and POSTs raw bytes to `/v1/logs/upload`. Generated files must work on that path.
- `sdth-replay/` - CesiumJS. Demo theater is won or lost here.
- `raw_telemetry-datasets/` - mixed corpus. See gold list below.

Target parser coverage today: DJI, PX4/Auterion, ArduPilot.
Hermes 900, Orbiter 4, and aunav.NEO HD remain as format-coverage claims from sample logs, not hardware-validated flights.
Generate those formats anyway because the user locked **all registry formats**.

## Parser keys you must emit

`detect_registry_format` / `parse_raw_log` in `sdth-telemetry/parsers/registry.py` must return a payload for each of these.

| Parser key | File shape | How to generate |
| --- | --- | --- |
| `dji_csv` | CSV with markers `OSD.latitude`, `OSD.longitude`, `BATTERY.chargeLevel` | Kinematic core + DJI FlightRecord skin. Gold prior: `raw_telemetry-datasets/dji.csv` and `unknown.csv`. |
| `dji_excel` / `excel` | `.xlsx` with the same DJI columns | Same skin written through openpyxl. `excel.py` already maps this. |
| `px4_ulg` | `.ulg` | PX4 SITL (or gazebo-less SITL) mission from the same scenario card. Must round-trip `parse_px4_ulg_to_l1`. |
| `ardupilot_bin` | DataFlash `.bin` | ArduPilot SITL. Round-trip `parse_ardupilot_bin_to_l1`. |
| `ardupilot_tlog` | MAVLink `.tlog` | ArduPilot SITL or MAVProxy log of the same run. Round-trip `parse_ardupilot_tlog_to_l1`. |
| `hermes900` | `.stanag` / syslog-like lines | Text skin matching `_HERMES_LINE` and `mock_logs/flight_log.stanag`. |
| `orbiter4` | `.json` (or `orbiter*.csv`) | Text skin matching `_orbiter_record` and `mock_logs/orbiter_log.json`. |
| `aunav` | `.ros` lines | Text skin matching `_AUNAV_LINE` and `mock_logs/robot_state.ros`. Ground vehicle. Do not make it fly. |
| `vendor_hex` | `timestamp,HEX` lines | Text skin matching `_parse_hex`. |

If a format cannot be produced yet, fail the build for that skin with a clear skip reason.
Do not silently emit a CSV and rename the extension.

## Gold vs junk

Fit priors and novelty checks on gold only.

Gold:

- `raw_telemetry-datasets/dji.csv` (2781 rows) and `unknown.csv` (3274 rows). Real DJI FlightRecord. 180+ columns. Units are ft, MPH, F. Mini 4 Pro serials. Real `APP.warning` codes like `GPS signal weak. Hovering unstable. Fly with caution (Code: 30008).`
- Three PX4 ULogs in `raw_telemetry-datasets/*.ulg`.
- `raw_telemetry-datasets/sample_crash_log.bin`.
- `raw_telemetry-datasets/dronekit-la-testdata-master/flight.tlog` and `log171.bin`.

Hold out: do not fit the DJI envelope on both gold CSVs.
Fit on `dji.csv`.
Hold out `unknown.csv` as the unseen realism reference.

Junk / do not fit:

- `sdth-telemetry/fixtures/demo/controller_mission_*.csv` (8-row staircases). Use as a negative test: a generator that emits this shape must fail the realism gate.
- `raw_telemetry-datasets/autonomous_drone.csv`, `autonomous_delivery_drone_telemetry.csv`, `SurveilDrone-Net23.csv`, `uav_navigation_dataset.csv`.

Auxiliary only (mission grammar or labels, not DJI column stats):

- KABR CSVs, `UAV_telemetry_dataset/` JSON waypoints, `alt_200/` sim logs, `drone_temparing_dataset_v2/`.

## Architecture

Pipeline order is fixed:

1. **Corpus index** lists gold paths and refuses junk.
2. **Profiler** extracts, per format: column set, units, `dt` histogram, missingness mask, warning/mode codebook, percentile envelopes for speed, climb, yaw rate, battery slope, sat count.
3. **Scenario card** (YAML or JSON, schema-validated). An LLM may write this card. It may not write samples. Required fields: phases (`ground`, `takeoff`, `cruise`, `hover`, `rth`, `land`), duration, home lat/lon (must pass geography rule), wind, event cues such as `gps_degraded_at_s`, `operator_warning_text` chosen from the codebook.
4. **Flight core** integrates one SI time series: timestamp, lat, lon, alt_m, vn/ve/vd or speed, roll/pitch/yaw deg, battery percent and voltage, gps quality latent, flight mode, on_ground, extra event flags. Position integrates from velocity. Speed must match geodesic `d(lat,lon)/dt` within the gold residual band. Battery is energy: drain tracks current, current tracks climb and speed, voltage tracks percent. GPS sats, gpsLevel, and GPS warnings are one latent. `isOnGround` is true iff height is near 0 and the phase is ground or landed. Aunav uses a ground-only core (pos_x/pos_y, no flying).
5. **Format skins** expand that series. DJI skin fills FlightRecord columns, including empty cells the way gold leaves them empty, sampling jitter from the gold `dt` histogram, and warnings from the codebook. PX4/ArduPilot skins prefer SITL driven by the same scenario (waypoints, wind, GPS-loss cue). Hermes/Orbiter/aunav/hex skins are text packers.
6. **Realism gate** then **novelty gate**. Fail regenerates with a new seed. CI must run both gates.

LLM role is only step 3, and even then a human-authored YAML fixture is enough for v1.
Do not block v1 on Ollama.

## Canonical series the core should match

L2 shape from `canonical_series.py` / `CANONICAL_JSON_SCHEMA`:

- `flight_id` string
- `timestamp_utc` string
- `position.lat` `position.lon` `position.alt_m`
- `attitude.roll_deg` `attitude.pitch_deg` `attitude.yaw_deg`
- `battery.percent` `battery.voltage_v`
- `sensors` object (warnings, flight_mode, gps_satellites, extras)
- `metadata.source` `metadata.drone_model` `metadata.frame`

DJI CSV parser mapping you must satisfy after parse:

- `OSD.latitude` / `OSD.longitude` → `lat` / `lon`
- `OSD.height [ft]` preferred for `alt_m` (times 0.3048) when abs(height) > 0.05, else `OSD.altitude [ft]`
- `OSD.pitch` `OSD.roll` `OSD.yaw`
- `BATTERY.chargeLevel` `BATTERY.voltage [V]`
- `OSD.hSpeed [MPH]` → `speed_ms`
- `APP.warning` → `sensors.warning` after canonicalization
- `OSD.flycState` → `flight_mode`
- `OSD.gpsNum` → `gps_satellites`
- `HOME.latitude` / `HOME.longitude`

DJI detection requires all three markers: `OSD.latitude`, `OSD.longitude`, `BATTERY.chargeLevel`.

## Dual gates (tests, not vibes)

### Realism (must pass)

- `parse_raw_log` succeeds and returns 2+ L1 records.
- Every canonical point validates `CANONICAL_JSON_SCHEMA`.
- Kinematics: `|measured_speed - geodesic_speed|` inside the gold residual band. No teleports. Altitude continuous except known land/takeoff.
- Energy: battery percent non-increasing except charger-on-ground. Voltage tracks percent. Current rises on climb.
- Coupling: `isOnGround` iff height near 0. GPS sats vs quality vs warning codes are consistent. Mode changes are rare and sticky.
- Idiosyncrasy: DJI warnings drawn from the gold codebook (`Code: NNNNN` style). Sampling jitter matches gold `dt`. Some DJI cells empty.
- Distribution: KS or Wasserstein on the feature vector (speed, climb, yaw rate, battery slope, sat count, dt) versus held-out gold of the same family, inside a configured band.
- Demo theater extra: Cesium path is a flight, not a raster or an 8-point staircase. Duration should be minutes, not 8 seconds, for the showcase DJI mission.
- Negative test: the current demo fixture shape (1e-5 deg/s latitude steps, ~2% battery per second) must fail this gate.

### Novelty (must pass)

- No gold serial, GUID, or filename reuse.
- Default home is at least 50 km from every gold home extracted from gold DJI/PX4/ArduPilot logs, and at least 50 km from `1.3521, 103.8198` and from PX4 SITL Zurich `47.397742, 8.545594`.
- Relative-path DTW (subtract home, compare NED tracks) above a clone threshold versus every gold track. A time-shifted copy of `dji.csv` must fail.
- Exact warning-sequence copy of a gold log fails.
- Similarity that is allowed: same column set, similar speed histogram, same warning vocabulary, same phase grammar (takeoff-cruise-land).

## Demo theater requirements

The two-laptop demo today: Laptop A drops a log into a watched directory.
Laptop B parses, detects incidents, opens Cesium.

Checked demo behavior: `operator_warning` with evidence `GPS signal weak`, then a mitigation bulletin at `min_flights=2`.

Generated showcase missions must:

- Upload through `/v1/logs/upload` as raw files.
- Parse without special-casing.
- Replay in Cesium as a continuous Mini 4 Pro (or PX4/ArduPilot) flight over the **new** geography.
- Include at least one GPS-degraded stretch whose `APP.warning` / L2 `sensors.warning` contains `gps` so `operator_warning` still fires.
- Include a second distinct generated flight so `min_flights=2` still works.
- Not use gold serials or gold homes.

Replace `sdth-telemetry/fixtures/demo/controller_mission_alpha.csv` and `controller_mission_bravo.csv` only after generated files pass both gates and the existing demo e2e tests are updated to point at the new fixtures.
Until then, keep the old fixtures so current tests stay green.

## Package layout

Create `sdth-synth/` at repo root, next to `sdth-telemetry/`.

Suggested modules:

- `pyproject.toml` with a `synth` CLI and pytest.
- `src/sdth_synth/corpus.py` - gold index, junk denylist, holdout split.
- `src/sdth_synth/profile.py` - envelope and codebook extraction. Writes a report JSON.
- `src/sdth_synth/scenario.py` - typed scenario card + validation, including geography rule.
- `src/sdth_synth/core.py` - kinematic integrator. Ground-vehicle variant for aunav.
- `src/sdth_synth/skins/dji_csv.py`
- `src/sdth_synth/skins/dji_excel.py`
- `src/sdth_synth/skins/hermes.py`
- `src/sdth_synth/skins/orbiter.py`
- `src/sdth_synth/skins/aunav.py`
- `src/sdth_synth/skins/vendor_hex.py`
- `src/sdth_synth/skins/px4_sitl.py`
- `src/sdth_synth/skins/ardupilot_sitl.py`
- `src/sdth_synth/gates.py` - imports parsers from `sdth-telemetry/parsers` (sys.path or install the parsers package). Do not fork parser code.
- `src/sdth_synth/cli.py` - `synth profile`, `synth scenario`, `synth generate --format all`, `synth gate`.
- `tests/` - parse round-trip per format, negative staircase test, novelty clone test, geography test, operator_warning test.
- `scenarios/` - checked-in YAML cards for demo alpha/bravo replacements.
- `out/` - generated artifacts, gitignored except tiny fixtures you intend to commit.

CLI sketch:

```bash
python -m sdth_synth profile --gold raw_telemetry-datasets --out sdth-synth/out/profile.json
python -m sdth_synth generate --scenario sdth-synth/scenarios/demo_alpha.yaml --formats all --out sdth-synth/out/demo_alpha/
python -m sdth_synth gate sdth-synth/out/demo_alpha/
```

## Implementation order

Do this in order.
Do not start SITL before the core and DJI skin pass gates.
Do not start Hermes/Orbiter skins before DJI looks right in Cesium.

1. Corpus index + profiler report for gold DJI. Human-readable JSON of envelopes and codebook.
2. Flight core unit tests: integrate a hover, a climb, a turn. Assert speed vs geodesic, battery monotonic, on_ground coupling.
3. DJI CSV skin + both gates. Generate a minutes-long GPS-weak mission. Parse with `python -m parsers` from `sdth-telemetry/parsers`. Confirm Cesium replay is not a staircase.
4. Text skins: Hermes, Orbiter, aunav (ground only), vendor hex, DJI xlsx. Same core series, different packers. Parse via `parse_raw_log`.
5. PX4 SITL skin: scenario → mission → `.ulg` → `parse_px4_ulg_to_l1`. Document the exact docker/make command. If SITL cannot run in the local environment, make the skin fail loud and add a developer note. Do not commit a fake `.ulg`.
6. ArduPilot SITL skin for `.bin` and `.tlog`, same rule.
7. Only then replace demo fixtures and update `test_demo_e2e.py`.

## Verification

Minimum proof a change is done:

- `pytest` in `sdth-synth` is green.
- `pytest` in `sdth-telemetry/parsers` is still green.
- For each emitted format, `parse_raw_log` returns L1 and `series_from_l1_payload` validates L2.
- A time-shifted copy of `raw_telemetry-datasets/dji.csv` fails novelty.
- The 8-row staircase shape fails realism.
- Showcase DJI output, uploaded like a controller log, produces `operator_warning` and a plausible Cesium track over new geography.

If browser tools exist, actually open Cesium and fly the clock.
A screenshot of the first frame is not enough.

## SITL notes

PX4 parser default origin when GPS is missing is Zurich `47.397742, 8.545594`.
Do not leave generated PX4 flights on that origin.
Set SITL home from the scenario card.

ArduPilot and PX4 SITL are the honest way to get `.ulg` / `.bin` / `.tlog`.
They are also heavy.
Keep kinematic DJI working on a laptop with no simulator.
Gate SITL tests so they skip only when the simulator binary is missing, and print how to install it.

## Incident coupling

`detectors.py` treats warning text containing keywords like `gps` as `operator_warning`.
DJI gold warnings look like `GPS signal weak. Hovering unstable. Fly with caution (Code: 30008).`
Sample from that codebook.
Do not invent `GPS is kinda bad lol`.

Do not force battery plunges or GPS teleports to create incidents.
Those trip other detectors (`battery_plunge`, GPS jump) and look fake.

## Success looks like

A folder of new logs, one per registry format, from one scenario card.
None of them are in `raw_telemetry-datasets/`.
They parse today, replay as flights, fire GPS-weak on the DJI pair, and fail a clone check against gold.

## Pointers

- Plan surface: `my_team_workspace/shared_lavish_plan.html`
- This spec: `docs/synthetic-telemetry-handover.md`
- Root README: `README.md`
