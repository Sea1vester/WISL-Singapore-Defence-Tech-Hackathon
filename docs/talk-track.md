# WISL code-check talk track

Memorise this. Each block is what to say out loud, in order, mapped to the scorecard. Numbers are from the repo as of 24 Sep; if a live number differs, say the live one.

---

## The one-liner (say this first, 20 seconds)

> "WISL is a post-flight evidence pipeline for mixed drone fleets. You give it a recorded flight log from any of nine vendor formats. It hashes it, parses it into one canonical telemetry schema, runs deterministic detectors that flag incidents with the exact samples they fired on, replays the flight in 3D at the incident timestamp, and turns recurring signatures across the fleet into human-review bulletins. Everything numeric is rule-based and reproducible. The local model is optional and can only draft a hypothesis that cites evidence that already exists."

---

## 1. Happy path (20%) — what to say while the demo runs

Walk the runbook: normal control → GPS-weak mission → replay to observation → What happened? / Similar warnings → Recurring patterns → bulletin → PDF. While doing it, narrate:

- "One command starts everything: `demo-console.sh`. One Python process, SQLite, an in-process worker. No Redis, no Docker, no internet needed for parsing, detection, replay of the bundled regions, or the PDF."
- "Watch the terminal. Every upload prints five stages: **received → parsed → canonical → detected → done**, each with its time in milliseconds. A 200-row DJI CSV goes end to end in about 40 ms: parse ~7 ms, canonical write ~20 ms, detectors ~7 ms."
- Drop `dji_csv_gps_jamming.csv` fresh, then drop it **again**: "Same bytes, same SHA-256, so it returns the existing upload — `dedup=true`. Evidence identity is the checksum; the flight id is literally derived from it."
- On the normal control: "Zero incidents on a clean flight is a result, not an absence. It's our false-positive control."
- On the PDF: "Built by ReportLab from stored evidence only. No model call. Same input, same PDF."

Envelope, said plainly: "Post-flight logs only. Thirteen file extensions, nine vendor families. Thresholds are demonstration values. Terrain is cached for three regions; elsewhere we show a flat globe rather than invent terrain."

---

## 2. Breadth / unhappy path (20%) — hand them the controls

- "Your rubric example is 'shift north 2 km, drop 10% of observations'. We generated exactly that through our synthetic scenario generator, and you can do it live to any DJI CSV you bring."
- Pre-built in `sdth-demo/fixtures/perturbed/` — expected outcomes, memorise these three lines:
  - **normal control, +2 km N, 10% dropped (215→197 rows)** → **no incidents**. "The 10% drop creates one-to-three-second gaps, well under the 15 s telemetry-gap threshold, and no implied-speed jump."
  - **GPS-weak, +2 km N, 10% dropped (225→202)** → **operator_warning ×1**. "The warning text survives subsampling."
  - **GPS-weak + 20 s block cut mid-cruise (202→182)** → **operator_warning ×1 + telemetry_gap ×1**. "The gap detector fires on the cut, not on the random drop."
- Live: `generate_perturbed_fixtures.py --input their.csv --north-m 2000 --drop-frac 0.10 --cut-gap`. "The script prints what the detectors observed; then upload the result and compare with the terminal."
- Other things to offer: other format skins (Excel, Hermes, Orbiter) of the same scenarios in `output/evidence/corpus-validation-v2/failure-fixtures/`; an unsupported extension → **415** at receive; a corrupted file → **stage=failed**, status `failed` with the parser error, nothing half-written because the canonical write is one transaction; wrong API key → **401**; a log outside cached regions → "Terrain uncached · flat globe".
- Corpus numbers: "126 synthetic logs across nine formats all projected to schema-valid L2 within the 30-second bound. 36 of 36 gated exports met their scenario-card expectations. We also ran public real logs through it for a false-positive audit."

---

## 3. Technical depth (30%) — the parts that are ours

Say these as "what we built", pointing at the file each time.

