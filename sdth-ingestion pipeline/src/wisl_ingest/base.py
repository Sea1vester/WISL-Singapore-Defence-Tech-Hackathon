from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Protocol


class SourceFormat(str, Enum):
    PX4_ULOG = "px4_ulog"
    ARDUPILOT_BIN = "ardupilot_bin"
    VENDOR_HEX = "vendor_hex"


@dataclass(slots=True)
class ParsedLogEntry:
    """One record extracted from a raw flight log, prior to LLM normalisation (Pillar 1)."""

    source_format: SourceFormat
    source_file: str
    timestamp: datetime
    message_type: str
    fields: dict[str, Any] = field(default_factory=dict)
    raw: str | None = None


class LogParser(Protocol):
    """Anything that can turn a raw log file into a stream of ParsedLogEntry."""

    source_format: SourceFormat

    def can_parse(self, path: Path) -> bool: ...

    def parse(self, path: Path) -> Iterator[ParsedLogEntry]: ...
