# WISL Ingestion Pipeline

Two independent things live here:

1. **`wisl_ingest.cli`** — a local parse-and-forward pipeline for PX4 ULog, ArduPilot
   DataFlash, and vendor hex-code logs, useful for offline analysis or feeding the
   platform API's older `/v1/telemetry/ingest` structured-JSON endpoint directly.
2. **`wisl_ingest.edge`** — the controller-side extension: watches a directory for
   completed raw log files and ships them, unparsed, to the `sdth-telemetry` platform's
   `/v1/logs/upload` endpoint. **This is the primary path** — the platform parses every
   raw format server-side via its own parser registry (`sdth-telemetry/parsers/`), so
   the edge side's only job is getting bytes off the controller reliably.

## Layout

- `src/wisl_ingest/parsers/` — local parsers, still useful standalone:
  - `ulog_parser.py` — PX4 `.ulg`/`.ulog` (via `pyulog`)
  - `ardupilot_parser.py` — ArduPilot `.bin` DataFlash (via `pymavlink`)
  - `hexcode_parser.py` — proprietary vendor hex-code dumps, driven by a per-vendor
    lookup table in `vendor_tables/` (add a new JSON file per vendor)

  Note: `sdth-telemetry/parsers/registry.py` now parses these same raw formats
  server-side (plus DJI CSV and Excel), so for anything going through `/v1/logs/upload`
  these local parsers aren't on the critical path. They're kept for offline use and for
  the `/v1/telemetry/ingest` route. We previously also had local parsers for Hermes 900
  STANAG, Orbiter 4, and aunav.NEO HD (Taurus UGV) here — those were removed once we
  confirmed the platform's registry already covers them (and vendor hex), to avoid two
  independently-maintained copies of the same parsing logic drifting apart.

- `src/wisl_ingest/pipeline.py` — discovers files, dispatches to the matching parser,
  writes to sinks, hands entries to the normaliser
- `src/wisl_ingest/normalisation.py` — boundary to the normalisation module; currently a
  placeholder that queues into the local staging store
- `src/wisl_ingest/sinks/`
  - `local_store.py` — JSONL staging DB
  - `telemetry_api.py` — pushes parsed entries to `/v1/telemetry/ingest`
- `src/wisl_ingest/edge/` — the controller-side uploader:
  - `uploader.py` — `LogUploader`: scans for stable (fully-written) raw log files,
    tracks upload state in a manifest so nothing is re-sent or lost across restarts
  - `destinations.py` — `NullDestination` (default; tracks files as pending, sends
    nothing) and `HttpDestination` (real multipart upload to `/v1/logs/upload`, with
    the `X-WISL-SHA256` integrity header and bearer auth the platform expects)
  - `cli.py` — `wisl-edge-upload <log_dir> [--endpoint <url>] [--watch]`

Ingestion is built entirely in-house — the team is no longer working with Orcrist on
this (see git history for that decision).

## Usage

Edge uploader (the path that actually feeds the live platform + 3D replay viewer):

```bash
pip install -e ".[dev]"
export WISL_UPLOAD_KEY=<key>
python -m wisl_ingest.edge.cli path/to/raw_logs --endpoint http://<platform-host>:8000/v1/logs/upload --watch
```

Local parse-and-forward pipeline (offline analysis / `/v1/telemetry/ingest`):

```bash
python -m wisl_ingest.cli path/to/raw_logs \
  --vendor-hex-table vendor_tables/example_vendor.json \
  --telemetry-endpoint http://<platform-host>:8000/v1/telemetry/ingest \
  --telemetry-api-key <key>
```

```bash
pytest
```

## Adding a new format or destination

- New raw format (local pipeline): implement `LogParser` (see `base.py`) and register
  it in `cli.py`. For anything reaching the platform via `/v1/logs/upload`, add it to
  `sdth-telemetry/parsers/registry.py` instead — that's the copy actually in use.
- New destination: implement `LogSink` (see `sinks/base.py`) / `UploadDestination`
  (see `edge/destinations.py`) and wire it into the relevant `cli.py`.
