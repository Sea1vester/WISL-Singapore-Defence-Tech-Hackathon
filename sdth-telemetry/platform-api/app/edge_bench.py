"""Cheap SQLite + detector timings, used to validate edge-class hardware."""

from __future__ import annotations

import json
import time
from datetime import datetime, timedelta, timezone
from typing import Any

from app.canonical_series import l1_record_to_canonical
from app.db import db_session
from app.detectors import detect_incidents
from app.incidents import index_flight, rebuild_patterns
from app.schemas import new_id

# Conservative laptop/SBC budgets. A DJI/PX4/ArduPilot flight log lands as a bursty
# batch ingest, not a 100 kHz stream. Missing these means the index is too heavy for
# the edge box a cheap-fleet operator is actually running.
MAX_DETECT_MS_PER_2K = 750
MAX_INDEX_MS = 1500
MAX_PATTERN_QUERY_MS = 200


def _synthetic_l1_records(count: int) -> list[dict[str, Any]]:
    start = datetime(2026, 7, 11, 10, 0, 0, tzinfo=timezone.utc)
    records: list[dict[str, Any]] = []
    for i in range(count):
        battery = 90.0 - (i * 0.01)
        alt = 100.0
        if i == count // 2:
            battery = 8.0
            alt = 180.0
        records.append(
            {
                "timestamp_utc": (start + timedelta(seconds=i)).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "lat": 1.3521 + i * 0.00001,
                "lon": 103.8198,
                "alt_m": alt,
                "roll": 1.0,
                "pitch": -0.5,
                "yaw": 10.0,
                "battery_pct": battery,
                "battery_v": 15.0,
                "drone_model": "px4",
            }
        )
    return records


def run_edge_benchmark(sample_count: int = 2000) -> dict[str, Any]:
    records = _synthetic_l1_records(sample_count)
    series = [
        l1_record_to_canonical(record, flight_id="bench", source="px4-ulg", batch_ts=record["timestamp_utc"])
        for record in records
    ]
    detect_started = time.perf_counter()
    detected = detect_incidents(series)
    detect_ms = (time.perf_counter() - detect_started) * 1000

    flight_id = f"bench-{new_id()}"
    payload = {
        "flight_id": flight_id,
        "timestamp_utc": records[0]["timestamp_utc"],
        "source": "px4-ulg",
        "records": records,
    }
    with db_session() as conn:
        conn.execute(
            "INSERT INTO flights (id, source, started_at) VALUES (?, ?, ?)",
            (flight_id, "px4-ulg", records[0]["timestamp_utc"]),
        )
        conn.execute(
            """
            INSERT INTO ingest_events (id, flight_id, payload_json, idempotency_key)
            VALUES (?, ?, ?, ?)
            """,
            (new_id(), flight_id, json.dumps(payload), f"bench-{flight_id}"),
        )

    index_started = time.perf_counter()
    indexed = index_flight(flight_id)
    index_ms = (time.perf_counter() - index_started) * 1000

    query_started = time.perf_counter()
    with db_session() as conn:
        rebuild_patterns(conn)
        conn.execute("SELECT * FROM incident_patterns WHERE flight_count >= 1").fetchall()
        conn.execute(
            "SELECT brand, incident_type, COUNT(*) FROM incidents GROUP BY brand, incident_type"
        ).fetchall()
    query_ms = (time.perf_counter() - query_started) * 1000

    scale = max(1.0, sample_count / 2000)
    return {
        "sample_count": sample_count,
        "detected": len(detected),
        "detect_ms": round(detect_ms, 2),
        "index_ms": round(index_ms, 2),
        "pattern_query_ms": round(query_ms, 2),
        "index_result": indexed,
        "budgets_ms": {
            "detect_2k": MAX_DETECT_MS_PER_2K,
            "index": MAX_INDEX_MS,
            "pattern_query": MAX_PATTERN_QUERY_MS,
        },
        "within_budget": {
            "detect": detect_ms <= MAX_DETECT_MS_PER_2K * scale,
            "index": index_ms <= MAX_INDEX_MS * scale,
            "pattern_query": query_ms <= MAX_PATTERN_QUERY_MS,
        },
    }
