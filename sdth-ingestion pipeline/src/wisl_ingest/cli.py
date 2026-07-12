from __future__ import annotations

import argparse
import logging
from pathlib import Path

from .config import PipelineConfig
from .normalisation import StagingQueueNormaliser
from .parsers import ArduPilotDataFlashParser, PX4ULogParser, VendorHexCodeParser
from .pipeline import IngestionPipeline
from .sinks import JsonlStagingStore, OrcristSink


def build_pipeline(config: PipelineConfig) -> IngestionPipeline:
    parsers = [PX4ULogParser(), ArduPilotDataFlashParser()]
    if config.vendor_hex_table_path:
        parsers.append(VendorHexCodeParser(config.vendor_hex_table_path))

    staging_store = JsonlStagingStore(config.staging_db_path)
    orcrist_sink = OrcristSink(endpoint=config.orcrist_endpoint, enabled=config.orcrist_enabled)

    normaliser = StagingQueueNormaliser(staging_store)
    return IngestionPipeline(parsers=parsers, normaliser=normaliser, sinks=[orcrist_sink])


def main() -> None:
    parser = argparse.ArgumentParser(description="WISL log ingestion pipeline")
    parser.add_argument("source_dir", type=Path, help="Directory of raw flight logs to ingest")
    parser.add_argument("--staging-db", type=Path, default=Path("data/staging/normalised_entries.jsonl"))
    parser.add_argument("--vendor-hex-table", type=Path, default=None)
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO)

    config = PipelineConfig(
        source_dir=args.source_dir,
        staging_db_path=args.staging_db,
        vendor_hex_table_path=args.vendor_hex_table,
    )
    pipeline = build_pipeline(config)
    count = pipeline.run(config.source_dir)
    logging.info("Ingested %d entries", count)


if __name__ == "__main__":
    main()
