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

Open **Session** and enter the value of `INGEST_API_KEYS`.
The development default is `dev-teammate-key-change-me`; it is a public local development value, not a production credential.
Connecting imports the bundled Mission library from `sdth-demo/fixtures/` into this laptop's SQLite store.
The key does not sync flights between machines.
Raw uploads and the database live under `data/` and are excluded from Git.

## Optional local model

The default demo model is `qwen2.5:7b-instruct` through Ollama. Start `ollama serve` in another terminal if it is not already running. If the model is absent, obtain it with `ollama pull qwen2.5:7b-instruct`. `deepseek-r1:7b` remains selectable via `OLLAMA_MODEL`. The initial model download needs internet access; inference uses the loopback service. `OLLAMA_MODEL` and `OLLAMA_BASE_URL` select the local installation.

In **Mission analysis**, expand **AI-assisted analysis** and use **Analyze fleet records** once records are ready. The model receives at most 100 flight summaries and 50 indexed incident observations, with visible coverage counts. It does not receive every telemetry sample. Validated output must reference supplied evidence IDs. Offline, timed-out or invalid responses preserve the evidence and record-query workflow. Allow up to 120 seconds; actual measured runtime is recorded in `output/evidence/local-model-analysis.json`.

The replay currently loads Cesium and map resources externally. Local model inference does **not** mean the entire UI is air-gapped. Fully offline replay asset packaging remains future deployment work.

## Demonstration sequence

This order follows the submitted two-minute voiceover ([`demo-pitch-vo.md`](demo-pitch-vo.md)):

1. Open the nominal control mission (**Lim Chu Kang · Survey · Normal control**). The log parses cleanly and the detector engine flags zero incidents; mouse over the empty incident feed.
2. Open **Lim Chu Kang · Survey · GPS-weak** from the library. This is a separate generated mission for recurrence testing, outside the original 90-file corpus. Press Play on the 3D track, trace altitude/battery, and switch between **Tabletop**, **Map** and **Satellite** views.
3. Click **Replay this observation** (or scrub to the warning marker) to pause at the exact recorded timestamp of the GPS-weak warning.
4. In **Mission analysis**, ask **What happened?**, then **Similar warnings**. **Where is the evidence?** is the third deterministic query. An empty match result is valid until another record with the same warning is ingested.
5. Open **Recurring patterns** and click **Create review bulletin**. These are review records, with no automatic vehicle commands or maintenance actions.
6. Stay on **Lim Chu Kang · Survey · GPS-weak** and click **⬇ Comprehensive PDF**. The console shows **Building PDF…** for roughly 15 seconds; open the downloaded `{flight-id}-comprehensive-report.pdf` to show findings and evidence pages.
7. Optionally expand **AI-assisted analysis** and click **Analyze fleet records**. Inspect cited observations and limitations.
8. Close on **Seletar · Recording ends airborne** — press Play; the log ends while the aircraft is still airborne. **Seletar · Perimeter · GPS-weak** (the recurrence partner) and **Hillview · Inspection · Telemetry dropout** are also available. Label all synthetic material. Consult the validation report for expected results and false alerts.

To demonstrate a fresh ingestion, select **Import log** (or **Logs & uploads**). Use **Try an example log with a GPS warning**, or upload `sdth-demo/fixtures/dji_csv_gps_jamming.csv` (an unchanged copy from the intended original corpus). Wait for **Ready to review**. The filename describes the generator scenario; the supported observation is a GPS-weak warning, not proof of jamming. **Flight library** switches between stored missions; **Replay this observation** pauses at the incident timestamp. A detector observation may also expose a parser or simulator artifact; inspect its evidence before drawing a conclusion.

Duplicate bytes are detected by checksum and reuse the existing upload. Use a genuinely different fixture to demonstrate a new ingestion; do not edit bytes just to simulate a fresh mission. The launcher recovers interrupted jobs on restart. Processing multiple large exports is serialized and may take time.

## Additional failure walkthroughs

Session connect already imports the audited V2 exercise CSVs and the two supplemental missions.
`.venv/bin/python sdth-telemetry/scripts/load_demo_failures.py` remains the checksum gate: it re-uploads the exercise set, checks byte hashes and verifies stored detector observations.
Duplicate content reuses the existing record.
The normal control must have no incidents.
Other vendor exports remain available under `output/evidence/corpus-validation-v2/failure-fixtures/` for individual uploads.

## Reproducible evidence

- `docs/submission/corpus-validation.md`: denominator, provenance, parser and detector outcomes, limitations, reproduction command.
- `output/evidence/demo-console-live.json`: actual upload IDs, checksums and measured end-to-end times.
- `output/evidence/api-tests.txt`: API regression suite output.
- `docs/submission/video-handoff.md`: system-only two-minute shot list and narration.
- `docs/submission/research-brief.md`: sourced use-case hypotheses and competitive context.

