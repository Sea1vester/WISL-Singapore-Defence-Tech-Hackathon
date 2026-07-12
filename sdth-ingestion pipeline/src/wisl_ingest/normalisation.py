from __future__ import annotations

import logging
from typing import Protocol

from .base import ParsedLogEntry
from .sinks.base import LogSink

logger = logging.getLogger(__name__)


class NormalisationClient(Protocol):
    """Boundary to Pillar 1: the self-hosted, grammar-constrained LLM that converts
    ParsedLogEntry records into the unified vendor-agnostic JSON schema. The ingestion
    pipeline only needs to hand entries off here; the LLM/grammar-masking implementation
    lives in the normalisation module itself (separate scope from ingestion).
    """

    def submit(self, entries: list[ParsedLogEntry]) -> None: ...


class StagingQueueNormaliser:
    """Placeholder NormalisationClient that queues entries into a staging sink instead
    of calling the cloud LLM. Swap for an HTTP client against the normalisation module
    once it's stood up (Week 3).
    """

    def __init__(self, staging_sink: LogSink):
        self._staging_sink = staging_sink

    def submit(self, entries: list[ParsedLogEntry]) -> None:
        logger.info("Queuing %d entries for normalisation", len(entries))
        self._staging_sink.write(entries)
