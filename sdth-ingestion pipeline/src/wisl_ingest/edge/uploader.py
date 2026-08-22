from __future__ import annotations

import hashlib
import json
import logging
import time
from dataclasses import asdict, dataclass
from pathlib import Path

from .destinations import UploadDestination

logger = logging.getLogger(__name__)

# Raw log formats the controller produces; matches the parsers in wisl_ingest.parsers.
LOG_EXTENSIONS = {
    ".bin",
    ".csv",
    ".hex",
    ".hermes",
    ".json",
    ".ros",
    ".stanag",
    ".syslog",
    ".tlog",
    ".ulg",
    ".ulog",
    ".xlsx",
    ".xml",
}


@dataclass(slots=True)
class ManifestEntry:
    sha256: str
    size: int
    status: str  # "pending" | "uploaded"
    uploaded_at: float | None = None


class LogUploader:
    """Controller-side extension: watches the flight-log directory and ships completed
    logs to a cloud destination.

    A manifest file (JSON, kept next to nothing sensitive — just hashes and statuses)
    records which files have been uploaded, so re-runs and reboots never re-send data.
    A file is only considered "complete" when its size has stopped changing between
    scans, so logs still being written by the flight controller are left alone.
    """

    def __init__(
        self,
        log_dir: Path,
        destination: UploadDestination,
        manifest_path: Path | None = None,
    ):
        self.log_dir = log_dir
        self.destination = destination
        self.manifest_path = manifest_path or log_dir / ".wisl_upload_manifest.json"
        self._manifest: dict[str, ManifestEntry] = self._load_manifest()
        self._sizes_last_scan: dict[str, int] = {}

    def _load_manifest(self) -> dict[str, ManifestEntry]:
        if not self.manifest_path.exists():
            return {}
        raw = json.loads(self.manifest_path.read_text())
        return {k: ManifestEntry(**v) for k, v in raw.items()}

    def _save_manifest(self) -> None:
        serializable = {k: asdict(v) for k, v in self._manifest.items()}
        self.manifest_path.write_text(json.dumps(serializable, indent=2))

    @staticmethod
    def _sha256(path: Path) -> str:
        h = hashlib.sha256()
        with path.open("rb") as f:
            while chunk := f.read(1 << 20):
                h.update(chunk)
        return h.hexdigest()

    def _discover(self) -> list[Path]:
        manifest = self.manifest_path.resolve()
        return sorted(
            p for p in self.log_dir.rglob("*")
            if p.is_file()
            and p.resolve() != manifest
            and p.suffix.lower() in LOG_EXTENSIONS
        )

    def _is_stable(self, path: Path) -> bool:
        """A log still being written by the flight controller grows between scans."""
        key = str(path)
        current = path.stat().st_size
        previous = self._sizes_last_scan.get(key)
        self._sizes_last_scan[key] = current
        return previous == current

    def scan_once(self) -> dict[str, int]:
        """One pass: find stable, not-yet-uploaded logs and offer them to the destination.

        Returns counts: {"uploaded": n, "pending": n, "skipped_unstable": n}.
        """
        counts = {"uploaded": 0, "pending": 0, "skipped_unstable": 0}
        for path in self._discover():
            key = str(path.relative_to(self.log_dir))
            entry = self._manifest.get(key)
            if entry and entry.status == "uploaded":
                continue
            if not self._is_stable(path):
                counts["skipped_unstable"] += 1
                continue

            sha256 = self._sha256(path)
            ok = self.destination.upload(path, sha256)
            self._manifest[key] = ManifestEntry(
                sha256=sha256,
                size=path.stat().st_size,
                status="uploaded" if ok else "pending",
                uploaded_at=time.time() if ok else None,
            )
            counts["uploaded" if ok else "pending"] += 1
        self._save_manifest()
        return counts

    def watch(self, interval_seconds: float = 30.0) -> None:
        """Run forever, scanning on an interval. Intended as the long-lived service on
        the controller (e.g. under systemd or a scheduled task)."""
        logger.info("Watching %s every %.0fs", self.log_dir, interval_seconds)
        while True:
            counts = self.scan_once()
            if counts["uploaded"] or counts["pending"]:
                logger.info("Scan result: %s", counts)
            time.sleep(interval_seconds)
