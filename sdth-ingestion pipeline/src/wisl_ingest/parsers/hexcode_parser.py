from __future__ import annotations

import json
from collections.abc import Iterator
from datetime import datetime
from pathlib import Path

from ..base import ParsedLogEntry, SourceFormat


class VendorHexCodeParser:
    """Parses proprietary vendor hex-code error dumps via a per-vendor lookup table.

    Vendor hex formats aren't standardized (that's the fragmentation problem WISL exists
    to solve), so this parser is driven by a JSON table of {hex_code: {message_type}}
    instead of hardcoded per-vendor logic. Add a new table under vendor_tables/ per vendor.
    Expected input format: one `<ISO8601 timestamp>,<hex code>` per line.
    """

    source_format = SourceFormat.VENDOR_HEX

    def __init__(self, lookup_table_path: Path):
        self.lookup_table_path = lookup_table_path
        self._table: dict[str, dict] = json.loads(lookup_table_path.read_text())

    def can_parse(self, path: Path) -> bool:
        return path.suffix.lower() == ".hex"

    def parse(self, path: Path) -> Iterator[ParsedLogEntry]:
        for line in path.read_text().splitlines():
            line = line.strip()
            if not line:
                continue
            ts_str, _, code = line.partition(",")
            code = code.strip()
            entry_def = self._table.get(code, {})
            yield ParsedLogEntry(
                source_format=self.source_format,
                source_file=str(path),
                timestamp=datetime.fromisoformat(ts_str),
                message_type=entry_def.get("message_type", "UNKNOWN_HEX_CODE"),
                fields={"hex_code": code},
                raw=line,
            )
