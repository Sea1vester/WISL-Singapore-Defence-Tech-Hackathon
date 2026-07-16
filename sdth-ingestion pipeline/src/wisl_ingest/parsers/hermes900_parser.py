from __future__ import annotations

from collections.abc import Iterator
from datetime import datetime, timezone
from pathlib import Path

from ..base import LogParser, ParsedLogEntry, SourceFormat


class Hermes900Parser(LogParser):
    source_format = SourceFormat.HERMES900_STANAG

    def can_parse(self, path: Path) -> bool:
        return path.suffix in (".stanag", ".syslog", ".hermes")

    def parse(self, path: Path) -> Iterator[ParsedLogEntry]:
        with path.open("r", encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                # Mock parse STANAG 4586 / Syslog
                yield ParsedLogEntry(
                    source_format=self.source_format,
                    source_file=path.name,
                    timestamp=datetime.now(timezone.utc),
                    message_type="STANAG_MSG",
                    fields={"raw_line": line.strip(), "drone_model": "Hermes 900"},
                    raw=line.strip()
                )
