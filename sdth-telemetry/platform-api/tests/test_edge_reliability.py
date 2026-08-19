from tests.conftest import AUTH
from tests.hardware_l1 import HARDWARE_CASES


def test_reliability_groups_failures_by_hardware_brand(client):
    for brand_id, builder, _expected in HARDWARE_CASES:
        payload = builder(f"rel-{brand_id}")
        assert client.post("/v1/telemetry/ingest", json=payload, headers=AUTH).status_code == 202
        indexed = client.post(
            f"/v1/flights/{payload['flight_id']}/index-incidents",
            json={},
            headers=AUTH,
        )
        assert indexed.status_code == 200

    report = client.get("/v1/reliability", headers=AUTH)
    assert report.status_code == 200
    body = report.json()
    brands = {item["brand"]: item for item in body["brands"]}
    for brand_id, _builder, expected_type in HARDWARE_CASES:
        assert brand_id in brands, brands.keys()
        assert brands[brand_id]["flights_indexed"] >= 1
        assert brands[brand_id]["incident_count"] >= 1
        assert expected_type in brands[brand_id]["by_type"]
    assert body["recurring_patterns"] == [] or isinstance(body["recurring_patterns"], list)


def test_edge_benchmark_stays_within_budget(client):
    response = client.post("/v1/reliability/edge-benchmark?sample_count=400", headers=AUTH)
    assert response.status_code == 200
    body = response.json()
    assert body["sample_count"] == 400
    assert body["detected"] >= 1
    assert body["within_budget"]["detect"] is True
    assert body["within_budget"]["index"] is True
    assert body["within_budget"]["pattern_query"] is True
