from pathlib import Path

import pytest

from parsers.detect import detect_format

REPO = Path(__file__).resolve().parents[3] / "raw_telemetry-datasets"
CRASH_BIN = REPO / "sample_crash_log.bin"
LOG171 = REPO / "dronekit-la-testdata-master" / "log171.bin"
TLOG = REPO / "dronekit-la-testdata-master" / "flight.tlog"


def test_detect_bin_tlog(tmp_path: Path):
    b = tmp_path / "x.bin"
    t = tmp_path / "x.tlog"
    b.write_bytes(b"\x00")
    t.write_bytes(b"\x00")
    assert detect_format(b) == "ardupilot_bin"
    assert detect_format(t) == "ardupilot_tlog"


@pytest.mark.skipif(not CRASH_BIN.exists(), reason="sample_crash_log.bin missing")
def test_parse_crash_bin():
    pytest.importorskip("pymavlink")
    from parsers.ardupilot import parse_ardupilot_bin_to_l1

    payload = parse_ardupilot_bin_to_l1(CRASH_BIN, flight_id="bin-test", max_records=20)
    assert payload["source"] == "ardupilot-bin"
    assert 1 <= len(payload["records"]) <= 20
    first = payload["records"][0]
    assert first["lat"] == pytest.approx(35.7708816, abs=1e-4)
    assert "alt_m" in first
    assert "roll" in first


@pytest.mark.skipif(not LOG171.exists(), reason="log171.bin missing")
def test_parse_log171_bin():
    pytest.importorskip("pymavlink")
    from parsers.ardupilot import parse_ardupilot_bin_to_l1

    payload = parse_ardupilot_bin_to_l1(LOG171, max_records=10)
    assert len(payload["records"]) <= 10
    assert payload["records"][0]["lat"] < 0  # Australia SITL-ish


@pytest.mark.skipif(not TLOG.exists(), reason="flight.tlog missing")
def test_parse_tlog():
    pytest.importorskip("pymavlink")
    from parsers.ardupilot import parse_ardupilot_tlog_to_l1

    payload = parse_ardupilot_tlog_to_l1(TLOG, flight_id="tlog-test", max_records=25, stride=5)
    assert payload["source"] == "ardupilot-tlog"
    assert 1 <= len(payload["records"]) <= 25
    first = payload["records"][0]
    assert first["lat"] < 0
    assert "battery_pct" in first or "battery_v" in first
    # Attitude may arrive after the first GPS sample in the stream.
    assert any("yaw" in r for r in payload["records"])
