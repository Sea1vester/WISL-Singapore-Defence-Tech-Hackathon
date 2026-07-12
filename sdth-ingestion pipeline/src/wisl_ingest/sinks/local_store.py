from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

from ..base import ParsedLogEntry


class JsonlStagingStore:
    """Local/cloud-staging database stand-in: appends parsed entries as JSON Lines.

    Matches Week 2 of the roadmap ("Implement a local/cloud-staging database to store
    telemetry for testing"). Swap for a real DB once the cloud platform (Week 3) is up.
    """

    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def write(self, entries: list[ParsedLogEntry]) -> None:
        with self.path.open("a", encoding="utf-8") as f:
            for entry in entries:
                record = asdict(entry)
                record["timestamp"] = entry.timestamp.isoformat()
                record["source_format"] = entry.source_format.value
                f.write(json.dumps(record, default=str) + "\n")
