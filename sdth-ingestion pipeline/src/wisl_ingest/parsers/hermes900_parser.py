from __future__ import annotations

import re
from collections.abc import Iterator
from datetime import datetime
from pathlib import Path

from ..base import LogParser, ParsedLogEntry, SourceFormat
from ._util import parse_kv_pairs

# RFC 5424 syslog line carrying a bracketed STANAG 4586 message tag, e.g.:
# <123>1 2026-07-16T15:00:00.000Z drone-hermes900 flight-system 4586 - - [STANAG_MSG] VEHICLE_STEERING lat=1.3521 lon=103.8198 alt_msl=400.0 heading=45.0
_LINE_RE = re.compile(
    r"^<\d+>\d+\s+(?P<timestamp>\S+)\s+(?P<hostname>\S+)\s+(?P<app>\S+)\s+"
    r"(?P<procid>\S+)\s+(?P<msgid>\S+)\s+(?P<sd>\S+)\s+"
    r"\[(?P<tag>[^\]]+)\]\s+(?P<message_type>\S+)\s+(?P<kv>.*)$"
)


class Hermes900Parser(LogParser):
    """Parses Hermes 900 STANAG 4586 telemetry carried over RFC 5424 syslog."""

    source_format = SourceFormat.HERMES900_STANAG

    def can_parse(self, path: Path) -> bool:
        return path.suffix in (".stanag", ".syslog", ".hermes")

    def parse(self, path: Path) -> Iterator[ParsedLogEntry]:
        with path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                match = _LINE_RE.match(line)
                if not match:
                    continue
                fields = parse_kv_pairs(match.group("kv"))
                fields["hostname"] = match.group("hostname")
                fields["drone_model"] = "Hermes 900"
                yield ParsedLogEntry(
                    source_format=self.source_format,
                    source_file=path.name,
                    timestamp=datetime.fromisoformat(match.group("timestamp").replace("Z", "+00:00")),
                    message_type=match.group("message_type"),
                    fields=fields,
                    raw=line,
                )
