"""Separate vehicle telemetry from operator/GCS location fields."""

from __future__ import annotations

import json
from copy import deepcopy
from typing import Any

from app.schemas import new_id

OPERATOR_LOCATION_KEYS = {
    "home_lat",
    "home_lon",
    "home_lng",
    "home_latitude",
    "home_longitude",
    "home_alt_m",
    "gcs_lat",
    "gcs_lon",
    "gcs_lng",
    "operator_lat",
    "operator_lon",
    "rc_lat",
    "rc_lon",
    "launch_lat",
    "launch_lon",
    "home",
    "gcs",
    "operator_position",
}

VEHICLE_POSITION_KEYS = {"lat", "lon", "alt_m", "alt", "alt_msl", "north_m", "east_m", "up_m"}


def _redact_mapping(data: dict[str, Any], removed: list[str], prefix: str = "") -> dict[str, Any]:
    cleaned: dict[str, Any] = {}
    for key, value in data.items():
        path = f"{prefix}{key}" if not prefix else f"{prefix}.{key}"
        if key in OPERATOR_LOCATION_KEYS:
            removed.append(path)
            continue
        if isinstance(value, dict):
            nested = _redact_mapping(value, removed, path)
            if nested:
                cleaned[key] = nested
            continue
        cleaned[key] = value
    return cleaned


def redact_operator_locations(payload: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    """Return a copy of an L1 payload with operator/GCS/home coordinates removed."""
    cleaned = deepcopy(payload)
    removed: list[str] = []
    cleaned = _redact_mapping(cleaned, removed)
    records = []
    for record in cleaned.get("records") or []:
        if isinstance(record, dict):
            records.append(_redact_mapping(record, removed))
        else:
            records.append(record)
    cleaned["records"] = records
    return cleaned, sorted(set(removed))


def record_audit(conn, *, event_type: str, subject: str | None, detail: dict[str, Any]) -> None:
    conn.execute(
        """
        INSERT INTO audit_events (id, event_type, subject, detail_json)
        VALUES (?, ?, ?, ?)
        """,
        (new_id(), event_type, subject, json.dumps(detail)),
    )


def apply_retention(conn, *, retention_days: int) -> int:
    if retention_days <= 0:
        return 0
    cutoff = f"-{int(retention_days)} days"
    flights = conn.execute(
        """
        SELECT id FROM flights
        WHERE datetime(created_at) < datetime('now', ?)
        """,
        (cutoff,),
    ).fetchall()
    for row in flights:
        flight_id = row["id"]
        conn.execute("DELETE FROM incident_reports WHERE flight_id = ?", (flight_id,))
        conn.execute("DELETE FROM incidents WHERE flight_id = ?", (flight_id,))
        conn.execute("DELETE FROM incident_index_runs WHERE flight_id = ?", (flight_id,))
        conn.execute("DELETE FROM normalization_enrichments WHERE flight_id = ?", (flight_id,))
        conn.execute(
            """
            DELETE FROM translation_jobs
            WHERE ingest_id IN (SELECT id FROM ingest_events WHERE flight_id = ?)
            """,
            (flight_id,),
        )
        conn.execute("DELETE FROM canonical_records WHERE flight_id = ?", (flight_id,))
        conn.execute("DELETE FROM ingest_events WHERE flight_id = ?", (flight_id,))
        conn.execute("DELETE FROM raw_uploads WHERE flight_id = ?", (flight_id,))
        conn.execute("DELETE FROM flights WHERE id = ?", (flight_id,))
    return len(flights)
