"""Persist incidents, rebuild recurring patterns, and compute reliability."""

from __future__ import annotations

import json
import time
from typing import Any

from app.brands import identify_brand
from app.canonical_series import load_flight_series
from app.db import db_session
from app.detectors import detect_incidents, hazard_label, parse_timestamp
from app.schemas import new_id

_SEVERITY_RANK = {"info": 0, "warning": 1, "critical": 2}

UXO_INCIDENT_TYPES = {"mission_incomplete", "last_known_position", "operator_marked_debris"}


def upsert_operator_marker(marker: dict[str, Any]) -> str:
    """Persist an operator-marked debris pin and return its id."""
    marker_id = new_id()
    with db_session() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS operator_markers (
              id              TEXT PRIMARY KEY,
              flight_id       TEXT NOT NULL,
              lat             REAL NOT NULL,
              lon             REAL NOT NULL,
              alt_m           REAL NOT NULL DEFAULT 0,
              timestamp_utc   TEXT NOT NULL,
              note            TEXT,
              created_at      TEXT DEFAULT (datetime('now'))
            )
            """
        )
        conn.execute(
            """
            INSERT INTO operator_markers (id, flight_id, lat, lon, alt_m, timestamp_utc, note)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                marker_id,
                marker["flight_id"],
                marker["lat"],
                marker["lon"],
                marker.get("alt_m", 0),
                marker["timestamp_utc"],
                marker.get("note"),
            ),
        )
    return marker_id


def _get_operator_markers(flight_id: str) -> list[dict[str, Any]]:
    """Fetch operator markers for a flight, if the table exists."""
    with db_session() as conn:
        exists = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='operator_markers'"
        ).fetchone()
        if not exists:
            return []
        rows = conn.execute(
            "SELECT id, flight_id, lat, lon, alt_m, timestamp_utc, note FROM operator_markers WHERE flight_id = ?",
            (flight_id,),
        ).fetchall()
        return [dict(row) for row in rows]


def _max_severity(values: list[str]) -> str:
    return max(values, key=lambda item: _SEVERITY_RANK.get(item, 0), default="info")


def nearest_position(series: list[dict[str, Any]], timestamp: str | None) -> dict[str, Any] | None:
    """Return the path sample closest to an incident timestamp."""
    if not series:
        return None
    target = parse_timestamp(timestamp)
    best: dict[str, Any] | None = None
    best_delta: float | None = None
    for sample in series:
        position = sample.get("position") or {}
        if position.get("lat") is None and position.get("lon") is None:
            continue
        sample_ts = parse_timestamp(sample.get("timestamp_utc"))
        if target and sample_ts:
            delta = abs((sample_ts - target).total_seconds())
        else:
            delta = float("inf")
        if best is None or delta < (best_delta if best_delta is not None else float("inf")):
            best = {
                "lat": position.get("lat"),
                "lon": position.get("lon"),
                "alt_m": position.get("alt_m"),
                "timestamp_utc": sample.get("timestamp_utc"),
            }
            best_delta = 0.0 if delta == float("inf") else delta
    return best


