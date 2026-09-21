# WISL — Recorded Flight Evidence for Fleet Learning

Post-flight evidence pipeline for mixed UAS fleets. A controller-side watcher waits until a recorded log is size-stable, hashes it and uploads the raw bytes; a server-side registry parses supported formats into a canonical L2 series of position, attitude, battery, sensors and metadata; deterministic detectors index observations; a 3D CesiumJS replay follows recorded time; queries return stored evidence; recurring signatures produce reviewable bulletins. The server registry accepts thirteen recorded-log extensions, from DJI, PX4 and ArduPilot logs to Hermes, Orbiter and aunav text skins. An optional local model can draft a hypothesis against checked evidence identifiers — numbers and detectors stay rule-based.

Team: Sylvester Lim, Inessa Wong · Singapore Defence Tech Hackathon 2026 · 20 September 2026

## Start the local demo

Requirements: Python 3.11 or later. From this repository's root:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -e './sdth-telemetry/platform-api[dev]'
./sdth-telemetry/scripts/demo-console.sh
```

Once dependencies are installed, only the last command is needed.
The launcher prints and opens **<http://127.0.0.1:8010/demo/>**.
`http://127.0.0.1:8010/` and `/replay/` now redirect there.
`/replay/?embed=1` is only the 3D view inside the console.
In **Session**, enter the development key `dev-teammate-key-change-me`, or one key from your `INGEST_API_KEYS` setting.
This launcher runs the API and one background ingestion worker locally; Redis is not needed.
Stop it with Ctrl+C.
Run it again to recover interrupted ingestion jobs.

### Use the replay workspace

1. Choose a stored record in the **Mission library** sidebar. Search filters the loaded records. On small screens, use **Flight library** to open the drawer. The last selected flight loads automatically when you return.
2. To add a record, choose **Import log**, then drop a file in **Logs & uploads**. For a quick start, use **Try an example log with a GPS warning** in that tab. Its bytes are processed by the real pipeline; duplicate uploads reuse the existing record.
3. Wait for **Ready to review**. The replay fills the main view. **Tabletop** presents the recorded path above a low-poly terrain model with painted teal facets, solid map features and subtle tilt-shift focus; **Map** shows OpenStreetMap imagery on the cached elevation surface. Drag the scene to tilt/orbit and scroll to zoom. Shadows are disabled in both views. The enlarged aircraft model is for visibility. Use **Play/Pause**, **Restart**, playback-speed and timeline controls to inspect the recorded flight. The telemetry strip shows recorded altitude, battery and UTC; **Track speed** is derived from consecutive positions. The inset shows the recorded route.
4. Use the bar below the replay: **Mission analysis** contains observations and record queries, **Recurring patterns** compares stored signatures, and **Bulletins** holds reviewable follow-up. Switching these tabs keeps the replay on screen.
5. Click **Replay this observation** to pause at its recorded timestamp. Ask **What happened?**, **Where is the evidence?** or **Similar warnings** for deterministic evidence-backed answers.
6. Expand **AI-assisted analysis** inside Mission analysis and click **Analyze fleet records** for optional fleet interpretation. Its explanations are unverified hypotheses, even when the referenced evidence IDs are valid.

The bundled GPS-warning, dropout, Orbiter, exercise and supplemental logs in `sdth-demo/fixtures/` are synthetic copies.
They are imported into the Mission library when you connect a Session.
The term "jamming" in a simulator filename is not a causal diagnosis.

### Optional audit of the exercise fixtures

The same exercise CSVs can still be loaded through the checksum-gated script:

```sh
.venv/bin/python sdth-telemetry/scripts/load_demo_failures.py
```

Duplicate content reuses the existing record.
See the [validation report](docs/submission/corpus-validation.md) for supported conclusions and simulation limitations.

## Demo walkthrough

The recorded demo sequence (narrated in [demo-pitch-vo.md](docs/submission/demo-pitch-vo.md)):

