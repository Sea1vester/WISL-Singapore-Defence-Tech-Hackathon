from __future__ import annotations

import math
from pathlib import Path

import pytest

from parsers.registry import UnsupportedLogFormat, parse_raw_log


SHA = "cd" * 32


def test_generic_csv_with_radian_attitude_and_relative_time(tmp_path: Path):
    path = tmp_path / "solo.csv"
    path.write_text(
        "id,sec,voltage,battery_remaining,pitch,yaw,roll,alt,lat,lon,mode\n"
        "1,0,16.4,94,0.01,1.5,0.02,0.8,37.5993721,126.8635995,LOITER\n"
        "2,2,16.4,93,0.22,1.6,0.02,1.1,37.599374,126.8636039,LOITER\n"
        "3,4,16.4,92,0.35,1.7,0.13,1.2,37.5993844,126.863592,LOITER\n"
        "4,6,16.4,91,-0.03,1.8,0.04,0.2,37.5993885,126.8635732,LOITER\n"
    )

    payload, parser_key = parse_raw_log(path, sha256=SHA)

    assert parser_key == "csv_generic"
    assert payload["source"] == "csv-generic"
    assert len(payload["records"]) == 4

    first = payload["records"][0]
    assert first["battery_pct"] == 94.0
    assert first["battery_v"] == 16.4
    assert first["flight_mode"] == "LOITER"
    assert first["attitude_units_inferred"] == "rad"
    assert math.isclose(first["yaw_deg"], math.degrees(1.5), abs_tol=1e-3)
    assert math.isclose(first["pitch_deg"], math.degrees(0.01), abs_tol=1e-3)
    assert first["time_origin"] == "synthetic_relative"

    timestamps = [record["timestamp_utc"] for record in payload["records"]]
    assert timestamps == sorted(timestamps)
    assert timestamps[0].startswith("2000-01-01T00:00:00")


def test_generic_csv_rejects_columns_without_lat_lon(tmp_path: Path):
    path = tmp_path / "notelemetry.csv"
    path.write_text("id,value\n1,2\n2,3\n")

    with pytest.raises(UnsupportedLogFormat):
        parse_raw_log(path, sha256=SHA)