1. **Format registry** (`parsers/registry.py`) — "Extension plus content sniffing picks a parser. Every parser emits one L1 contract. DJI CSV and Excel, PX4 ULog via pyulog, ArduPilot bin/tlog via pymavlink, and text skins for Hermes, Orbiter, aunav and vendor hex. Adding a vendor is one parser file; the edge stays format-neutral."
2. **Canonical L2** (`canonical_series.py`) — "L1 is projected into a schema-validated series: UTC timestamp, position with a frame tag, attitude, battery, sensors, metadata with value origin. Local-NED-only logs get projected from a reference origin and tagged. Detectors are written once against L2, not nine times against vendors. Schema validation caught a real bug: the DJI parser treated a true 0.0 m altitude as missing and fabricated takeoff spikes."
3. **Detectors** (`detectors.py`, 660 lines) — "Eight deterministic rules: battery low/critical (20/10%), battery plunge (15 points in 60 s), telemetry gap (15 s), attitude shock (40°/70°), GPS jump (implied speed 120 m/s air, 15 m/s ground, 25 m step), last-known-position (30 s frozen), mission incomplete (ends airborne), operator warning (keyword match on GPS/failsafe/motor/compass/RTH/link text). Each incident stores the timestamped L2 samples it fired on in `evidence_json`. That's what 'Where is the evidence?' shows and the PDF prints."
4. **Fleet layer** (`incidents.py`, `bulletins.py`) — "Rule incidents are replaced atomically per flight, then `incident_patterns` is rebuilt across the fleet by signature. Two flights with the same signature is a recurring pattern; a bulletin is a review record a human signs off. Never a vehicle command."
5. **Privacy** (`privacy.py`) — "Operator home coordinates are redacted before persistence and written to an audit table. Retention is enforced on every ingest."
6. **Replay** (`sdth-replay`) — "CesiumJS, served locally, no Ion token. The viewer only sees `/v1/flights/{id}/path`, a stable contract; never raw vendor rows. Terrain and OSM tiles are cached for the three demo regions."
7. **Model guardrail** (`demo_api.py`) — "At most 100 flight summaries and 50 incidents go to a local Ollama model. `_validate_model_response` rejects any hypothesis citing an incident id not in that context. Timeouts degrade to the deterministic path. The console labels the output as unverified."
8. **Synthetic generator** (`sdth-synth`, local) — "A kinematic flight core integrates scenario cards into flights, then vendor skins write native files. Two gates: physical sanity, and a 50 km geography gate away from real reference homes. Scenario cards are ground truth for expected detector outcomes."

Test line: "197 platform tests, 30 parser tests, 27 replay tests, 5 console tests. All green."

---

## 4. Ownership (10%) — decisions and trade-offs

Have one sentence ready for each "why":

- **Why parse server-side, not on the controller?** "Edge stays tiny and format-neutral; raw bytes are preserved for audit; a new vendor is a server change, not a firmware change. Cost: bigger uploads."
- **Why checksum identities?** "Idempotent re-ingest, global dedup, tamper-evident. Cost: change one byte and it's a new flight — by design."
- **Why deterministic detectors instead of a model?** "In July we let an LLM normalise logs. It invented values. We replaced it with parsers plus schema validation and demoted the model to hypothesis-drafting. Cost: hand-tuned thresholds, no learned anomaly detection."
- **Why SQLite?** "One file, one process, reproducible for a judge. The same schema and worker run under the Redis/Compose deployment we built for the two-laptop demo."
- **Why synthetic data?** "No rights to a large real failure corpus. Scenario cards give us ground truth. Everything is labelled synthetic; real public logs were used only for the false-positive audit."
- **Why local Cesium and tile cache?** "Offline replay for the demo regions. We refuse to invent terrain outside the cache."

Live modification to offer: change a threshold in `detectors.py`, call `POST /v1/flights/{id}/index-incidents`, show the incident set change. Or run the test suite.

Individual contributions: say who built what. Be specific — file names, not areas.

---

## 5. Iteration (20%) — the story in five beats

"Seventy-plus commits over 21 active days from July 11 to September 21. The pivots:"

1. **July** — "SQLite + Ollama 'local cloud', first parsers for ulg/bin/tlog/csv/xlsx. The model was the normaliser."
2. **Mid-August** — "Unified parser contract, deterministic L2 persistence, incident indexing across missions, redaction and retention audit, mitigation bulletins, secure controller delivery, two-laptop Tailscale demo. Built a raylib replay and replaced it with Cesium the same week."
3. **Early September** — "Refocused on cheap drones after mentor feedback. Added the UXO risk detectors — mission-incomplete and last-known-position — and the Mission Control replay UI."
4. **Mid-September** — "Built the gated synthetic corpus, audited it, found and fixed the DJI zero-altitude bug. Relabelled fixtures 'Exercise' after feedback that 'jamming' in a filename read as a causal claim."
5. **Final week** — "PDF without a model call, false-positive fixes from real public logs, real-log coverage audit, local Cesium and tile cache so replay works offline, per-stage timed logging."

Before/after artefacts: `output/evidence/demo-console-live-before-altitude-fix.json` vs `demo-console-live.json`. Superseded work is in `archive/`, including the dropped Orcrist collaboration brief and the old report pipeline.

---

## Bonus — operational realism

"The mission thread is: controller-side watcher sees a size-stable log, hashes and uploads it; the platform produces evidence; a human reviews a bulletin. No automated fleet action. The edge uploader survives restarts via its manifest. Operator locations are redacted. Replay works offline for cached regions. Not in scope: live GCS links, onboard inference, automated fixes, accreditation."

---

## If asked something you don't know

Say: "I'll show you in the code." Open the file. Don't guess a number.
