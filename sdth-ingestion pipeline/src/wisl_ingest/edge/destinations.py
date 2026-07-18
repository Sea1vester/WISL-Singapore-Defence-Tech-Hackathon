from __future__ import annotations

import logging
from pathlib import Path
from typing import Protocol

logger = logging.getLogger(__name__)


class UploadDestination(Protocol):
    """Anywhere a raw flight log file can be shipped to from the controller."""

    def upload(self, path: Path, sha256: str) -> bool:
        """Upload one log file. Returns True on success. Must be idempotent per sha256."""
        ...


class NullDestination:
    """Default destination while the cloud endpoint is undecided.

    Marks every file as pending instead of uploading it, so the uploader's manifest
    keeps track of what's waiting. Once a real destination is configured, the same
    files will be picked up and actually uploaded (pending files are never marked done).
    """

    def upload(self, path: Path, sha256: str) -> bool:
        logger.info("No cloud destination configured; %s (%s) left pending", path.name, sha256[:12])
        return False


class HttpDestination:
    """Cloud upload over HTTPS. Endpoint intentionally unset until the team picks one.

    Expected contract once decided: PUT/POST the file bytes with the sha256 as an
    integrity header, authenticated via a bearer token from an environment variable.
    """

    def __init__(self, endpoint: str, api_key: str | None = None):
        if not endpoint:
            raise ValueError("HttpDestination requires a non-empty endpoint; use NullDestination until one is decided")
        self.endpoint = endpoint
        self.api_key = api_key

    def upload(self, path: Path, sha256: str) -> bool:
        raise NotImplementedError(
            "Cloud destination contract not agreed yet (endpoint, auth, integrity header). "
            "Implement the request here once the team decides where logs are hosted."
        )
