# WISL — Recorded Flight Evidence for Fleet Learning

Post-flight evidence pipeline for mixed UAS fleets. A controller-side watcher waits until a recorded log is size-stable, hashes it and uploads the raw bytes; a server-side registry parses supported formats into a canonical L2 series of position, attitude, battery, sensors and metadata; deterministic detectors index observations; a 3D CesiumJS replay follows recorded time; queries return stored evidence; recurring signatures produce reviewable bulletins. The server registry accepts thirteen recorded-log extensions, from DJI, PX4 and ArduPilot logs to Hermes, Orbiter and aunav text skins. An optional local model can draft a hypothesis against checked evidence identifiers — numbers and detectors stay rule-based.

Team: Sylvester Lim, Inessa Wong · Singapore Defence Tech Hackathon 2026 · 20 September 2026

## Start the local demo

Requirements: Python 3.11 or later, and Node.js 22+ for the first Cesium download. A complete local Cesium build is reused offline. From this repository's root on macOS/Linux:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -e './sdth-telemetry/platform-api[dev]'
./sdth-telemetry/scripts/demo-console.sh
```

On **Windows (PowerShell)**, from the repository root:

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".\sdth-telemetry\platform-api[dev]"
.\.venv\Scripts\python.exe .\sdth-telemetry\scripts\demo-console.py
```

No virtual-environment activation, Bash, `rsync`, Unix `unzip`, or PowerShell execution-policy change is required on Windows. If `py` is unavailable, install Python 3.11+ with its Windows launcher, or use the full path to your Python executable for the first command. The launcher uses the platform's path separator, handles paths with spaces, and fails clearly if the local Cesium build cannot be prepared. The Windows installer uses built-in `curl.exe` and PowerShell `Expand-Archive`; TLS verification stays enabled. `--no-browser` starts the server without opening a tab.

Once dependencies are installed, only the last command for your operating system is needed.
The launcher prints and opens **<http://127.0.0.1:8010/demo/>**.
`http://127.0.0.1:8010/` and `/replay/` now redirect there.
`/replay/?embed=1` is only the 3D view inside the console.
In **Session**, enter the development key `dev-key-12345`, or one key from your `INGEST_API_KEYS` setting.
This launcher runs the API and one background ingestion worker locally; Redis is not needed.
Stop it with Ctrl+C.
Run it again to recover interrupted ingestion jobs.

### Use the replay workspace

1. Open a recorded log in the **Mission explorer** file tree. Filenames keep their original extensions; expand/collapse folders with their chevrons or the Left/Right keys. Up/Down, Home/End and Enter navigate/open tree items; **F2**, right-click or **⋯** opens organisation controls. **New folder** creates a folder inside the selected folder; select **RECORDED LOGS** to create one at the root. Drag logs onto folders or the root heading to move them. Search spans all folders and files. Drag the vertical divider to resize the sidebar, or focus it and use Left/Right; double-click resets it. Folder organisation is shared by authenticated sessions and saved in SQLite, without moving original files or changing evidence. Width and expansion state are remembered for the browser session. On small screens, use **Flight library** to open the drawer.
2. To add a record, choose **Import log**, then drop a file in **Logs & uploads**. New records go into the folder that was open when uploading started. For a quick start, use **Try an example log with a GPS warning** in that tab. Its bytes are processed by the real pipeline; duplicate uploads reuse the existing record and keep its folder.
3. Wait for **Ready to review**. The replay fills the main view. **Tabletop** presents the recorded path above a low-poly terrain model with painted teal facets, solid map features and subtle tilt-shift focus; **Map** shows OpenStreetMap imagery on the cached elevation surface. Drag the scene to tilt/orbit and scroll to zoom. Shadows are disabled in both views. The enlarged aircraft model is for visibility. Use **Play/Pause**, **Restart**, playback-speed and timeline controls to inspect the recorded flight. The telemetry strip shows recorded altitude, battery and UTC; **Track speed** is derived from consecutive positions. The inset shows the recorded route.
4. Click **Mission analysis** beside **Tabletop / Map / Satellite** to open the separate review page. It retains all four tabs: **Mission analysis**, **Recurring patterns**, **Bulletins**, and **Logs & uploads**. Replay pauses while this page is open. **Back to replay** restores the same camera, timestamp and previous play/pause state without reloading the scene. Browser Back/Forward and direct `#/analysis/overview`, `#/analysis/patterns`, `#/analysis/bulletins`, and `#/analysis/logs` routes are supported. The replay uses the full workspace height and a muted blue-grey daytime atmosphere. This is a visual style, not reconstructed weather.
5. Click **Replay this observation** to pause at its recorded timestamp. Ask **What happened?**, **Where is the evidence?** or **Similar warnings** for deterministic evidence-backed answers.
6. Expand **AI-assisted analysis** inside Mission analysis. Select **Ollama** or **OpenAI-compatible** (LM Studio / llama.cpp), enter the local server URL, and click **Check connection & list models**. Choose a model, then **Analyze fleet records**. The panel shows connection, model waiting/generation and evidence-validation progress, elapsed time, and an optional live draft. Only validated output becomes the final answer; its explanations remain unverified hypotheses.

