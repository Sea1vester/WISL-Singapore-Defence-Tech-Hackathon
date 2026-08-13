from __future__ import annotations

import argparse
import logging
from pathlib import Path

from .config import PipelineConfig
from .normalisation import StagingQueueNormaliser
from .parsers import (
    ArduPilotDataFlashParser,
    AunavParser,
    Hermes900Parser,
    Orbiter4Parser,
    PX4ULogParser,
    VendorHexCodeParser,
)
from .pipeline import IngestionPipeline
from .sinks import JsonlStagingStore, TelemetryApiSink


def build_pipeline(config: PipelineConfig) -> IngestionPipeline:
    parsers = [
        PX4ULogParser(),
        ArduPilotDataFlashParser(),
        Hermes900Parser(),
        Orbiter4Parser(),
        AunavParser(),
    ]
    if config.vendor_hex_table_path:
        parsers.append(VendorHexCodeParser(config.vendor_hex_table_path))

    staging_store = JsonlStagingStore(config.staging_db_path)
    sinks = []
    if config.telemetry_endpoint and config.telemetry_api_key:
        sinks.append(TelemetryApiSink(config.telemetry_endpoint, config.telemetry_api_key))

    normaliser = StagingQueueNormaliser(staging_store)
    return IngestionPipeline(parsers=parsers, normaliser=normaliser, sinks=sinks)


def main() -> None:
    parser = argparse.ArgumentParser(description="WISL log ingestion pipeline")
    parser.add_argument("source_dir", type=Path, help="Directory of raw flight logs to ingest")
    parser.add_argument("--staging-db", type=Path, default=Path("data/staging/normalised_entries.jsonl"))
    parser.add_argument("--vendor-hex-table", type=Path, default=None)
    parser.add_argument("--telemetry-endpoint", type=str, default=None, help="URL for unified telemetry API")
    parser.add_argument("--telemetry-api-key", type=str, default=None, help="API key for telemetry API")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO)

    config = PipelineConfig(
        source_dir=args.source_dir,
        staging_db_path=args.staging_db,
        vendor_hex_table_path=args.vendor_hex_table,
        telemetry_endpoint=args.telemetry_endpoint,
        telemetry_api_key=args.telemetry_api_key,
    )
    pipeline = build_pipeline(config)
    count = pipeline.run(config.source_dir)
    logging.info("Ingested %d entries", count)


if __name__ == "__main__":
    main()
