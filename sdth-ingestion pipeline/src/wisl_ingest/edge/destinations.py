from __future__ import annotations

import logging
import mimetypes
import uuid
from pathlib import Path
from typing import Protocol
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

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
    """Upload raw logs to the WISL multipart endpoint over Tailscale or HTTPS."""

    def __init__(self, endpoint: str, api_key: str | None = None, timeout_seconds: float = 60.0):
        if not endpoint:
            raise ValueError("HttpDestination requires a non-empty endpoint")
        self.endpoint = endpoint.rstrip("/")
        self.api_key = api_key
        self.timeout_seconds = timeout_seconds

    def upload(self, path: Path, sha256: str) -> bool:
        boundary = f"wisl-{uuid.uuid4().hex}"
        content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        prefix = (
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="file"; filename="{path.name}"\r\n'
            f"Content-Type: {content_type}\r\n\r\n"
        ).encode()
        body = prefix + path.read_bytes() + f"\r\n--{boundary}--\r\n".encode()
        headers = {
            "Content-Type": f"multipart/form-data; boundary={boundary}",
            "Content-Length": str(len(body)),
            "X-WISL-SHA256": sha256,
        }
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        request = Request(self.endpoint, data=body, headers=headers, method="POST")
        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:
                ok = 200 <= response.status < 300
                if ok:
                    logger.info("Uploaded %s (%s)", path.name, sha256[:12])
                return ok
        except HTTPError as exc:
            logger.error("Upload rejected for %s: HTTP %s", path.name, exc.code)
        except URLError as exc:
            logger.warning("Upload unavailable for %s: %s", path.name, exc.reason)
        return False
