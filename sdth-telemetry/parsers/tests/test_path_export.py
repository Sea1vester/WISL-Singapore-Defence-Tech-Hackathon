from parsers.path_export import l1_payload_to_path, sample_from_l2_record


def test_l1_to_path_skips_zero_gps_and_maps_fields():
    payload = {
        "flight_id": "f1",
        "timestamp_utc": "2026-07-11T10:00:00Z",
        "source": "dji-csv",
        "records": [
            {"lat": 0, "lon": 0, "alt_m": 10},
            {
                "timestamp_utc": "2026-07-11T10:00:01Z",
                "lat": 1.35,
                "lon": 103.82,
                "alt_m": 42.5,
                "roll": 1.0,
                "pitch": -0.5,
                "yaw": 90.0,
                "battery_pct": 80,
                "warning": "low gps",
            },
        ],
    }
    path = l1_payload_to_path(payload)
    assert path["contract_version"] == "1.0"
    assert path["flight_id"] == "f1"
    assert path["count"] == 1
    sample = path["samples"][0]
    assert sample["lat"] == 1.35
    assert sample["lon"] == 103.82
    assert sample["alt_m"] == 42.5
    assert sample["roll_deg"] == 1.0
    assert sample["yaw_deg"] == 90.0
    assert sample["battery_pct"] == 80
    assert sample["warning"] == "low gps"
    assert sample["t"] == "2026-07-11T10:00:01Z"


def test_l1_stride_and_batch_timestamp_fallback():
    payload = {
        "flight_id": "f2",
        "timestamp_utc": "2026-07-11T10:00:00Z",
        "source": "demo",
        "records": [
            {"lat": 1.0, "lon": 2.0, "alt_m": 1},
            {"lat": 1.1, "lon": 2.1, "alt_m": 2},
            {"lat": 1.2, "lon": 2.2, "alt_m": 3},
        ],
    }
    path = l1_payload_to_path(payload, stride=2)
    assert path["count"] == 2
    assert path["samples"][0]["alt_m"] == 1
    assert path["samples"][1]["alt_m"] == 3
    assert path["samples"][0]["t"] == "2026-07-11T10:00:00Z"


def test_sample_from_l2_record():
    canonical = {
        "timestamp_utc": "2026-07-11T10:00:00Z",
        "position": {"lat": 1.35, "lon": 103.82, "alt_m": 40},
        "attitude": {"roll_deg": 1, "pitch_deg": 2, "yaw_deg": 3},
        "battery": {"percent": 70, "voltage_v": 15.1},
        "sensors": {"flight_mode": "AUTO"},
    }
    sample = sample_from_l2_record(canonical)
    assert sample is not None
    assert sample["lat"] == 1.35
    assert sample["alt_m"] == 40
    assert sample["yaw_deg"] == 3
    assert sample["battery_pct"] == 70
    assert sample["flight_mode"] == "AUTO"
