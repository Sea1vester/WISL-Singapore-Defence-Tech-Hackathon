import pytest

from tests.conftest import AUTH
from tests.hardware_l1 import HARDWARE_CASES, dji_l1


@pytest.mark.parametrize("brand_id,builder,expected_type", HARDWARE_CASES)
def test_index_detects_failure_on_each_hardware_log(client, brand_id, builder, expected_type):
    payload = builder(f"hw-{brand_id}")
    ingest = client.post("/v1/telemetry/ingest", json=payload, headers=AUTH)
    assert ingest.status_code == 202

    indexed = client.post(
        f"/v1/flights/{payload['flight_id']}/index-incidents",
        json={"include_llm": False},
        headers=AUTH,
    )
    assert indexed.status_code == 200, indexed.text
    body = indexed.json()
    assert body["brand"] == brand_id
    assert body["sample_count"] >= 2
    assert body["rule_incident_count"] >= 1

    incidents = client.get(f"/v1/flights/{payload['flight_id']}/incidents", headers=AUTH)
    assert incidents.status_code == 200
    types = {item["incident_type"] for item in incidents.json()["items"]}
    assert expected_type in types


def test_reindexing_does_not_fail_when_a_visual_is_linked_to_an_incident(client):
    """Re-running detection replaces every rule-detector incident row for a flight.
    If a visual_records row was linked to one of the old incident ids, deleting that
    row must not violate visual_records.incident_id's foreign key -- the stale link
    should be cleared, not left to block the delete."""
    import io

    flight_id = "dji-reindex-with-linked-visual"
    payload = dji_l1(flight_id, inject="warning")
    assert client.post("/v1/telemetry/ingest", json=payload, headers=AUTH).status_code == 202
    first = client.post(f"/v1/flights/{flight_id}/index-incidents", json={"include_llm": False}, headers=AUTH)
    assert first.status_code == 200, first.text

    incident_id = client.get(f"/v1/flights/{flight_id}/incidents", headers=AUTH).json()["items"][0]["id"]
    upload = client.post(
        f"/v1/flights/{flight_id}/visuals",
        params={"kind": "camera_frame", "recorded_at": payload["timestamp_utc"], "incident_id": incident_id},
        files={"file": ("frame.jpg", io.BytesIO(b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00\xff\xd9"), "image/jpeg")},
        headers=AUTH,
    )
    assert upload.status_code == 201, upload.text

    second = client.post(f"/v1/flights/{flight_id}/index-incidents", json={"include_llm": False}, headers=AUTH)
    assert second.status_code == 200, second.text


def test_recurring_pattern_across_two_dji_missions(client):
    for flight_id in ("dji-msn-1", "dji-msn-2"):
        payload = dji_l1(flight_id, inject="warning")
        assert client.post("/v1/telemetry/ingest", json=payload, headers=AUTH).status_code == 202
        indexed = client.post(
            f"/v1/flights/{flight_id}/index-incidents",
            json={},
            headers=AUTH,
        )
        assert indexed.status_code == 200

    patterns = client.get("/v1/incidents/patterns?min_flights=2", headers=AUTH)
    assert patterns.status_code == 200
    signatures = {item["signature"] for item in patterns.json()["items"]}
    assert "operator_warning" in signatures


def test_llm_report_is_persisted(client):
    payload = dji_l1("dji-llm", inject="warning")
    client.post("/v1/telemetry/ingest", json=payload, headers=AUTH)
    indexed = client.post(
        "/v1/flights/dji-llm/index-incidents",
        json={"include_llm": True, "llm_report": "GPS weak on Mini 4 Pro."},
        headers=AUTH,
    )
    assert indexed.status_code == 200
    items = client.get("/v1/flights/dji-llm/incidents", headers=AUTH).json()["items"]
    llm_rows = [item for item in items if item["detector"] == "llm"]
    assert len(llm_rows) == 1
    assert llm_rows[0]["evidence"]["report"] == "GPS weak on Mini 4 Pro."


def test_drop_debris_pin_creates_marker(client):
    payload = dji_l1("pin-flight")
    client.post("/v1/telemetry/ingest", json=payload, headers=AUTH)

    response = client.post(
        "/v1/flights/pin-flight/debris-pin",
        json={
            "flight_id": "pin-flight",
            "lat": 1.3600,
            "lon": 103.8200,
            "alt_m": 12.5,
            "timestamp_utc": "2026-07-16T16:00:00Z",
            "note": "visual confirmation of downed drone",
        },
        headers=AUTH,
    )
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "recorded"
    assert body["lat"] == 1.3600
    assert body["lon"] == 103.8200
    assert body["uxo_flag"] == "warhead state unknown, treat as potential UXO, do not approach"


def test_drop_debris_pin_rejects_unknown_flight(client):
    response = client.post(
        "/v1/flights/nonexistent/debris-pin",
        json={
            "flight_id": "nonexistent",
            "lat": 1.0,
            "lon": 2.0,
            "timestamp_utc": "2026-07-16T16:00:00Z",
        },
        headers=AUTH,
    )
    assert response.status_code == 404


def test_drop_debris_pin_unauthenticated(client):
    response = client.post(
        "/v1/flights/fake/debris-pin",
        json={
            "flight_id": "fake",
            "lat": 1.0,
            "lon": 2.0,
            "timestamp_utc": "2026-07-16T16:00:00Z",
        },
    )
    assert response.status_code == 401


def test_rule_c_full_flow_pin_then_index(client):
    """End-to-end: operator drops a debris pin, re-index flight, UXO incident appears."""
    import math
    from tests.hardware_l1 import ardupilot_l1

    payload = ardupilot_l1("uxo-flow-flight")
    client.post("/v1/telemetry/ingest", json=payload, headers=AUTH)

    pin = client.post(
        "/v1/flights/uxo-flow-flight/debris-pin",
        json={
            "flight_id": "uxo-flow-flight",
            "lat": 1.3550,
            "lon": 103.8210,
            "alt_m": 15.0,
            "timestamp_utc": "2026-07-16T15:00:03Z",
            "note": "operator-confirmed debris",
        },
        headers=AUTH,
    )
    assert pin.status_code == 200
    pin_body = pin.json()
    assert pin_body["status"] == "recorded"
    assert pin_body["uxo_flag"] == "warhead state unknown, treat as potential UXO, do not approach"
    assert pin_body["debris_pin_id"]

    indexed = client.post(
        "/v1/flights/uxo-flow-flight/index-incidents",
        json={"include_llm": False},
        headers=AUTH,
    )
    assert indexed.status_code == 200
    indexed_body = indexed.json()
    assert indexed_body["rule_incident_count"] >= 1

    incidents_resp = client.get("/v1/flights/uxo-flow-flight/incidents", headers=AUTH)
    assert incidents_resp.status_code == 200
    items = incidents_resp.json()["items"]
    uxos = [i for i in items if i["incident_type"] == "operator_marked_debris"]
    assert len(uxos) >= 1, f"Expected operator_marked_debris incident, got types: {[i['incident_type'] for i in items]}"
    # lat/lon come from nearest_position() which maps to the nearest flight-sample coords
    evidence = uxos[0].get("evidence", {})
    marker = evidence.get("marker", {})
    assert math.isclose(marker["lat"], 1.3550, abs_tol=0.0001)
    assert math.isclose(marker["lon"], 103.8210, abs_tol=0.0001)
    assert evidence.get("limitations") == "warhead state unknown, treat as potential UXO, do not approach"


def test_rule_a_full_flow_mission_incomplete(client):
    """End-to-end: flight ends airborne with no landing -> mission_incomplete incident."""
    from tests.hardware_l1 import dji_l1
    from datetime import datetime, timedelta, timezone

    ts_base = datetime(2026, 7, 16, 15, 0, 0, tzinfo=timezone.utc)
    records = []
    for i in range(10):
        records.append({
            "timestamp_utc": (ts_base + timedelta(seconds=i)).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "lat": 1.3521 + i * 0.00001,
            "lon": 103.8198,
            "alt_m": 50.0,
            "flight_mode": "P-GPS",
            "battery_pct": 80 - i,
            "drone_model": "Mini 4 Pro",
        })
    payload = {
        "flight_id": "uxo-mission-incomplete",
        "timestamp_utc": records[0]["timestamp_utc"],
        "source": "dji-csv",
        "event_id": "evt-mission-incomplete",
        "records": records,
    }
    client.post("/v1/telemetry/ingest", json=payload, headers=AUTH)

    indexed = client.post(
        "/v1/flights/uxo-mission-incomplete/index-incidents",
        json={"include_llm": False},
        headers=AUTH,
    )
    assert indexed.status_code == 200

    incidents_resp = client.get("/v1/flights/uxo-mission-incomplete/incidents", headers=AUTH)
    assert incidents_resp.status_code == 200
    items = incidents_resp.json()["items"]
    uxos = [i for i in items if i["incident_type"] == "mission_incomplete"]
    assert len(uxos) >= 1, f"Expected mission_incomplete incident, got types: {[i['incident_type'] for i in items]}"
    assert uxos[0]["severity"] == "critical"
    evidence = uxos[0].get("evidence", {})
    assert evidence.get("limitations") == "warhead state unknown, treat as potential UXO, do not approach"
    assert evidence.get("last_known_position") is not None


def test_rule_b_full_flow_frozen_position(client):
    """End-to-end: position frozen >30s while IMU indicates motion -> last_known_position incident."""
    from tests.hardware_l1 import dji_l1
    from datetime import datetime, timedelta, timezone

    ts_base = datetime(2026, 7, 16, 15, 0, 0, tzinfo=timezone.utc)
    records = []
    for i in range(40):
        records.append({
            "timestamp_utc": (ts_base + timedelta(seconds=i)).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "lat": 1.3521,
            "lon": 103.8198,
            "alt_m": 50.0,
            "flight_mode": "P-GPS",
            "roll_deg": 1.0,
            "pitch_deg": 0.5,
            "yaw_deg": 45.0 + i * 3.0,
            "battery_pct": 80,
            "drone_model": "Mini 4 Pro",
        })
    payload = {
        "flight_id": "uxo-frozen-pos",
        "timestamp_utc": records[0]["timestamp_utc"],
        "source": "dji-csv",
        "event_id": "evt-frozen-pos",
        "records": records,
    }
    client.post("/v1/telemetry/ingest", json=payload, headers=AUTH)

    indexed = client.post(
        "/v1/flights/uxo-frozen-pos/index-incidents",
        json={"include_llm": False},
        headers=AUTH,
    )
    assert indexed.status_code == 200

    incidents_resp = client.get("/v1/flights/uxo-frozen-pos/incidents", headers=AUTH)
    assert incidents_resp.status_code == 200
    items = incidents_resp.json()["items"]
    uxos = [i for i in items if i["incident_type"] == "last_known_position"]
    assert len(uxos) >= 1, f"Expected last_known_position incident, got types: {[i['incident_type'] for i in items]}"
    assert uxos[0]["severity"] == "critical"
    evidence = uxos[0].get("evidence", {})
    assert evidence.get("limitations") == "warhead state unknown, treat as potential UXO, do not approach"
    assert evidence.get("frozen_start") is not None


def test_incident_report_includes_uxo_limitations(client):
    """Incident report timeline entries for UXO incidents carry the limitation text."""
    from datetime import datetime, timedelta, timezone

    ts_base = datetime(2026, 7, 16, 15, 0, 0, tzinfo=timezone.utc)
    records = []
    for i in range(10):
        records.append({
            "timestamp_utc": (ts_base + timedelta(seconds=i)).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "lat": 1.3521 + i * 0.00001,
            "lon": 103.8198,
            "alt_m": 50.0,
            "flight_mode": "P-GPS",
            "battery_pct": 80 - i,
            "drone_model": "Mini 4 Pro",
        })
    payload = {
        "flight_id": "uxo-limit-flight",
        "timestamp_utc": records[0]["timestamp_utc"],
        "source": "dji-csv",
        "event_id": "evt-limit",
        "records": records,
    }
    client.post("/v1/telemetry/ingest", json=payload, headers=AUTH)

    indexed = client.post(
        "/v1/flights/uxo-limit-flight/index-incidents",
        json={"include_llm": False},
        headers=AUTH,
    )
    assert indexed.status_code == 200

    incidents_resp = client.get("/v1/flights/uxo-limit-flight/incidents", headers=AUTH)
    assert incidents_resp.status_code == 200
    items = incidents_resp.json()["items"]
    uxos = [i for i in items if i["incident_type"] == "mission_incomplete"]
    assert len(uxos) >= 1
    evidence = uxos[0].get("evidence", {})
    assert evidence.get("limitations") == "warhead state unknown, treat as potential UXO, do not approach"


def test_operator_marker_persists_and_reappears_after_reindex(client):
    """Drop a debris pin, re-index, the operator_marked_debris incident is still there."""
    from tests.hardware_l1 import dji_l1

    payload = dji_l1("reindex-pin")
    client.post("/v1/telemetry/ingest", json=payload, headers=AUTH)

    client.post(
        "/v1/flights/reindex-pin/debris-pin",
        json={
            "flight_id": "reindex-pin",
            "lat": 1.3650,
            "lon": 103.8250,
            "alt_m": 20.0,
            "timestamp_utc": "2026-07-16T15:00:05Z",
            "note": "reindex test",
        },
        headers=AUTH,
    )

    indexed1 = client.post(
        "/v1/flights/reindex-pin/index-incidents",
        json={},
        headers=AUTH,
    )
    assert indexed1.status_code == 200

    inc1 = client.get("/v1/flights/reindex-pin/incidents", headers=AUTH).json()["items"]
    pin_incidents_1 = [i for i in inc1 if i["incident_type"] == "operator_marked_debris"]
    assert len(pin_incidents_1) >= 1

    # Re-index — should still have the pin
    indexed2 = client.post(
        "/v1/flights/reindex-pin/index-incidents",
        json={},
        headers=AUTH,
    )
    assert indexed2.status_code == 200

    inc2 = client.get("/v1/flights/reindex-pin/incidents", headers=AUTH).json()["items"]
    pin_incidents_2 = [i for i in inc2 if i["incident_type"] == "operator_marked_debris"]
    assert len(pin_incidents_2) >= 1
