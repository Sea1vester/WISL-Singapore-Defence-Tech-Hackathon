# Code-check session guide

For the SDTH technical assessment (30–60 min, one mentor). Rubric weights: happy path 20 · breadth on new inputs 20 · technical depth 30 · ownership 10 · iteration 20 · bonus operational realism +10.

Repository: <https://github.com/Sea1vester/WISL-Singapore-Defence-Tech-Hackathon>. Architecture: [`ARCHITECTURE.md`](ARCHITECTURE.md).

## Before the slot

```sh
git status                      # clean, on main
./sdth-telemetry/scripts/demo-console.sh   # terminal stays visible: this is the log feed
```

Keep this terminal on screen for the whole session — every upload prints `stage=received → parsed → canonical → detected → done` with timings.

Optional, in a second terminal: `ollama serve` (model `qwen2.5:7b-instruct`). Not required for anything deterministic.

Have open: the console at <http://127.0.0.1:8010/demo/>, `docs/ARCHITECTURE.md`, `sdth-telemetry/platform-api/app/detectors.py`, `sdth-telemetry/parsers/registry.py`.

## 1. Live demonstration (happy path, ~8 min)

Follow [`submission/demo-runbook.md`](submission/demo-runbook.md) steps 1–6: normal control (zero incidents) → GPS-weak mission → replay to the observation → What happened? / Similar warnings → Recurring patterns → bulletin → Comprehensive PDF.

Then do one **fresh ingest in front of the mentor**: Import log → drop `sdth-demo/fixtures/dji_csv_gps_jamming.csv`. Point at the terminal: parse, canonical, detect timings in milliseconds. Drop the same file again: `dedup=true`, same upload id — evidence identity is by checksum.

## 2. Architecture (~5 min)

Talk from the diagram in `ARCHITECTURE.md`. Land these points:

- Raw bytes in, parse server-side, checksum identities, L1 → L2 canonical schema, deterministic detectors that cite the L2 samples they fired on.
- Model is optional and validated against evidence IDs; numbers never come from it.
- One process, SQLite, in-process worker; Redis/Compose path exists but isn't needed.

## 3. Hands-on by the assessor — unhappy path (breadth, ~10 min)

The rubric's own example is "shift north 2 km, randomly remove 10% of observations". We pre-generated exactly that through the synthetic generator, and can do it live to any DJI CSV the mentor brings.

Pre-built, in `sdth-demo/fixtures/perturbed/` (not auto-imported — upload them via Import log so the mentor sees a fresh ingest):

| File | Perturbation | Observed detectors |
|---|---|---|
| `dji_csv_perturbed_normal_control_north2km_drop10.csv` | home +2 km N, 10% rows dropped (215 → 197) | none — control stays clean |
| `dji_csv_perturbed_gps_weak_north2km_drop10.csv` | home +2 km N, 10% rows dropped (225 → 202) | `operator_warning` ×1 |
| `dji_csv_perturbed_gps_weak_north2km_drop10_gap20s.csv` | as above + 20 s block cut mid-cruise (202 → 182) | `operator_warning` ×1, `telemetry_gap` ×1 |

Details and SHA-256s: `sdth-demo/fixtures/perturbed/manifest.json`.

Live perturbation of an arbitrary DJI CSV (the mentor picks the file and the parameters):

```sh
.venv/bin/python sdth-telemetry/scripts/generate_perturbed_fixtures.py \
  --input <their.csv> --north-m 2000 --drop-frac 0.10 --cut-gap --gap-s 20 --out /tmp/perturbed
```

The script prints the detector types it observed; then upload the output through the console and compare with the terminal log.

Other things to invite the mentor to try, and what to expect:

- Any other bundled format: `output/evidence/corpus-validation-v2/failure-fixtures/` has Excel, Hermes and Orbiter skins of the same scenarios.
- A file with an unsupported extension → rejected at `received` with the reason (extension gate).
- A truncated or corrupted file → `stage=failed` in the log, `failed` status with the parser error; nothing half-written (the canonical write is one transaction).
- A log outside the three cached regions → replay says **Terrain uncached · flat globe**; no terrain is invented.
- Uploading with a wrong API key → 401.

Envelope to state plainly: post-flight logs only; 13 extensions; detector thresholds are demonstration values (table in `sdth-telemetry/README.md`); terrain cached for three regions.

## 4. Technical Q&A — likely questions

- **Why not let the model normalise?** We did in July; it invented values. Deterministic parsers + schema validation replaced it; the model now only drafts hypotheses and must cite existing evidence IDs.
- **How do you know a detector hit is real?** Every incident stores the timestamped L2 samples it came from (`sample`/`samples` in `evidence_json`); *Where is the evidence?* shows them; the PDF prints them.
- **What about false positives?** Audit on public real logs found and fixed detector FPs (commit `d56d7d6`) and a DJI parser bug that turned 0.0 m altitude into missing data and fabricated takeoff spikes.
- **Why SQLite?** One file, one process, trivially reproducible for a judge; the schema and worker are unchanged under the Redis/Compose deployment.
- **What's synthetic vs real?** All bundled missions are labelled synthetic and come from gated scenario cards; real public logs were used for the FP audit, not as demo missions.
- **Live modification:** change a threshold in `detectors.py`, re-run `POST /v1/flights/{id}/index-incidents`, show the incident set change. Tests: `cd sdth-telemetry/platform-api && ../../.venv/bin/python -m pytest -q`.

## 5. Iteration evidence (have ready)

`git log --oneline` tells the story; the milestones to point at:

- Jul 11–19: SQLite + Ollama "local cloud", first parsers for `.ulg/.bin/.tlog/.csv/.xlsx`.
- Aug 13–23: unified parser contract, deterministic L2 persistence, SQLite incident indexing across missions, redaction + retention audit, mitigation bulletins, secure controller delivery, two-laptop Tailscale demo, first raylib replay → replaced by Cesium the same week.
- Sep 3–9: cheap-drone focus, visual sidecar, UXO risk detectors (`mission_incomplete`, `last_known_position`), Mission Control replay UI.
- Sep 11–16: audited synthetic failure corpus with gates, tabletop terrain, studio replay redesign, fixtures relabelled "Exercise" after feedback.
- Sep 20–21: PDF without a model call, false-positive fixes on real logs, real-log coverage audit, local Cesium + tile cache for offline replay.

Before/after artefacts: `output/evidence/demo-console-live-before-altitude-fix.json` vs `demo-console-live.json`; `archive/` holds superseded report pipeline and the dropped Orcrist brief. Programme material (proposal, conditional approval, scorecard) is in `archive/reference/`.

## Bonus: operational realism

Mission thread: controller-side watcher → platform → evidence → human-review bulletin, never a vehicle command. Operator location redaction and retention audit. Offline-capable replay for cached regions. Edge uploader survives restarts via its manifest.
