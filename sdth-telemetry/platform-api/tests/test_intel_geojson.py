from app.intel_geojson import build_feature_collection, is_gps_degraded, public_hazard, remap_incidents_to_singapore


def _incident(**kwargs):
    base = {
        "flight_id": "flight-a",
        "incident_type": "operator_warning",
        "severity": "warning",
        "started_at": "2026-03-18T09:42:30Z",
        "ended_at": "2026-03-18T09:42:40Z",
        "lat": 51.1797,
        "lon": -1.8247,
        "evidence": {"hazard": "jamming", "position": {"lat": 51.1797, "lon": -1.8247}},
    }
    base.update(kwargs)
    return base


def test_jamming_label_is_gps_degraded_not_confirmed_cause():
    assert public_hazard("jamming") == "gps_degraded"
    assert public_hazard("mechanical_failure") == "mechanical_failure"
    assert is_gps_degraded(_incident())
    assert not is_gps_degraded(_incident(incident_type="attitude_shock", evidence={"hazard": "mechanical_failure"}))


def test_feature_collection_points_and_zone_from_two_flights():
    incidents = [
        _incident(),
        _incident(
            flight_id="flight-b",
            incident_type="last_known_position",
            lat=51.1739,
            lon=-1.8309,
            evidence={"hazard": "jamming", "position": {"lat": 51.1739, "lon": -1.8309}},
        ),
        _incident(
            flight_id="flight-c",
            incident_type="battery_low",
            lat=51.1756,
            lon=-1.8373,
            evidence={"position": {"lat": 51.1756, "lon": -1.8373}},
        ),
    ]
    collection = build_feature_collection(incidents)
    assert collection["type"] == "FeatureCollection"
    points = [f for f in collection["features"] if f["properties"]["kind"] == "pin"]
    zones = [f for f in collection["features"] if f["properties"]["kind"] == "zone"]
    assert len(points) == 3
    assert len(zones) == 1
    assert points[0]["geometry"]["coordinates"] == [-1.8247, 51.1797]
    assert points[0]["properties"]["what"] == "GPS signal degraded"
    assert points[0]["properties"]["start_time"] == "2026-03-18T09:42:30Z"
    assert points[0]["properties"]["end_time"] == "2026-03-18T09:42:40Z"
    assert "confidence" not in points[0]["properties"]
    assert "evidence" not in points[0]["properties"]
    assert "place" not in points[0]["properties"]
    assert "area" not in points[0]["properties"]
    zone = zones[0]
    assert zone["geometry"]["type"] == "Polygon"
    assert zone["properties"]["what"] == "GPS degraded area"
    assert zone["properties"]["flights_that_saw_this"] == 2
    assert "confidence" not in zone["properties"]
    ring = zone["geometry"]["coordinates"][0]
    assert ring[0] == ring[-1]


def test_lonely_gps_hit_does_not_become_a_zone():
    collection = build_feature_collection(
        [
            _incident(flight_id="flight-only", lat=53.0475, lon=-3.0032),
        ]
    )
    assert [f["properties"]["kind"] for f in collection["features"]] == ["pin"]


def test_skips_incidents_without_coordinates():
    collection = build_feature_collection(
        [_incident(lat=None, lon=None, evidence={"hazard": "jamming"})]
    )
    assert collection["features"] == []


def test_remap_puts_uk_homes_in_singapore():
    incidents = [
        _incident(),
        _incident(flight_id="flight-b", lat=51.1739, lon=-1.8309),
        _incident(flight_id="flight-c", lat=53.0475, lon=-3.0032),
    ]
    remapped = remap_incidents_to_singapore(incidents)
    assert len(remapped) == 3
    for item in remapped:
        assert 1.22 < item["lat"] < 1.47
        assert 103.60 < item["lon"] < 104.10
        assert "place" not in item
        assert "area" not in item
    # Separate original homes stay in separate Singapore clusters.
    assert abs(remapped[0]["lat"] - remapped[2]["lat"]) > 0.01
    collection = build_feature_collection(remapped)
    props = collection["features"][0]["properties"]
    assert "place" not in props
    assert "area" not in props
    assert "place" not in collection
