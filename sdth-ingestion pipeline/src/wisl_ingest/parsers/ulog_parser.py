from __future__ import annotations

from collections.abc import Iterator
from datetime import datetime, timedelta, timezone
from pathlib import Path

from ..base import ParsedLogEntry, SourceFormat


class PX4ULogParser:
    """Parses PX4 .ulg/.ulog SD-card flight logs into ParsedLogEntry records.

    Requires the `pyulog` package (pip install pyulog).
    """

    source_format = SourceFormat.PX4_ULOG

    def can_parse(self, path: Path) -> bool:
        return path.suffix.lower() in {".ulg", ".ulog"}

    def parse(self, path: Path) -> Iterator[ParsedLogEntry]:
        from pyulog import ULog  # lazy import: only required when PX4 logs are present

        ulog = ULog(str(path))
        epoch = datetime(1970, 1, 1, tzinfo=timezone.utc)

        for dataset in ulog.data_list:
            field_names = [f.field_name for f in dataset.field_data if f.field_name != "timestamp"]
            timestamps = dataset.data["timestamp"]
            for i, t_us in enumerate(timestamps):
                yield ParsedLogEntry(
                    source_format=self.source_format,
                    source_file=str(path),
                    timestamp=epoch + timedelta(microseconds=int(t_us)),
                    message_type=dataset.name,
                    fields={name: dataset.data[name][i] for name in field_names},
                )
