# WISL local demo runbook

The console runs at <http://127.0.0.1:8010/demo/>. It processes uploaded files through the real parser, canonical store and rule detectors. Processing labels reflect server state. The three record queries are deterministic; fleet analysis is a separate optional local model call.

## Start

From the repository root, using Python 3.11 or later:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -e './sdth-telemetry/platform-api[dev]'
./sdth-telemetry/scripts/demo-console.sh
```

If the environment already exists, only run the last command. Use `WISL_PYTHON=/absolute/path/to/python` to select another installed environment. The launcher binds to loopback and uses a single background worker with SQLite; Redis is unnecessary for this local demo. The standard deployment's Redis queue remains available.

Open **Session key** and enter the value of `INGEST_API_KEYS`. The development default is `dev-teammate-key-change-me`; it is a public local development value, not a production credential. The console keeps the entered value for the browser session. Raw uploads and the database live under `data/` and are excluded from Git.

## Optional local model

The installed demo model is `deepseek-r1:7b` through Ollama. Start `ollama serve` in another terminal if it is not already running. If the model is absent, obtain it with `ollama pull deepseek-r1:7b`. The initial model download needs internet access; inference uses the loopback service. `OLLAMA_MODEL` and `OLLAMA_BASE_URL` select the local installation.

Use **Analyze fleet records** once records are ready. The model receives at most 100 flight summaries and 50 indexed incident observations, with visible coverage counts. It does not receive every telemetry sample. Validated output must reference supplied evidence IDs. Offline, timed-out or invalid responses preserve the evidence and record-query workflow. Allow up to 120 seconds; actual measured runtime is recorded in `output/evidence/local-model-analysis.json`.

The replay currently loads Cesium and map resources externally. Local model inference does **not** mean the entire UI is air-gapped. Fully offline replay asset packaging remains future deployment work.

## Demonstration sequence

1. Upload the included `sdth-demo/fixtures/dji_csv_gps_jamming.csv` (an unchanged copy from the intended original corpus). The filename describes the generator scenario; the supported observation is a GPS-weak warning, not proof of jamming.
2. Wait for **Record normalized**. Select the processed flight, inspect its observations and open replay. A detector observation may also expose a parser or simulator artifact; inspect its evidence before drawing a conclusion.
3. Ask **What happened?**, **Where is the evidence?**, then **Similar warnings**. An empty match result is valid until another record with the same warning is ingested.
4. Upload `output/evidence/corpus-validation/supplemental/gps-weak-recurrence/DJI/dji_csv/dji_csv_supplemental_gps_weak_recurrence.csv`. This is a separate generated mission for recurrence testing, outside the original 90-file corpus. Repeat the warning query.
5. Open **Recurring patterns**, review a stored signature and create a bulletin. These are review records, with no automatic vehicle commands or maintenance actions.
6. Run optional local analysis. Inspect cited observations and limitations.
7. Demonstrate the normal control from `output/evidence/corpus-validation/supplemental/normal-control/DJI/dji_csv/dji_csv_supplemental_normal_control.csv` and the original logger-dropout log. Label all synthetic material. Consult the validation report for expected results and false alerts.

Duplicate bytes are detected by checksum and reuse the existing upload. Use a genuinely different fixture to demonstrate a new ingestion; do not edit bytes just to simulate a fresh mission. The launcher recovers interrupted jobs on restart. Processing multiple large exports is serialized and may take time.

## Reproducible evidence

- `docs/submission/corpus-validation.md`: denominator, provenance, parser and detector outcomes, limitations, reproduction command.
- `output/evidence/demo-console-live.json`: actual upload IDs, checksums and measured end-to-end times.
- `output/evidence/api-tests.txt`: API regression suite output.
- `docs/submission/video-handoff.md`: system-only two-minute shot list and narration.
- `docs/submission/research-brief.md`: sourced use-case hypotheses and competitive context.

The PDF report and video handoff still need the team's factual mentor/advisor identity and June 21 baseline. GitHub can distribute code, but Gary's PDFs do not identify it as the final submission portal.
