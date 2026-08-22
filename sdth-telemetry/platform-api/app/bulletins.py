"""Operator mitigation bulletins from recurring incident signatures.

These are reviewable guidance documents, not a vehicle command or firmware
deployment channel.
"""

from __future__ import annotations

import json
from typing import Any

from app.db import db_session
from app.schemas import new_id

BULLETIN_KIND = "operator_mitigation_bulletin"


def build_mitigation_bulletin(signature: str) -> dict[str, Any]:
    with db_session() as conn:
        pattern = conn.execute(
            """
            SELECT signature, incident_type, flight_count, incident_count,
                   first_seen_at, last_seen_at, max_severity, summary
            FROM incident_patterns
            WHERE signature = ?
            """,
            (signature,),
        ).fetchone()
        rows = conn.execute(
            """
            SELECT DISTINCT flight_id, started_at, summary, brand
            FROM incidents
            WHERE signature = ? AND detector = 'rule'
            ORDER BY started_at ASC
            """,
            (signature,),
        ).fetchall()
    if not pattern or not rows:
        raise KeyError(signature)

    flights = [row["flight_id"] for row in rows]
    bulletin = {
        "kind": BULLETIN_KIND,
        "not_a_fleet_deployment": True,
        "signature": signature,
        "incident_type": pattern["incident_type"],
        "severity": pattern["max_severity"],
        "affected_flights": flights,
        "flight_count": pattern["flight_count"],
        "incident_count": pattern["incident_count"],
        "first_seen_at": pattern["first_seen_at"],
        "last_seen_at": pattern["last_seen_at"],
        "evidence_summary": pattern["summary"],
        "recommended_review": [
            "Compare the marked timestamps on the affected missions in replay.",
            "Confirm whether the same firmware, batch, or operating area is shared.",
            "Brief operators on the observed signature before the next sortie.",
        ],
        "explicitly_not_included": [
            "firmware push to airframes",
            "remote configuration changes",
            "in-flight command uplink",
        ],
        "limitations": (
            "This bulletin is generated from recorded logs and detector signatures. "
            "It is not authorization to modify vehicles."
        ),
    }
    with db_session() as conn:
        bulletin_id = new_id()
        conn.execute(
            """
            INSERT INTO mitigation_bulletins (id, signature, incident_type, flight_count, bulletin_json)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                bulletin_id,
                signature,
                pattern["incident_type"],
                pattern["flight_count"],
                json.dumps(bulletin),
            ),
        )
    return {"id": bulletin_id, **bulletin}


def list_bulletins() -> list[dict[str, Any]]:
    with db_session() as conn:
        rows = conn.execute(
            """
            SELECT id, signature, incident_type, flight_count, bulletin_json, created_at
            FROM mitigation_bulletins
            ORDER BY created_at DESC
            """
        ).fetchall()
    items = []
    for row in rows:
        item = json.loads(row["bulletin_json"])
        item["id"] = row["id"]
        item["created_at"] = row["created_at"]
        items.append(item)
    return items
