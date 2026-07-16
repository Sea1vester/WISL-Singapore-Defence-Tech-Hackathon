from __future__ import annotations

import json
from collections.abc import Iterator
from datetime import datetime, timezone
from pathlib import Path

from ..base import LogParser, ParsedLogEntry, SourceFormat


class Orbiter4Parser(LogParser):
    source_format = SourceFormat.ORBITER4_JSON

    def can_parse(self, path: Path) -> bool:
        return path.name.lower().startswith("orbiter") and path.suffix in (".json", ".csv")

    def parse(self, path: Path) -> Iterator[ParsedLogEntry]:
        with path.open("r", encoding="utf-8") as f:
            if path.suffix == ".json":
                data = json.load(f)
                if not isinstance(data, list):
                    data = [data]
                for item in data:
                    yield ParsedLogEntry(
                        source_format=self.source_format,
                        source_file=path.name,
                        timestamp=datetime.now(timezone.utc),
                        message_type="ORBITER_STATE",
                        fields=item,
                        raw=json.dumps(item)
                    )
            else:
                for line in f:
                    if not line.strip():
                        continue
                    yield ParsedLogEntry(
                        source_format=self.source_format,
                        source_file=path.name,
                        timestamp=datetime.now(timezone.utc),
                        message_type="ORBITER_CSV",
                        fields={"raw_csv": line.strip(), "drone_model": "Orbiter 4"},
                        raw=line.strip()
                    )
