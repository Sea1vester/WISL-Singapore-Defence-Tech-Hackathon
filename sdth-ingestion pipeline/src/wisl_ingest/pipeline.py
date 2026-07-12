from __future__ import annotations

import logging
from collections.abc import Iterator
from pathlib import Path

from .base import LogParser
from .normalisation import NormalisationClient
from .sinks.base import LogSink

logger = logging.getLogger(__name__)


class IngestionPipeline:
    """Discovers raw flight logs, parses them, and feeds the results to the normalisation
    module. Covers Week 2 of the roadmap: "Build initial parsers and the data ingestion
    pipeline to feed raw logs into the normalisation module." New formats or destinations
    only need a new parser or sink registered here.
    """

    def __init__(
        self,
        parsers: list[LogParser],
        normaliser: NormalisationClient,
        sinks: list[LogSink] | None = None,
    ):
        self._parsers = parsers
        self._normaliser = normaliser
        self._sinks = sinks or []

    def _parser_for(self, path: Path) -> LogParser | None:
        return next((p for p in self._parsers if p.can_parse(path)), None)

    def discover(self, source_dir: Path) -> Iterator[Path]:
        yield from (p for p in source_dir.rglob("*") if p.is_file())

    def run(self, source_dir: Path) -> int:
        count = 0
        for path in self.discover(source_dir):
            parser = self._parser_for(path)
            if parser is None:
                logger.debug("No parser registered for %s, skipping", path)
                continue
            logger.info("Parsing %s with %s", path, type(parser).__name__)
            entries = list(parser.parse(path))
            for sink in self._sinks:
                sink.write(entries)
            self._normaliser.submit(entries)
            count += len(entries)
        return count
