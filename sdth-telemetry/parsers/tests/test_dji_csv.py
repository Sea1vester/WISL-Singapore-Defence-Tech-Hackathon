import json
from pathlib import Path

import pytest

from parsers.detect import detect_format
from parsers.dji_csv import is_dji_csv, parse_dji_csv_to_l1, row_to_record

FIXTURE = Path(__file__).parent / "fixtures" / "dji_mini_snippet.csv"


def test_is_dji_csv_markers():
    assert is_dji_csv(["OSD.latitude", "OSD.longitude", "BATTERY.chargeLevel", "other"])
    assert not is_dji_csv(["lat", "lon"])


def test_detect_dji_fixture():
    assert detect_format(FIXTURE) == "dji_csv"


def test_row_to_record_converts_units():
    row = {
        "timestamps": "1722648670",
        "OSD.latitude": "39.62655835",
        "OSD.longitude": "-105.0007326",
        "OSD.height [ft]": "100",
        "OSD.altitude [ft]": "5000",
        "OSD.pitch": "1.5",
        "OSD.roll": "-2.0",
        "OSD.yaw": "90",
        "OSD.hSpeed [MPH]": "10",
        "BATTERY.chargeLevel": "80",
        "BATTERY.voltage [V]": "15.2",
        "OSD.droneType": "Mini 4 Pro",
        "OSD.flycState": "P-GPS",
        "OSD.isOnGround": "FALSE",
        "APP.warning": "GPS signal weak",
        "HOME.latitude": "1.3499",
        "HOME.longitude": "103.8177",
    }
    record = row_to_record(row)
    assert record is not None
    assert record["lat"] == pytest.approx(39.62655835)
    assert record["alt_m"] == pytest.approx(30.48)
    assert record["speed_ms"] == pytest.approx(4.4704)
    assert record["battery_pct"] == 80
    assert record["warning"] == "GPS signal weak"
    assert record["timestamp_utc"] == "2024-08-03T01:31:10.000000Z"
    assert record["home_lat"] == pytest.approx(1.3499)
    assert record["home_lon"] == pytest.approx(103.8177)


def test_parse_fixture_skips_zero_gps():
    payload = parse_dji_csv_to_l1(FIXTURE, flight_id="test-flight", event_id="evt-1")
    assert payload["flight_id"] == "test-flight"
    assert payload["source"] == "dji-csv"
    assert len(payload["records"]) == 2
    assert payload["records"][0]["lat"] == pytest.approx(39.62655835)
    assert all(abs(r["lat"]) > 0.01 for r in payload["records"])
    json.dumps(payload)  # serializable
