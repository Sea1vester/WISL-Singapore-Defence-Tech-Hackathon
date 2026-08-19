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
