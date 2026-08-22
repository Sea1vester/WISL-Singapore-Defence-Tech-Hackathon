from __future__ import annotations

import json
from pathlib import Path

from app.config import settings
from app.db import db_session
from app.privacy import apply_retention, redact_operator_locations
from parsers.dji_csv import parse_dji_csv_to_l1
from tests.conftest import AUTH


DEMO_LOG = Path(__file__).parents[2] / "fixtures" / "demo" / "controller_mission_alpha.csv"


def test_operator_home_coordinates_are_stripped_before_persist(client):
    payload = parse_dji_csv_to_l1(
        DEMO_LOG,
        flight_id="privacy-demo",
        event_id="privacy-demo-event",
    )
    assert any(record.get("home_lat") == 1.3499 for record in payload["records"])

    response = client.post("/v1/telemetry/ingest", json=payload, headers=AUTH)
    assert response.status_code == 202

    records = client.get("/v1/flights/privacy-demo/records", headers=AUTH).json()["items"]
    blob = json.dumps(records)
    assert "1.3499" not in blob
    assert "103.8177" not in blob
    assert records[0]["canonical_json"]["position"]["lat"] == payload["records"][0]["lat"]
    assert records[0]["canonical_json"]["metadata"]["value_origin"]["operator_location"] == "redacted"

    with db_session() as conn:
        stored = conn.execute(
            "SELECT payload_json FROM ingest_events WHERE flight_id = ?",
            ("privacy-demo",),
        ).fetchone()
        audit = conn.execute(
            "SELECT event_type, detail_json FROM audit_events WHERE subject = ?",
            ("privacy-demo",),
        ).fetchone()
    assert "home_lat" not in stored["payload_json"]
    assert audit["event_type"] == "operator_location_redacted"
    assert "home_lat" in audit["detail_json"]


def test_redaction_can_be_disabled_for_synthetic_demo(client, monkeypatch):
    monkeypatch.setattr(settings, "redact_operator_location", False)
    payload = parse_dji_csv_to_l1(
        DEMO_LOG,
        flight_id="privacy-keep",
        event_id="privacy-keep-event",
    )
    assert client.post("/v1/telemetry/ingest", json=payload, headers=AUTH).status_code == 202
    records = client.get("/v1/flights/privacy-keep/records", headers=AUTH).json()["items"]
    extras = json.dumps(records[0]["canonical_json"]["sensors"])
    assert "1.3499" in extras or "home" in extras.lower()


def test_redact_helper_keeps_vehicle_coordinates():
    cleaned, removed = redact_operator_locations(
        {
            "flight_id": "x",
            "records": [
                {"lat": 1.35, "lon": 103.82, "home_lat": 1.2, "gcs_lon": 103.1},
            ],
        }
    )
    assert cleaned["records"][0]["lat"] == 1.35
    assert "home_lat" not in cleaned["records"][0]
    assert "home_lat" in removed
    assert "gcs_lon" in removed


def test_retention_deletes_old_flights(client):
    payload = {
        "flight_id": "old-flight",
        "timestamp_utc": "2020-01-01T00:00:00Z",
        "source": "dji-csv",
        "event_id": "old-event",
        "records": [
            {
                "lat": 1.35,
                "lon": 103.82,
                "alt_m": 10,
                "timestamp_utc": "2020-01-01T00:00:00Z",
            }
        ],
    }
    assert client.post("/v1/telemetry/ingest", json=payload, headers=AUTH).status_code == 202
    with db_session() as conn:
        conn.execute("UPDATE flights SET created_at = '2020-01-01T00:00:00' WHERE id = 'old-flight'")
        deleted = apply_retention(conn, retention_days=30)
    assert deleted == 1
    listed = client.get("/v1/flights", headers=AUTH).json()
    assert all(item["id"] != "old-flight" for item in listed["items"])
