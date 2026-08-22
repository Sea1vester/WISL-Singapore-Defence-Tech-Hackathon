from pathlib import Path

import pytest

from parsers.detect import detect_format
from parsers.px4_ulg import _ned_to_lat_lon, _quat_to_euler_deg, parse_px4_ulg_to_l1

REPO_ULG = Path(__file__).resolve().parents[3] / "raw_telemetry-datasets" / "e0ad253a-a5f5-4883-ab96-56c397fe18ee.ulg"


def test_detect_ulg_extension(tmp_path: Path):
    p = tmp_path / "x.ulg"
    p.write_bytes(b"ULog")
    assert detect_format(p) == "px4_ulg"


def test_ned_projection_north_increases_lat():
    lat, lon = _ned_to_lat_lon(111_320.0, 0.0, 0.0, 0.0)
    assert lat == pytest.approx(1.0, abs=0.01)
    assert lon == pytest.approx(0.0, abs=1e-6)


def test_quat_identity_near_zero_euler():
    roll, pitch, yaw = _quat_to_euler_deg(1.0, 0.0, 0.0, 0.0)
    assert roll == pytest.approx(0.0, abs=1e-6)
    assert pitch == pytest.approx(0.0, abs=1e-6)
    assert yaw == pytest.approx(0.0, abs=1e-6)


@pytest.mark.skipif(not REPO_ULG.exists(), reason="sample .ulg not present")
def test_parse_sample_ulg():
    pytest.importorskip("pyulog")
    payload = parse_px4_ulg_to_l1(REPO_ULG, flight_id="ulg-test", max_records=10)
    assert payload["source"] == "px4-ulg"
    assert payload["flight_id"] == "ulg-test"
    assert 1 <= len(payload["records"]) <= 10
    first = payload["records"][0]
    assert "lat" in first and "lon" in first and "alt_m" in first
    assert "north_m" in first  # these sample logs are local-NED
    assert "timestamp_utc" in first
