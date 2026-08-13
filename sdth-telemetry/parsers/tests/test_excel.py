from pathlib import Path

import pytest

from parsers.detect import detect_format


@pytest.fixture
def dji_xlsx(tmp_path: Path) -> Path:
    openpyxl = pytest.importorskip("openpyxl")
    path = tmp_path / "dji_flight.xlsx"
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(
        [
            "timestamps",
            "OSD.latitude",
            "OSD.longitude",
            "OSD.height [ft]",
            "OSD.pitch",
            "OSD.roll",
            "OSD.yaw",
            "BATTERY.chargeLevel",
            "BATTERY.voltage [V]",
            "OSD.droneType",
            "APP.warning",
        ]
    )
    ws.append([1722648654, 0, 0, 0, 0, 0, 0, 50, 15.0, "Mini 4 Pro", ""])
    ws.append([1722648670, 39.62655835, -105.0007326, 100, 1.2, -0.5, 45, 49, 14.9, "Mini 4 Pro", "weak GPS"])
    ws.append([1722648671, 39.62656, -105.00074, 110, 1.0, -0.4, 46, 49, 14.8, "Mini 4 Pro", ""])
    wb.save(path)
    return path


@pytest.fixture
def generic_xlsx(tmp_path: Path) -> Path:
    openpyxl = pytest.importorskip("openpyxl")
    path = tmp_path / "generic.xlsx"
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["timestamp", "latitude", "longitude", "altitude_m"])
    ws.append(["2024-01-01T12:00:00Z", 1.35, 103.82, 40.0])
    ws.append(["2024-01-01T12:00:01Z", 1.351, 103.821, 41.5])
    wb.save(path)
    return path


def test_detect_and_parse_dji_excel(dji_xlsx: Path):
    from parsers.excel import parse_excel_to_l1

    assert detect_format(dji_xlsx) == "dji_excel"
    payload = parse_excel_to_l1(dji_xlsx, flight_id="xlsx-dji")
    assert payload["source"] == "dji-excel"
    assert payload["flight_id"] == "xlsx-dji"
    assert len(payload["records"]) == 2
    assert payload["records"][0]["lat"] == pytest.approx(39.62655835)
    assert payload["records"][0]["alt_m"] == pytest.approx(30.48)
    assert payload["records"][0]["warning"] == "weak GPS"


def test_parse_generic_excel(generic_xlsx: Path):
    from parsers.excel import parse_excel_to_l1

    assert detect_format(generic_xlsx) == "excel"
    payload = parse_excel_to_l1(generic_xlsx)
    assert payload["source"] == "excel-generic"
    assert len(payload["records"]) == 2
    assert payload["records"][1]["alt_m"] == pytest.approx(41.5)


def test_xls_rejected(tmp_path: Path):
    from parsers.excel import parse_excel_to_l1

    path = tmp_path / "old.xls"
    path.write_bytes(b"not-a-real-xls")
    with pytest.raises(ValueError, match="Legacy .xls"):
        parse_excel_to_l1(path)
