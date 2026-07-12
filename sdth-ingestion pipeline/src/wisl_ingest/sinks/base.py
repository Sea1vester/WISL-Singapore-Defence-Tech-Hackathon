from __future__ import annotations

from typing import Protocol

from ..base import ParsedLogEntry


class LogSink(Protocol):
    """Anything that persists or forwards a batch of parsed log entries."""

    def write(self, entries: list[ParsedLogEntry]) -> None: ...
