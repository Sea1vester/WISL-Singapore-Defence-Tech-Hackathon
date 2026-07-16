from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request
import uuid
from datetime import datetime, timezone

from ..base import ParsedLogEntry
from .base import LogSink

logger = logging.getLogger(__name__)


class TelemetryApiSink(LogSink):
    """Extension Adapter (Phase 2) pushing to the unified telemetry API."""

    def __init__(self, endpoint: str, api_key: str):
        self.endpoint = endpoint
        self.api_key = api_key

    def write(self, entries: list[ParsedLogEntry]) -> None:
        if not entries:
            return

        flight_id = str(uuid.uuid4())
        event_id = f"evt-{uuid.uuid4()}"
        timestamp_utc = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        source = "wisl-ingest-extension"

        records = []
        for e in entries:
            record = e.fields.copy()
            record["_source_format"] = e.source_format.value
            record["_message_type"] = e.message_type
            records.append(record)

        payload = {
            "flight_id": flight_id,
            "timestamp_utc": timestamp_utc,
            "source": source,
            "event_id": event_id,
            "records": records,
        }

        req = urllib.request.Request(
            self.endpoint,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json", "Authorization": f"Bearer {self.api_key}"},
            method="POST",
        )

        try:
            with urllib.request.urlopen(req) as response:
                if response.status in (200, 202):
                    logger.info("Successfully pushed %d records to %s", len(records), self.endpoint)
                else:
                    logger.error("Failed to push to %s: %s", self.endpoint, response.status)
        except urllib.error.URLError as ex:
            logger.error("Error connecting to telemetry API: %s", ex)
