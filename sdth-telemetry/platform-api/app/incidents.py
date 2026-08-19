"""Persist incidents, rebuild recurring patterns, and compute reliability."""

from __future__ import annotations

import json
import time
from typing import Any

from app.brands import identify_brand
from app.canonical_series import load_flight_series
from app.db import db_session
from app.detectors import detect_incidents
from app.schemas import new_id

_SEVERITY_RANK = {"info": 0, "warning": 1, "critical": 2}


def _max_severity(values: list[str]) -> str:
    return max(values, key=lambda item: _SEVERITY_RANK.get(item, 0), default="info")


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
        detected = detect_incidents(series)

        conn.execute(
            "DELETE FROM incidents WHERE flight_id = ? AND detector = 'rule'",
            (flight_id,),
        )
        for item in detected:
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
                    json.dumps(item.evidence),
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
    return [dict(row) for row in rows]


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
    return item
