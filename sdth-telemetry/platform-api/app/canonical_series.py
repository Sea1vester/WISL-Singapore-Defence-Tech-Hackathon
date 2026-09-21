"""Project L1 ingest records and L2 canonical blobs into a uniform L2 series.

Detectors never read vendor packet fields. They only see L2-shaped objects:
flight_id, timestamp_utc, position, attitude, battery, sensors, metadata.
"""

from __future__ import annotations

import json
import math
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

import jsonschema

from app.config import settings
from app.path_export import _num
from app.privacy import redact_operator_locations
from app.schemas import CANONICAL_JSON_SCHEMA

# Constructing a validator for every telemetry point dominates raw-log processing
# on multi-thousand-point SITL files.  The schema is immutable at runtime, so one
# compiled validator preserves validation semantics while avoiding that overhead.
_CANONICAL_VALIDATOR_CLASS = jsonschema.validators.validator_for(CANONICAL_JSON_SCHEMA)
_CANONICAL_VALIDATOR_CLASS.check_schema(CANONICAL_JSON_SCHEMA)
CANONICAL_VALIDATOR = _CANONICAL_VALIDATOR_CLASS(CANONICAL_JSON_SCHEMA)

# Same default home as PX4 SITL / local-NED projection in the parsers.
_ORIGIN_LAT = 1.3521
_ORIGIN_LON = 103.8198
_METERS_PER_DEG_LAT = 111_320.0


def _local_to_latlon(north_m: float, east_m: float) -> tuple[float, float]:
    lat = _ORIGIN_LAT + north_m / _METERS_PER_DEG_LAT
    lon = _ORIGIN_LON + east_m / (_METERS_PER_DEG_LAT * math.cos(math.radians(_ORIGIN_LAT)))
    return lat, lon


def _iso(value: Any) -> str | None:
    if value is None or value == "":
        return None
    text = str(value)
    if text.endswith("Z"):
        return text
    return text