def rebuild_patterns(conn) -> int:
    conn.execute("DELETE FROM incident_patterns")
    rows = conn.execute(
        """
        SELECT
          signature,
          incident_type,
          COUNT(DISTINCT flight_id) AS flight_count,
          COUNT(*) AS incident_count,
          MIN(started_at) AS first_seen_at,
          MAX(COALESCE(ended_at, started_at)) AS last_seen_at,
          GROUP_CONCAT(severity) AS severities
        FROM incidents
        WHERE detector = 'rule'
        GROUP BY signature, incident_type
        """
    ).fetchall()
    now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    for row in rows:
        severities = [part for part in (row["severities"] or "").split(",") if part]
        conn.execute(
            """
            INSERT INTO incident_patterns (
              id, signature, incident_type, flight_count, incident_count,
              first_seen_at, last_seen_at, max_severity, summary, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                new_id(),
                row["signature"],
                row["incident_type"],
                row["flight_count"],
                row["incident_count"],
                row["first_seen_at"],
                row["last_seen_at"],
                _max_severity(severities),
                f"{row['incident_type']} seen on {row['flight_count']} missions",
                now,
            ),
        )
    return len(rows)


def index_flight(flight_id: str, *, include_llm_report: str | None = None) -> dict[str, Any]:
    """Detect rule incidents for a flight, optionally store an LLM report, rebuild patterns."""
    started = time.perf_counter()
    with db_session() as conn:
        flight = conn.execute(
            "SELECT id, source FROM flights WHERE id = ?",
            (flight_id,),
        ).fetchone()
        if not flight:
            raise KeyError(flight_id)

        series, origin = load_flight_series(conn, flight_id)
        brand = identify_brand(series[0] if series else {}, source=flight["source"])
        user_markers = _get_operator_markers(flight_id)
        detected = detect_incidents(series, user_markers=user_markers)

        # visual_records.incident_id has no ON DELETE clause, so re-running detection
        # (which replaces every rule incident row for this flight) would otherwise fail
        # a foreign-key check for any visual already linked to one of the old rows.
        # Those links point at rows about to disappear, so clear them first.
        conn.execute(
            """
            UPDATE visual_records SET incident_id = NULL
            WHERE incident_id IN (SELECT id FROM incidents WHERE flight_id = ? AND detector = 'rule')
            """,
            (flight_id,),
        )
        conn.execute(
            "DELETE FROM incidents WHERE flight_id = ? AND detector = 'rule'",
            (flight_id,),
        )
        for item in detected:
            evidence = dict(item.evidence)
            position = nearest_position(series, item.started_at)
            if position:
                evidence.setdefault("position", position)
            label = hazard_label(item, series, detected)
            if label:
                evidence["hazard"] = label
            conn.execute(
                """
                INSERT INTO incidents (
                  id, flight_id, source, brand, incident_type, severity, detector,
                  started_at, ended_at, signature, summary, evidence_json
                ) VALUES (?, ?, ?, ?, ?, ?, 'rule', ?, ?, ?, ?, ?)
                """,
                (
                    new_id(),
                    flight_id,
                    flight["source"],
                    brand.id,
                    item.incident_type,
                    item.severity,
                    item.started_at,
                    item.ended_at,
                    item.signature,
                    item.summary,
                    json.dumps(evidence),
                ),
            )

        if include_llm_report:
            conn.execute(
                "DELETE FROM incidents WHERE flight_id = ? AND detector = 'llm'",
                (flight_id,),
            )
            first_ts = series[0]["timestamp_utc"] if series else ""
            last_ts = series[-1]["timestamp_utc"] if series else first_ts
            conn.execute(
                """
                INSERT INTO incidents (
                  id, flight_id, source, brand, incident_type, severity, detector,
                  started_at, ended_at, signature, summary, evidence_json
                ) VALUES (?, ?, ?, ?, 'llm_report', 'info', 'llm', ?, ?, 'llm_report', ?, ?)
                """,
                (
                    new_id(),
                    flight_id,
                    flight["source"],
                    brand.id,
                    first_ts,
                    last_ts,
                    include_llm_report[:500],
                    json.dumps({"report": include_llm_report}),
                ),
            )

        pattern_count = rebuild_patterns(conn)
        duration_ms = int((time.perf_counter() - started) * 1000)
        incident_count = len(detected) + (1 if include_llm_report else 0)
        conn.execute(
            """
            INSERT INTO incident_index_runs (
              id, flight_id, status, sample_count, incident_count, duration_ms
            ) VALUES (?, ?, 'done', ?, ?, ?)
            """,
            (new_id(), flight_id, len(series), incident_count, duration_ms),
        )

    return {
        "flight_id": flight_id,
        "brand": brand.id,
        "brand_name": brand.name,
        "sample_count": len(series),
        "sample_origin": origin,
        "incident_count": incident_count,
        "rule_incident_count": len(detected),
        "duration_ms": duration_ms,
        "pattern_count": pattern_count,
    }


def _flight_identity(conn, flight_id: str) -> dict[str, Any]:
    """Best-effort identifying info for one flight: source log filename (if it
    came from a raw file upload) and aircraft model/serial (if the parser
    captured one -- currently only DJI FlightRecord CSV/Excel carry a real
    serial; other brands fall back to model/brand only)."""
    upload = conn.execute(
        "SELECT original_name FROM raw_uploads WHERE flight_id = ? ORDER BY received_at ASC LIMIT 1",
        (flight_id,),
    ).fetchone()
    record = conn.execute(
        "SELECT canonical_json FROM canonical_records WHERE flight_id = ? ORDER BY recorded_at ASC LIMIT 1",
        (flight_id,),
    ).fetchone()
    metadata: dict[str, Any] = {}
    if record:
        metadata = (json.loads(record["canonical_json"]) or {}).get("metadata") or {}
    return {
        "flight_id": flight_id,
        "source_file": upload["original_name"] if upload else None,
        "drone_model": metadata.get("drone_model"),
        "aircraft_serial": metadata.get("aircraft_serial"),
    }


def affected_flight_details(signature: str) -> list[dict[str, Any]]:
    """Per-flight identity for every flight carrying a given incident signature --
    the exact logs and aircraft behind a recurring pattern or bulletin, not just
    a count."""
    with db_session() as conn:
        rows = conn.execute(
            """
            SELECT flight_id, brand, MIN(started_at) AS first_started_at
            FROM incidents
            WHERE signature = ? AND detector = 'rule'
            GROUP BY flight_id
            ORDER BY first_started_at ASC
            """,
            (signature,),
        ).fetchall()
        details = []
        for row in rows:
            identity = _flight_identity(conn, row["flight_id"])
            identity["brand"] = row["brand"]
            identity["first_incident_at"] = row["first_started_at"]
            details.append(identity)
    return details


def list_flight_incidents(flight_id: str) -> list[dict[str, Any]]:
    with db_session() as conn:
        rows = conn.execute(
            """
            SELECT id, flight_id, source, brand, incident_type, severity, detector,
                   started_at, ended_at, signature, summary, evidence_json, created_at
            FROM incidents
            WHERE flight_id = ?
            ORDER BY started_at ASC
            """,
            (flight_id,),
        ).fetchall()
    return [_incident_row(row) for row in rows]


def list_patterns(*, min_flights: int = 2) -> list[dict[str, Any]]:
    with db_session() as conn:
        rows = conn.execute(
            """
            SELECT id, signature, incident_type, flight_count, incident_count,
                   first_seen_at, last_seen_at, max_severity, summary, updated_at
            FROM incident_patterns
            WHERE flight_count >= ?
            ORDER BY flight_count DESC, incident_count DESC
            """,
            (min_flights,),
        ).fetchall()
    patterns = [dict(row) for row in rows]
    for pattern in patterns:
        pattern["affected_flights"] = affected_flight_details(pattern["signature"])
    return patterns


def reliability_report() -> dict[str, Any]:
    with db_session() as conn:
        run_rows = conn.execute(
            """
            SELECT DISTINCT r.flight_id, f.source
            FROM incident_index_runs r
            JOIN flights f ON f.id = r.flight_id
            WHERE r.status = 'done'
            """
        ).fetchall()
        brand_rows = conn.execute(
            """
            SELECT
              brand,
              COUNT(DISTINCT flight_id) AS flights_with_incidents,
              COUNT(*) AS incident_count
            FROM incidents
            WHERE detector = 'rule'
            GROUP BY brand
            """
        ).fetchall()
        type_rows = conn.execute(
            """
            SELECT brand, incident_type,
                   COUNT(DISTINCT flight_id) AS flights,
                   COUNT(*) AS incident_count
            FROM incidents
            WHERE detector = 'rule'
            GROUP BY brand, incident_type
            """
        ).fetchall()
        patterns = conn.execute(
            """
            SELECT signature, incident_type, flight_count, incident_count, max_severity, summary
            FROM incident_patterns
            WHERE flight_count >= 2
            ORDER BY flight_count DESC
            """
        ).fetchall()

    indexed_by_brand: dict[str, int] = {}
    for row in run_rows:
        brand_id = identify_brand({}, source=row["source"]).id
        indexed_by_brand[brand_id] = indexed_by_brand.get(brand_id, 0) + 1

    by_type: dict[str, dict[str, dict[str, int]]] = {}
    for row in type_rows:
        by_type.setdefault(row["brand"], {})[row["incident_type"]] = {
            "flights": row["flights"],
            "count": row["incident_count"],
        }

    incidents_by_brand = {row["brand"]: dict(row) for row in brand_rows}
    brands: list[dict[str, Any]] = []
    for brand_id in sorted(set(indexed_by_brand) | set(incidents_by_brand)):
        flights_indexed = indexed_by_brand.get(brand_id, 0)
        with_incidents = incidents_by_brand.get(brand_id, {}).get("flights_with_incidents", 0)
        incident_count = incidents_by_brand.get(brand_id, {}).get("incident_count", 0)
        brands.append(
            {
                "brand": brand_id,
                "flights_indexed": flights_indexed,
                "flights_with_incidents": with_incidents,
                "incident_count": incident_count,
                "incident_rate": (with_incidents / flights_indexed) if flights_indexed else 0.0,
                "by_type": by_type.get(brand_id, {}),
            }
        )

    return {
        "brands": brands,
        "recurring_patterns": [dict(row) for row in patterns],
    }


def _incident_row(row) -> dict[str, Any]:
    item = dict(row)
    item["evidence"] = json.loads(item.pop("evidence_json") or "{}")
    position = item["evidence"].get("position") or {}
    item["lat"] = position.get("lat")
    item["lon"] = position.get("lon")
    item["alt_m"] = position.get("alt_m")
    return item
