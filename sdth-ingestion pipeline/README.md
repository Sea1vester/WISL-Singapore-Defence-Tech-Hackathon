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
- `src/wisl_ingest/pipeline.py` — discovers files, dispatches to the matching parser,
  writes to sinks, hands entries to the normaliser
- `src/wisl_ingest/normalisation.py` — boundary to the normalisation module; currently a
  placeholder that queues into the local staging store instead of calling the cloud LLM
- `src/wisl_ingest/sinks/`
  - `local_store.py` — JSONL staging DB (Week 2's "local/cloud-staging database")
  - `orcrist.py` — **disabled reference stub** for the planned Orcrist integration; see
    the docstring in that file for why it's not wired into the live data path yet

## Usage

```bash
pip install -e ".[dev]"
python -m wisl_ingest.cli path/to/raw_logs --vendor-hex-table vendor_tables/example_vendor.json
pytest
```

## Adding a new format or destination

- New raw format: implement `LogParser` (see `base.py`) and register it in `cli.py`.
- New destination: implement `LogSink` (see `sinks/base.py`) and add it to the `sinks`
  list in `cli.py`.

## Open item: Orcrist

The team plans to work with Orcrist (https://orcrist.org) directly, but no API contract,
endpoint, or auth scheme is confirmed yet. `OrcristSink` is scaffolded and disabled by
default so nothing is sent externally until that's implemented. Note that WISL's own
design (Pillar 1) commits to keeping telemetry off third-party commercial APIs for
sovereignty/security reasons — worth confirming Orcrist's intended role against that
before enabling this sink on real flight data.
