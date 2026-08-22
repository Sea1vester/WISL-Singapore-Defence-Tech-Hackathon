from datetime import datetime, timezone
from pathlib import Path

from wisl_ingest.base import ParsedLogEntry, SourceFormat
from wisl_ingest.normalisation import StagingQueueNormaliser
from wisl_ingest.pipeline import IngestionPipeline
from wisl_ingest.sinks.local_store import JsonlStagingStore


class FakeParser:
    source_format = SourceFormat.VENDOR_HEX

    def can_parse(self, path: Path) -> bool:
        return path.suffix == ".fake"

    def parse(self, path: Path):
        yield ParsedLogEntry(
            source_format=self.source_format,
            source_file=str(path),
            timestamp=datetime(2026, 7, 11, tzinfo=timezone.utc),
            message_type="TEST_EVENT",
            fields={"ok": True},
        )


def test_pipeline_parses_and_stages_entries(tmp_path: Path):
    source_dir = tmp_path / "logs"
    source_dir.mkdir()
    (source_dir / "flight1.fake").write_text("irrelevant")
    (source_dir / "ignored.txt").write_text("no parser for this")

    staging_path = tmp_path / "staging.jsonl"
    staging_store = JsonlStagingStore(staging_path)
    normaliser = StagingQueueNormaliser(staging_store)

    pipeline = IngestionPipeline(parsers=[FakeParser()], normaliser=normaliser, sinks=[])
    count = pipeline.run(source_dir)

    assert count == 1
    lines = staging_path.read_text().splitlines()
    assert len(lines) == 1
    assert "TEST_EVENT" in lines[0]
