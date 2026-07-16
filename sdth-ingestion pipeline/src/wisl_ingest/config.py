from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass
class PipelineConfig:
    source_dir: Path
    staging_db_path: Path = Path("data/staging/normalised_entries.jsonl")
    vendor_hex_table_path: Path | None = None
    orcrist_enabled: bool = False
    orcrist_endpoint: str | None = None
    telemetry_endpoint: str | None = None
    telemetry_api_key: str | None = None
