from __future__ import annotations

from collections.abc import Iterator
from datetime import datetime, timezone
from pathlib import Path

from ..base import ParsedLogEntry, SourceFormat


class ArduPilotDataFlashParser:
    """Parses ArduPilot .bin DataFlash SD-card logs into ParsedLogEntry records.

    Requires the `pymavlink` package (pip install pymavlink).
    """

    source_format = SourceFormat.ARDUPILOT_BIN

    def can_parse(self, path: Path) -> bool:
        return path.suffix.lower() == ".bin"

    def parse(self, path: Path) -> Iterator[ParsedLogEntry]:
        from pymavlink import DFReader  # lazy import: only required when ArduPilot logs are present

        reader = DFReader.DFReader_binary(str(path))
        while True:
            msg = reader.recv_msg()
            if msg is None:
                break
            data = msg.to_dict()
            data.pop("mavpackettype", None)
            yield ParsedLogEntry(
                source_format=self.source_format,
                source_file=str(path),
                timestamp=datetime.fromtimestamp(getattr(msg, "_timestamp", 0.0), tz=timezone.utc),
                message_type=msg.get_type(),
                fields=data,
            )
