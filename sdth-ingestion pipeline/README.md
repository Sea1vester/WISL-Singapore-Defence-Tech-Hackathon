# WISL Ingestion Pipeline

Parses raw drone flight logs and feeds them into the normalisation module (Pillar 1: the
self-hosted, grammar-constrained LLM that translates vendor jargon into the unified JSON
schema). Covers Week 2 of the roadmap.

## Layout

- `src/wisl_ingest/parsers/` — one parser per raw format:
  - `ulog_parser.py` — PX4 `.ulg`/`.ulog` (via `pyulog`)
  - `ardupilot_parser.py` — ArduPilot `.bin` DataFlash (via `pymavlink`)
  - `hexcode_parser.py` — proprietary vendor hex-code dumps, driven by a per-vendor
    lookup table in `vendor_tables/` (add a new JSON file per vendor)
  - `hermes900_parser.py` — Elbit Hermes 900 STANAG 4586 telemetry over RFC 5424 syslog
    (`.stanag`/`.syslog`/`.hermes`)
  - `orbiter4_parser.py` — Aeronautics Orbiter 4 telemetry, JSON array or CSV
    (`orbiter*.json`/`.csv`)
  - `aunav_parser.py` — aunav.NEO HD ROS console logs (`.ros`/`.xml`/`.aunav`)
- `src/wisl_ingest/pipeline.py` — discovers files, dispatches to the matching parser,
  writes to sinks, hands entries to the normaliser
- `src/wisl_ingest/normalisation.py` — boundary to the normalisation module; currently a
  placeholder that queues into the local staging store instead of calling the cloud LLM
- `src/wisl_ingest/sinks/`
  - `local_store.py` — JSONL staging DB (Week 2's "local/cloud-staging database")
  - `telemetry_api.py` — pushes parsed entries to the `sdth-telemetry` platform API
    (`/v1/telemetry/ingest`) for LLM normalisation and storage

Ingestion is built entirely in-house — the team is no longer working with Orcrist on
this. All three target platforms (Hermes 900, Orbiter 4, Taurus UGV via aunav.NEO HD)
have real, format-aware parsers driven by sample logs in `mock_logs/`, not passthrough
stubs.

## Usage

```bash
pip install -e ".[dev]"
python -m wisl_ingest.cli path/to/raw_logs \
  --vendor-hex-table vendor_tables/example_vendor.json \
  --telemetry-endpoint http://<platform-host>:8000/v1/telemetry/ingest \
  --telemetry-api-key <key>
pytest
```

## Adding a new format or destination

- New raw format: implement `LogParser` (see `base.py`) and register it in `cli.py`.
- New destination: implement `LogSink` (see `sinks/base.py`) and add it to the `sinks`
  list in `cli.py`.