**Terrain coverage and replay cache:** Tabletop draws the full bundled region, rather than a smaller flight-centred patch. A surrounding globe supplies context outside it, but areas outside the elevation cache remain simplified; detailed global terrain/buildings are not included. Devices without globe-polygon clipping support retain a bounded Tabletop view and can use Map for surrounding context. Switching logs keeps the same Cesium viewer and reuses up to two loaded regions' geometry, with a 256-tile globe cache. The first visit to a region shows a preparation screen and waits for geometry before playback, rather than exposing the build-up. Flight telemetry and evidence are fetched afresh; this is not a cached video. GPU geometry reuse lasts while the page is open; refreshing rebuilds it. Downloaded raster tiles still persist in the server's disk cache.

The demo launcher starts an installed Ollama server if needed and preloads `qwen2.5:7b-instruct`. Signing in with the dev key (or returning to an authenticated session) reconnects and warms this default automatically. No second terminal is needed. **Use laptop default** restores it after trying a judge's provider. Existing servers are reused, and Ollama stays running when the demo stops. Set `AUTO_START_LOCAL_MODEL=false` to manage the server yourself; `WARM_LOCAL_MODEL=false` disables preloading. Automatic startup is restricted to the local-demo worker and the configured HTTP loopback address.

The model server must be reachable from the **WISL API host**, not just the browser. Install a suitable Ollama model once if missing, for example `ollama pull qwen2.5:7b-instruct`; the usual URL is `http://127.0.0.1:11434`. Outside the demo launcher, start it with `ollama serve`. For LM Studio, load a model and start its local server, usually `http://127.0.0.1:1234/v1`. llama.cpp uses the same OpenAI-compatible option with its configured port. Only loopback and `host.docker.internal` endpoints are accepted; use a loopback SSH tunnel on the WISL host if the model is on another machine. No model is installed automatically.

Connection selections are per browser session, not global server changes. Optional server tokens stay in page memory and are not saved. **Run fresh** is on by default; turn it off to reuse a cached answer for identical evidence, question and connection. Cached answers are labelled. **Stop waiting** ends the browser request, but the model server may still finish inference. `DEMO_ANALYSIS_TIMEOUT_SECONDS` controls the server wait (default 120 seconds). A model must produce valid JSON and cite only supplied evidence IDs; incompatible or truncated output is rejected without affecting the deterministic analysis.

The library auto-imports six Singapore missions (Lim Chu Kang survey, Seletar perimeter patrol, Hillview inspection) under `sdth-demo/fixtures/singapore/`, plus seven UK examples: GPS-weak warning · DJI CSV, Frozen position · Orbiter JSON, Exercise · Attitude excursion + warning, Amesbury · Telemetry sortie · ArduPilot TLOG, Amesbury · Blackbox · ArduPilot BIN, Amesbury · Perimeter · Hermes 900 STANAG, and Amesbury · Route check · aunav ROS. The other fixtures stay on disk for explicit upload.
They are imported into the Mission library when you connect a Session.
The term "jamming" in a simulator filename is not a causal diagnosis.

**Map/Satellite on another laptop:** Tabletop geometry and elevation are bundled, but raster imagery downloads through the WISL server into `data/tiles/`. That local cache is not included in Git, so a fresh checkout needs server-side internet access to the imagery providers. If downloads fail, the viewer shows an imagery warning; **Retry imagery** retries after connectivity recovers, without restarting the flight. Blank fallback tiles are not browser-cached. In browser Network tools, failed tile responses carry `X-WISL-Tile: missing` and `X-WISL-Tile-Reason`; the WISL terminal also logs the failure type. Switch to Tabletop while imagery is unavailable.

If Map and Satellite stay blank on Windows, run this from the repo root in PowerShell to test the same download path with the installed Python environment:

