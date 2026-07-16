from __future__ import annotations

from collections.abc import Iterator
from datetime import datetime, timezone
from pathlib import Path

from ..base import LogParser, ParsedLogEntry, SourceFormat


class AunavParser(LogParser):
    source_format = SourceFormat.AUNAV_ROS

    def can_parse(self, path: Path) -> bool:
        return path.suffix in (".ros", ".xml", ".aunav")

    def parse(self, path: Path) -> Iterator[ParsedLogEntry]:
        with path.open("r", encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                yield ParsedLogEntry(
                    source_format=self.source_format,
                    source_file=path.name,
                    timestamp=datetime.now(timezone.utc),
                    message_type="AUNAV_ROS_MSG",
                    fields={"ros_log": line.strip(), "drone_model": "aunav.NEO HD"},
                    raw=line.strip()
                )
