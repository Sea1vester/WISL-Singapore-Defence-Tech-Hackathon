import json
from pathlib import Path

import pytest

from wisl_ingest.edge.destinations import HttpDestination, NullDestination
from wisl_ingest.edge.uploader import LogUploader


class RecordingDestination:
    def __init__(self):
        self.uploaded: list[tuple[str, str]] = []

    def upload(self, path: Path, sha256: str) -> bool:
        self.uploaded.append((path.name, sha256))
        return True


def test_null_destination_leaves_files_pending(tmp_path: Path):
    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    (log_dir / "flight1.ulg").write_bytes(b"ulog-bytes")

    uploader = LogUploader(log_dir, NullDestination())
    uploader.scan_once()  # first scan: file not yet stable
    counts = uploader.scan_once()

    assert counts == {"uploaded": 0, "pending": 1, "skipped_unstable": 0}
    manifest = json.loads((log_dir / ".wisl_upload_manifest.json").read_text())
    assert manifest["flight1.ulg"]["status"] == "pending"


def test_pending_files_upload_once_destination_exists(tmp_path: Path):
    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    (log_dir / "flight1.ulg").write_bytes(b"ulog-bytes")

    # First run with no destination configured
    uploader = LogUploader(log_dir, NullDestination())
    uploader.scan_once()
    uploader.scan_once()

    # Later run, same manifest, real destination: pending file gets picked up
    dest = RecordingDestination()
    uploader2 = LogUploader(log_dir, dest)
    uploader2.scan_once()
    counts = uploader2.scan_once()

    assert counts["uploaded"] == 1
    assert dest.uploaded[0][0] == "flight1.ulg"

    manifest = json.loads((log_dir / ".wisl_upload_manifest.json").read_text())
    assert manifest["flight1.ulg"]["status"] == "uploaded"


def test_uploaded_files_are_never_resent(tmp_path: Path):
    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    (log_dir / "flight1.bin").write_bytes(b"dataflash")

    dest = RecordingDestination()
    uploader = LogUploader(log_dir, dest)
    uploader.scan_once()
    uploader.scan_once()
    uploader.scan_once()
    uploader.scan_once()

    assert len(dest.uploaded) == 1


def test_growing_file_is_skipped(tmp_path: Path):
    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    f = log_dir / "inflight.ulg"
    f.write_bytes(b"a")

    dest = RecordingDestination()
    uploader = LogUploader(log_dir, dest)
    uploader.scan_once()
    f.write_bytes(b"aa")  # still growing between scans
    counts = uploader.scan_once()

    assert counts["skipped_unstable"] == 1
    assert dest.uploaded == []


def test_non_log_files_are_ignored(tmp_path: Path):
    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    (log_dir / "notes.txt").write_text("not a log")

    dest = RecordingDestination()
    uploader = LogUploader(log_dir, dest)
    uploader.scan_once()
    counts = uploader.scan_once()

    assert counts == {"uploaded": 0, "pending": 0, "skipped_unstable": 0}


def test_http_destination_requires_endpoint():
    with pytest.raises(ValueError):
        HttpDestination("")
