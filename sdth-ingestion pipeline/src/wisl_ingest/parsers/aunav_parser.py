from __future__ import annotations

import re
from collections.abc import Iterator
from datetime import datetime, timezone
from pathlib import Path

from ..base import LogParser, ParsedLogEntry, SourceFormat
from ._util import parse_kv_pairs

# ROS console log line, e.g.:
# [ROS_INFO] [1718550000.000000] /aunav/robot_state pos_x=45.0 pos_y=12.0 pos_z=0.0 arm_ext_m=1.2
_LINE_RE = re.compile(r"^\[ROS_INFO\]\s+\[(?P<timestamp>[\d.]+)\]\s+(?P<topic>\S+)\s+(?P<kv>.*)$")


class AunavParser(LogParser):
    """Parses aunav.NEO HD ROS console logs (e.g. /aunav/robot_state)."""

    source_format = SourceFormat.AUNAV_ROS

    def can_parse(self, path: Path) -> bool:
        return path.suffix in (".ros", ".xml", ".aunav")

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
                fields["topic"] = match.group("topic")
                fields["drone_model"] = "aunav.NEO HD"
                yield ParsedLogEntry(
                    source_format=self.source_format,
                    source_file=path.name,
                    timestamp=datetime.fromtimestamp(float(match.group("timestamp")), tz=timezone.utc),
                    message_type=match.group("topic").strip("/").upper().replace("/", "_"),
                    fields=fields,
                    raw=line,
                )