```powershell
.\.venv\Scripts\python.exe -c "import httpx; r=httpx.get('https://tile.openstreetmap.org/0/0/0.png', headers={'User-Agent':'WISL-replay/1.0'}, timeout=15, trust_env=False); print(r.status_code, r.headers.get('content-type')); r.raise_for_status()"
```

A certificate, proxy, DNS or firewall failure still needs to be resolved on the WISL host. Keep TLS verification enabled; Tabletop remains available without raster imagery.

### Optional audit of the exercise fixtures

The same exercise CSVs can still be loaded through the checksum-gated script:

```sh
.venv/bin/python sdth-telemetry/scripts/load_demo_failures.py
```

Duplicate content reuses the existing record.
See the [validation report](docs/submission/corpus-validation.md) for supported conclusions and simulation limitations.

### Perturbed fixtures (unhappy path)

`sdth-demo/fixtures/perturbed/` holds synthetic DJI logs shifted 2 km north with 10% of rows dropped (one also has a 20 s mid-cruise gap) for the judges' unhappy-path test; see its `manifest.json` for observed detectors. They are not auto-imported — upload via the console's Import log dropzone. To perturb a judge-supplied DJI CSV: `.venv/bin/python sdth-telemetry/scripts/generate_perturbed_fixtures.py --input <file.csv> --out /tmp/perturbed --cut-gap`.

## Demo walkthrough

The recorded demo sequence (narrated in [demo-pitch-vo.md](docs/submission/demo-pitch-vo.md)):

1. Open **Lim Chu Kang · Survey · Normal control**; the log parses cleanly and the detector engine flags zero incidents.
2. Open **Lim Chu Kang · Survey · GPS-weak**, press Play on the 3D track, switch between **Tabletop**, **Map** and **Satellite** views; the aircraft renders at true 1:1 scale (toggle to **Enlarged** from the HUD) with a scale legend in the corner.
3. Click **Replay this observation** to jump to the GPS-weak warning marker.
4. In **Mission analysis**, ask **What happened?**, then **Similar warnings** — a second stored flight threw the exact same warning.
5. Open **Recurring patterns** and click **Create review bulletin** — a human-review bulletin, never an automated vehicle command.
6. Stay on the mission and click **⬇ Comprehensive PDF**; open the downloaded comprehensive report.
7. Optionally expand **AI-assisted analysis** and click **Analyze fleet records** (requires Ollama serving `qwen2.5:7b-instruct`).
8. Close on **Exercise · Recording ends airborne** — the log ends while the aircraft is still airborne.

## Optional local model

With Ollama installed, run these in a separate terminal:

```sh
ollama pull qwen2.5:7b-instruct
ollama serve
```

The download is needed once; skip `ollama serve` if it is already running. The launcher defaults to `http://127.0.0.1:11434` and `qwen2.5:7b-instruct`. Set `OLLAMA_MODEL` (for example `OLLAMA_MODEL=deepseek-r1:7b`) or `OLLAMA_BASE_URL` before starting the demo to select another local installation. Parsing, replay, record queries and bulletins work without the model. Local inference does not make replay air-gapped: Cesium and map assets still require network access. The six bundled demo regions (three in the UK, three in Singapore: Lim Chu Kang, Hillview, Seletar) have local elevation and OpenStreetMap geometry caches, so terrain loading does not depend on an external request. Cesium is served locally once fetched (`node sdth-replay/scripts/fetch-cesium.cjs`), and map tiles are cached on first view (pre-warm the six demo regions — OSM and satellite — with `node sdth-replay/scripts/warm-tiles.cjs`); anything outside the cache still needs network. An upload outside those regions is labelled **Terrain uncached · flat globe**; no terrain is invented. See [map data and styling notes](sdth-replay/public/assets/TABLETOP-SOURCES.md).

## Runtime and evidence

The database is `data/demo-console.db`; raw uploads, reports and visuals also stay under `data/`. These runtime files are excluded from Git. `WISL_PYTHON=/absolute/path/to/python` selects another Python environment; `API_PORT=8011` selects another local port. See the [detailed runbook](docs/submission/demo-runbook.md) for the complete demonstration sequence. Every upload prints timed `stage=received → parsed → canonical → detected → done` lines in the launcher terminal (sample: `output/evidence/ingest-stage-log-sample.txt`).

## Layout

- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) — how the code fits together; [docs/architecture-uml.md](docs/architecture-uml.md) — component, sequence, data-model and state diagrams; [docs/code-check.md](docs/code-check.md) — live assessment guide and unhappy-path fixtures.

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
- Test suites: 197 platform tests, 30 parser tests, 27 replay engine tests, 5 UI tests — all passing.
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