1. Open the nominal control mission; the log parses cleanly and the detector engine flags zero incidents.
2. Open **Supplemental GPS-weak mission**, press Play on the 3D track, switch between **Map** and **Tabletop** views.
3. Click **Replay this observation** to jump to the GPS-weak warning marker.
4. In **Mission analysis**, ask **What happened?**, then **Similar warnings** — a second stored flight threw the exact same warning.
5. Open **Recurring patterns** and click **Create review bulletin** — a human-review bulletin, never an automated vehicle command.
6. Stay on the mission and click **⬇ Comprehensive PDF**; open the downloaded comprehensive report.
7. Optionally expand **AI-assisted analysis** and click **Analyze fleet records** (requires Ollama serving `deepseek-r1:7b`).
8. Close on **Exercise · Recording ends airborne** — the log ends while the aircraft is still airborne.

## Optional local model

With Ollama installed, run these in a separate terminal:

```sh
ollama pull deepseek-r1:7b
ollama serve
```

The download is needed once; skip `ollama serve` if it is already running. The launcher defaults to `http://127.0.0.1:11434` and `deepseek-r1:7b`. Set `OLLAMA_MODEL` or `OLLAMA_BASE_URL` before starting the demo to select another local installation. Parsing, replay, record queries and bulletins work without the model. Local inference does not make replay air-gapped: Cesium and map assets still require network access. The three bundled demo regions have local elevation and OpenStreetMap geometry caches, so terrain loading does not depend on an external request. Map imagery and the Cesium runtime still require network access. An upload outside those regions is labelled **Terrain uncached · flat globe**; no terrain is invented. See [map data and styling notes](sdth-replay/public/assets/TABLETOP-SOURCES.md).

## Runtime and evidence

The database is `data/demo-console.db`; raw uploads, reports and visuals also stay under `data/`. These runtime files are excluded from Git. `WISL_PYTHON=/absolute/path/to/python` selects another Python environment; `API_PORT=8011` selects another local port. See the [detailed runbook](docs/submission/demo-runbook.md) for the complete demonstration sequence.

## Layout

The five packages, as described in the report:

- [`sdth-ingestion pipeline/`](sdth-ingestion%20pipeline/README.md) — edge folder watcher and format parsing registry.
- [`sdth-telemetry/`](sdth-telemetry/README.md) — FastAPI platform, SQLite storage, standardized projection, incident detectors, and query engine.
- [`sdth-replay/`](sdth-replay/README.md) — web-based 3D CesiumJS replay viewer.
- [`sdth-demo/`](sdth-demo/) — unified web mission console (`/demo/`).
- `sdth-synth/` — synthetic log generation engine driven by kinematic scenario cards. It is gitignored in this checkout, so it is not present in a fresh clone.

## Validation

Headline results from the report (§3):

- 126 logs processed: the 90-file simulator inventory (ten scenario cards, nine format skins) plus a second gated set of 36 exports. Every file projected to schema-valid L2 within a 30-second bound.
- 40 of 90 original files and all 36 gated exports met their declared scenario-card expectations; the normal control produced zero incidents.
- A representative upload (GPS-warning CSV plus frozen-position JSON) reached ready status in 1.223 s, persisting 225 standardized records and indexing the expected alerts.
- Test suites: 161 platform tests, 28 parser tests, 15 replay engine tests, 5 UI tests — all passing.
- The audit caught and fixed a DJI parser defect that treated a true 0.0 m altitude as missing and fabricated takeoff spikes.

Details: [docs/submission/corpus-validation.md](docs/submission/corpus-validation.md).

## Submission documents

- [Final report (LaTeX source)](docs/submission/WISL_FinalReport_v1.tex)
- [Two-minute demo voiceover](docs/submission/demo-pitch-vo.md)
- [Video shot list and handoff](docs/submission/video-handoff.md)
- [Three-minute pitch script](docs/submission/pitch-script.md)
- [Reserve Q&A](docs/submission/pitch-qa-kiv.md)
- [Cited use-case research](docs/submission/research-brief.md)
- [`archive/`](archive/) — superseded materials kept for history.

## Legacy

An earlier raw-log workflow ran across two laptops over Tailscale; see [sdth-telemetry/docs/two-laptop-demo.md](sdth-telemetry/docs/two-laptop-demo.md) for that legacy optional path.

## Not in scope

Live airframe or ground-control-station connections, onboard or edge inference, automated fleet fixes, operational accreditation, and Azure deployment are not part of this demo.
