from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from parsers.registry import UnsupportedLogFormat, parse_raw_log, stable_identifiers


ROOT = Path(__file__).parents[3]
DEMO = ROOT / "sdth-telemetry" / "fixtures" / "demo"
MOCKS = ROOT / "sdth-ingestion pipeline" / "mock_logs"
SHA = "ab" * 32


@pytest.mark.parametrize(
    ("source_file", "original_name", "expected_source"),
    [
        (DEMO / "controller_mission_alpha.csv", "controller_mission_alpha.csv", "dji-csv"),
        (MOCKS / "flight_log.stanag", "flight_log.stanag", "hermes900-stanag"),
        (MOCKS / "orbiter_log.json", "orbiter_log.json", "orbiter4-json"),
        (MOCKS / "robot_state.ros", "robot_state.ros", "aunav-ros"),
    ],
)
def test_registry_parsers_emit_complete_l1_contract(
    tmp_path: Path,
    source_file: Path,
    original_name: str,
    expected_source: str,
):
    stored = tmp_path / f"generated{source_file.suffix}"
    shutil.copyfile(source_file, stored)

    payload, parser_key = parse_raw_log(
        stored,
        sha256=SHA,
        original_name=original_name,
    )

    expected_flight, expected_event = stable_identifiers(SHA)
    assert parser_key
    assert payload["flight_id"] == expected_flight
    assert payload["event_id"] == expected_event
    assert payload["source"] == expected_source
    assert len(payload["records"]) >= 2
    assert all(record.get("timestamp_utc") for record in payload["records"])


def test_registry_parses_vendor_hex_into_warning_records(tmp_path: Path):
    path = tmp_path / "error.hex"
    path.write_text("2026-08-22T10:00:00Z,0xA13F\n")

    payload, parser_key = parse_raw_log(path, sha256=SHA)

    assert parser_key == "vendor_hex"
    assert payload["records"][0]["hex_code"] == "0xA13F"
    assert payload["records"][0]["warning"] == "Vendor error code 0xA13F"


def test_registry_rejects_unsupported_and_corrupt_logs(tmp_path: Path):
    unsupported = tmp_path / "flight.txt"
    unsupported.write_text("not telemetry")
    with pytest.raises(UnsupportedLogFormat):
        parse_raw_log(unsupported, sha256=SHA)

    corrupt = tmp_path / "orbiter_corrupt.json"
    corrupt.write_text("{")
    with pytest.raises(ValueError):
        parse_raw_log(corrupt, sha256=SHA, original_name="orbiter_corrupt.json")
