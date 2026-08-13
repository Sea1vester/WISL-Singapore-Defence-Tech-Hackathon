from __future__ import annotations

import csv
import json
from collections.abc import Iterator
from datetime import datetime, timezone
from pathlib import Path

from ..base import LogParser, ParsedLogEntry, SourceFormat

_NUMERIC_FIELDS = {"lat", "lon", "alt_m", "roll_deg", "pitch_deg", "yaw_deg", "battery_pct"}


def _coerce_numeric(record: dict) -> dict:
    for key in _NUMERIC_FIELDS & record.keys():
        try:
            record[key] = float(record[key])
        except (TypeError, ValueError):
            pass
    return record


class Orbiter4Parser(LogParser):
    """Parses Orbiter 4 telemetry exported as a JSON array or CSV, one state per row/item."""

    source_format = SourceFormat.ORBITER4_JSON

    def can_parse(self, path: Path) -> bool:
        return path.name.lower().startswith("orbiter") and path.suffix in (".json", ".csv")

    def parse(self, path: Path) -> Iterator[ParsedLogEntry]:
        if path.suffix == ".json":
            yield from self._parse_json(path)
        else:
            yield from self._parse_csv(path)

    def _parse_json(self, path: Path) -> Iterator[ParsedLogEntry]:
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, list):
            data = [data]
        for item in data:
            yield self._entry(path, item)

    def _parse_csv(self, path: Path) -> Iterator[ParsedLogEntry]:
        with path.open("r", encoding="utf-8", newline="") as f:
            for row in csv.DictReader(f):
                yield self._entry(path, _coerce_numeric(dict(row)))

    def _entry(self, path: Path, item: dict) -> ParsedLogEntry:
        item = dict(item)
        timestamp_ms = item.pop("timestamp_ms", None)
        timestamp = (
            datetime.fromtimestamp(float(timestamp_ms) / 1000, tz=timezone.utc)
            if timestamp_ms is not None
            else datetime.now(timezone.utc)
        )
        item["drone_model"] = "Orbiter 4"
        return ParsedLogEntry(
            source_format=self.source_format,
            source_file=path.name,
            timestamp=timestamp,
            message_type="ORBITER_STATE",
            fields=item,
            raw=json.dumps(item, default=str),
        )