def _parse_iso(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def l1_record_to_canonical(
    record: dict[str, Any],
    *,
    flight_id: str,
    source: str,
    batch_ts: str | None = None,
) -> dict[str, Any]:
    """Map one L1 record (parser output) into L2 canonical JSON."""
    lat = _num(record.get("lat"))
    lon = _num(record.get("lon"))
    north = _num(record.get("north_m", record.get("pos_x")))
    east = _num(record.get("east_m", record.get("pos_y")))
    frame = "wgs84"
    if (lat is None or lon is None) and north is not None and east is not None:
        lat, lon = _local_to_latlon(north, east)
        frame = "local_ned"

    alt = _num(record.get("alt_m", record.get("alt", record.get("alt_msl", record.get("pos_z", record.get("up_m"))))))
    roll = _num(record.get("roll_deg", record.get("roll")))
    pitch = _num(record.get("pitch_deg", record.get("pitch")))
    yaw = _num(record.get("yaw_deg", record.get("yaw", record.get("heading"))))
    percent = _num(record.get("battery_pct", record.get("percent")))
    voltage = _num(record.get("battery_v", record.get("voltage_v")))

    known = {
        "lat",
        "lon",
        "alt",
        "alt_m",
        "alt_msl",
        "pos_x",
        "pos_y",
        "pos_z",
        "north_m",
        "east_m",
        "up_m",
        "roll",
        "pitch",
        "yaw",
        "roll_deg",
        "pitch_deg",
        "yaw_deg",
        "heading",
        "battery_pct",
        "percent",
        "battery_v",
        "voltage_v",
        "timestamp_utc",
        "t",
        "drone_model",
        "aircraft_serial",
        "warning",
        "tip",
        "flight_mode",
        "gps_satellites",
    }
    extra = {k: v for k, v in record.items() if k not in known and v not in (None, "")}

    sensors: dict[str, Any] = {}
    if record.get("warning"):
        sensors["warning"] = record["warning"]
    if record.get("tip"):
        sensors["tip"] = record["tip"]
    if record.get("flight_mode"):
        sensors["flight_mode"] = record["flight_mode"]
    gps_sats = record.get("gps_satellites")
    if gps_sats is not None and gps_sats != "":
        sensors["gps_satellites"] = gps_sats
    if north is not None:
        sensors["north_m"] = north
    if east is not None:
        sensors["east_m"] = east
    if record.get("drone_model"):
        sensors["drone_model"] = record["drone_model"]
    if extra:
        sensors["extra"] = extra

    timestamp = _iso(record.get("timestamp_utc") or record.get("t") or batch_ts) or ""
    return {
        "flight_id": flight_id,
        "timestamp_utc": timestamp,
        "position": {
            "lat": lat if lat is not None else 0.0,
            "lon": lon if lon is not None else 0.0,
            "alt_m": alt if alt is not None else 0.0,
        },
        "attitude": {
            "roll_deg": roll if roll is not None else 0.0,
            "pitch_deg": pitch if pitch is not None else 0.0,
            "yaw_deg": yaw if yaw is not None else 0.0,
        },
        "battery": {
            "percent": percent if percent is not None else 0.0,
            "voltage_v": voltage if voltage is not None else 0.0,
        },
        "sensors": sensors,
        "metadata": {
            "source": source,
            "drone_model": record.get("drone_model"),
            "aircraft_serial": record.get("aircraft_serial"),
            "frame": frame,
        },
    }


def series_from_l1_payload(payload: dict[str, Any]) -> list[dict[str, Any]]:
    flight_id = str(payload.get("flight_id") or "")
    source = str(payload.get("source") or "unknown")
    batch_ts = payload.get("timestamp_utc")
    series: list[dict[str, Any]] = []
    for record in payload.get("records") or []:
        if not isinstance(record, dict):
            continue
        series.append(
            l1_record_to_canonical(
                record,
                flight_id=flight_id,
                source=source,
                batch_ts=batch_ts,
            )
        )
    # Telemetry streams are not always logged in order (e.g. MAVLink tlogs
    # interleave buffered messages). Sort by timestamp only when every record
    # parses; otherwise keep the recorded order rather than guessing.
    parsed = [_parse_iso(sample.get("timestamp_utc")) for sample in series]
    if series and all(ts is not None for ts in parsed):
        series = [sample for _, sample in sorted(zip(parsed, series), key=lambda pair: pair[0])]
    return series


def persist_canonical_series(
    conn,
    *,
    ingest_id: str,
    payload: dict[str, Any],
    parser: str,
    redactions: list[str] | None = None,
) -> int:
    """Persist every L1 sample as deterministic, schema-valid canonical telemetry."""
    working = payload
    applied = list(redactions or [])
    if settings.redact_operator_location and redactions is None:
        working, applied = redact_operator_locations(payload)
    series = series_from_l1_payload(working)
    conn.execute("DELETE FROM canonical_records WHERE ingest_id = ?", (ingest_id,))
    for canonical in series:
        frame = (canonical.get("metadata") or {}).get("frame")
        value_origin = {
            "telemetry_fields": "observed",
            "canonical_structure": "derived",
            "position": "derived" if frame == "local_ned" else "observed",
            "model_enrichment": "none",
            "operator_location": "redacted" if applied else "not_present",
            "redactions": applied,
        }
        canonical["metadata"] = {
            **(canonical.get("metadata") or {}),
            "schema_version": "1.0",
            "normalization": "deterministic",
            "value_origin": value_origin,
        }
        CANONICAL_VALIDATOR.validate(canonical)
        record_id = str(uuid4())
        conn.execute(
            """
            INSERT INTO canonical_records (
              id, ingest_id, flight_id, recorded_at, canonical_json,
              llm_model, llm_latency_ms, validation_ok
            ) VALUES (?, ?, ?, ?, ?, NULL, NULL, 1)
            """,
            (
                record_id,
                ingest_id,
                payload["flight_id"],
                canonical["timestamp_utc"],
                json.dumps(canonical),
            ),
        )
        conn.execute(
            """
            INSERT INTO normalization_provenance (
              canonical_record_id, parser, source_format, schema_version,
              validation_status, value_origin
            ) VALUES (?, ?, ?, '1.0', 'schema_valid', ?)
            """,
            (
                record_id,
                parser,
                payload.get("source") or "unknown",
                json.dumps(value_origin),
            ),
        )
    return len(series)


def normalize_l2(canonical: dict[str, Any], *, source: str | None = None, recorded_at: str | None = None) -> dict[str, Any]:
    """Ensure an L2 blob has the nested objects detectors expect."""
    position = canonical.get("position") if isinstance(canonical.get("position"), dict) else {}
    attitude = canonical.get("attitude") if isinstance(canonical.get("attitude"), dict) else {}
    battery = canonical.get("battery") if isinstance(canonical.get("battery"), dict) else {}
    sensors = canonical.get("sensors") if isinstance(canonical.get("sensors"), dict) else {}
    metadata = canonical.get("metadata") if isinstance(canonical.get("metadata"), dict) else {}
    if source and not metadata.get("source"):
        metadata = {**metadata, "source": source}
    timestamp = canonical.get("timestamp_utc") or recorded_at or ""
    return {
        "flight_id": canonical.get("flight_id"),
        "timestamp_utc": timestamp,
        "position": {
            "lat": _num(position.get("lat")) or 0.0,
            "lon": _num(position.get("lon")) or 0.0,
            "alt_m": _num(position.get("alt_m")) or 0.0,
        },
        "attitude": {
            "roll_deg": _num(attitude.get("roll_deg")) or 0.0,
            "pitch_deg": _num(attitude.get("pitch_deg")) or 0.0,
            "yaw_deg": _num(attitude.get("yaw_deg")) or 0.0,
        },
        "battery": {
            "percent": _num(battery.get("percent")) or 0.0,
            "voltage_v": _num(battery.get("voltage_v")) or 0.0,
        },
        "sensors": sensors,
        "metadata": metadata,
    }


def load_flight_series(conn, flight_id: str) -> tuple[list[dict[str, Any]], str]:
    """Return (L2 series, origin).

    Prefer a true L2 time series when the worker stored 2+ canonical points.
    Otherwise project stored L1 records into the same L2 shape so rules still
    see a flight, not a single LLM summary blob.
    """
    flight = conn.execute(
        "SELECT id, source FROM flights WHERE id = ?",
        (flight_id,),
    ).fetchone()
    if not flight:
        return [], "none"
    source = flight["source"]

    l2_rows = conn.execute(
        """
        SELECT recorded_at, canonical_json
        FROM canonical_records
        WHERE flight_id = ? AND validation_ok = 1
        ORDER BY recorded_at ASC
        """,
        (flight_id,),
    ).fetchall()
    l2_series = [
        normalize_l2(json.loads(row["canonical_json"]), source=source, recorded_at=row["recorded_at"])
        for row in l2_rows
    ]
    if len(l2_series) >= 2:
        return l2_series, "l2_canonical"

    events = conn.execute(
        """
        SELECT payload_json
        FROM ingest_events
        WHERE flight_id = ?
        ORDER BY rowid ASC
        """,
        (flight_id,),
    ).fetchall()
    l1_series: list[dict[str, Any]] = []
    for event in events:
        payload = json.loads(event["payload_json"])
        l1_series.extend(series_from_l1_payload(payload))
    if l1_series:
        return l1_series, "l1_projected"
    if l2_series:
        return l2_series, "l2_canonical"
    return [], "none"
