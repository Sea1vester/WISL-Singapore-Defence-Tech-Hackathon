from pathlib import Path

from parsers.dji_csv import parse_dji_csv_to_l1
from tests.conftest import AUTH
from tests.hardware_l1 import dji_l1


DEMO_LOG = Path(__file__).parents[2] / "fixtures" / "demo" / "controller_mission_alpha.csv"


def test_ingest_indexes_geolocated_incidents_immediately(client):
    payload = dji_l1("geo-demo", inject="warning")
    assert client.post("/v1/telemetry/ingest", json=payload, headers=AUTH).status_code == 202

    incidents = client.get("/v1/flights/geo-demo/incidents", headers=AUTH)
    assert incidents.status_code == 200
    items = [item for item in incidents.json()["items"] if item["incident_type"] == "operator_warning"]
    assert items
    warning = items[0]
    assert warning["started_at"]
    assert warning["lat"] == payload["records"][1]["lat"]
    assert warning["lon"] == payload["records"][1]["lon"]
    assert warning["alt_m"] == payload["records"][1]["alt_m"]
    assert warning["evidence"]["position"]["lat"] == warning["lat"]


def test_structured_report_uses_full_series_and_degrades_without_ollama(client, monkeypatch):
    payload = parse_dji_csv_to_l1(
        DEMO_LOG,
        flight_id="report-demo",
        event_id="report-demo-event",
    )
    assert client.post("/v1/telemetry/ingest", json=payload, headers=AUTH).status_code == 202

    def fail_llm(*_args, **_kwargs):
        raise RuntimeError("Ollama offline")

    monkeypatch.setattr("app.analytics._ask_llm", fail_llm)
    response = client.post("/v1/flights/report-demo/incident-report", headers=AUTH)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["kind"] == "evidence_backed_incident_summary"
    assert body["not_a_root_cause_analysis"] is True
    assert body["flight_id"] == "report-demo"
    assert body["model_enrichment"] == "degraded"
    assert "root-cause" in body["confidence_and_limitations"].lower() or "causal" in body[
        "confidence_and_limitations"
    ].lower()
    assert body["timeline"]
    first = body["timeline"][0]
    assert first["timestamp_utc"]
    assert first["lat"] is not None
    assert first["lon"] is not None
    assert "GPS signal weak" in body["report"]

    stored = client.get("/v1/flights/report-demo/incident-report", headers=AUTH)
    assert stored.status_code == 200
    assert stored.json()["mission_summary"] == body["mission_summary"]
