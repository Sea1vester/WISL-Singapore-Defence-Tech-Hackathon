from pathlib import Path

from parsers.dji_csv import parse_dji_csv_to_l1
from tests.conftest import AUTH


FIXTURE_DIR = Path(__file__).parents[2] / "fixtures" / "demo"


def test_two_missions_export_a_reviewable_mitigation_bulletin(client):
    for name in ("controller_mission_alpha.csv", "controller_mission_bravo.csv"):
        payload = parse_dji_csv_to_l1(
            FIXTURE_DIR / name,
            flight_id=Path(name).stem,
            event_id=f"event-{Path(name).stem}",
        )
        assert client.post("/v1/telemetry/ingest", json=payload, headers=AUTH).status_code == 202

    patterns = client.get("/v1/incidents/patterns?min_flights=2", headers=AUTH).json()
    signatures = {item["signature"] for item in patterns["items"]}
    assert "operator_warning" in signatures

    reliability = client.get("/v1/reliability", headers=AUTH).json()
    assert reliability["recurring_patterns"]

    missing = client.post(
        "/v1/mitigation-bulletins",
        json={"signature": "does-not-exist"},
        headers=AUTH,
    )
    assert missing.status_code == 404

    created = client.post(
        "/v1/mitigation-bulletins",
        json={"signature": "operator_warning"},
        headers=AUTH,
    )
    assert created.status_code == 200, created.text
    bulletin = created.json()
    assert bulletin["kind"] == "operator_mitigation_bulletin"
    assert bulletin["not_a_fleet_deployment"] is True
    assert len(bulletin["affected_flights"]) >= 2
    assert "firmware push to airframes" in bulletin["explicitly_not_included"]

    listed = client.get("/v1/mitigation-bulletins", headers=AUTH).json()
    assert listed["count"] >= 1
    assert listed["items"][0]["signature"] == "operator_warning"
