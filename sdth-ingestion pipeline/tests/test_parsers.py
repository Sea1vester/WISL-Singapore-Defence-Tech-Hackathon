import json
from pathlib import Path

from wisl_ingest.parsers.hexcode_parser import VendorHexCodeParser


def test_vendor_hex_parser_maps_known_code(tmp_path: Path):
    table_path = tmp_path / "vendor.json"
    table_path.write_text(json.dumps({"0x1A3": {"message_type": "GPS_MULTIPATH_WARNING"}}))

    log_path = tmp_path / "flight.hex"
    log_path.write_text("2026-07-11T10:00:00,0x1A3\n2026-07-11T10:00:01,0xDEAD\n")

    parser = VendorHexCodeParser(table_path)
    assert parser.can_parse(log_path)

    entries = list(parser.parse(log_path))
    assert len(entries) == 2
    assert entries[0].message_type == "GPS_MULTIPATH_WARNING"
    assert entries[0].fields == {"hex_code": "0x1A3"}
    assert entries[1].message_type == "UNKNOWN_HEX_CODE"


def test_vendor_hex_parser_rejects_other_extensions(tmp_path: Path):
    table_path = tmp_path / "vendor.json"
    table_path.write_text("{}")
    parser = VendorHexCodeParser(table_path)
    assert not parser.can_parse(tmp_path / "flight.bin")
