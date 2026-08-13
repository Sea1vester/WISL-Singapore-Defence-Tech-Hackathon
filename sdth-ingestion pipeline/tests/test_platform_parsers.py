from pathlib import Path

from wisl_ingest.parsers.aunav_parser import AunavParser
from wisl_ingest.parsers.hermes900_parser import Hermes900Parser
from wisl_ingest.parsers.orbiter4_parser import Orbiter4Parser

HERMES_LINE_1 = (
    "<123>1 2026-07-16T15:00:00.000Z drone-hermes900 flight-system 4586 - - "
    "[STANAG_MSG] VEHICLE_STEERING lat=1.3521 lon=103.8198 alt_msl=400.0 heading=45.0"
)
HERMES_LINE_2 = (
    "<123>1 2026-07-16T15:00:01.000Z drone-hermes900 flight-system 4586 - - "
    "[STANAG_MSG] VEHICLE_STEERING lat=1.3522 lon=103.8199 alt_msl=401.0 heading=45.2"
)

ORBITER_JSON = """[
  {"timestamp_ms": 1718550000000, "lat": 1.352, "lon": 103.8197, "alt_m": 120.5,
   "roll_deg": 1.1, "pitch_deg": 0.5, "yaw_deg": 88.0, "battery_pct": 95},
  {"timestamp_ms": 1718550001000, "lat": 1.3523, "lon": 103.8194, "alt_m": 121.0,
   "roll_deg": 1.2, "pitch_deg": 0.4, "yaw_deg": 87.5, "battery_pct": 94}
]"""

ORBITER_CSV = (
    "timestamp_ms,lat,lon,alt_m,roll_deg,pitch_deg,yaw_deg,battery_pct\n"
    "1718550000000,1.352,103.8197,120.5,1.1,0.5,88.0,95\n"
)

AUNAV_LINE_1 = "[ROS_INFO] [1718550000.000000] /aunav/robot_state pos_x=45.0 pos_y=12.0 pos_z=0.0 arm_ext_m=1.2"
AUNAV_LINE_2 = "[ROS_INFO] [1718550001.000000] /aunav/robot_state pos_x=45.1 pos_y=12.0 pos_z=0.0 arm_ext_m=1.5"


def test_hermes900_parser_extracts_fields_and_timestamp(tmp_path: Path):
    path = tmp_path / "flight_log.stanag"
    path.write_text(HERMES_LINE_1 + "\n" + HERMES_LINE_2 + "\n")

    parser = Hermes900Parser()
    assert parser.can_parse(path)

    entries = list(parser.parse(path))
    assert len(entries) == 2
    assert entries[0].message_type == "VEHICLE_STEERING"
    assert entries[0].fields["lat"] == 1.3521
    assert entries[0].fields["lon"] == 103.8198
    assert entries[0].fields["alt_msl"] == 400.0
    assert entries[0].fields["heading"] == 45.0
    assert entries[0].fields["drone_model"] == "Hermes 900"
    assert entries[0].timestamp.isoformat() == "2026-07-16T15:00:00+00:00"


def test_hermes900_parser_skips_malformed_lines(tmp_path: Path):
    path = tmp_path / "flight_log.stanag"
    path.write_text("not a syslog line\n" + HERMES_LINE_1 + "\n")

    entries = list(Hermes900Parser().parse(path))
    assert len(entries) == 1


def test_orbiter4_parser_json_uses_real_timestamp(tmp_path: Path):
    path = tmp_path / "orbiter_log.json"
    path.write_text(ORBITER_JSON)

    parser = Orbiter4Parser()
    assert parser.can_parse(path)

    entries = list(parser.parse(path))
    assert len(entries) == 2
    assert entries[0].message_type == "ORBITER_STATE"
    assert entries[0].fields["lat"] == 1.352
    assert entries[0].fields["battery_pct"] == 95
    assert entries[0].fields["drone_model"] == "Orbiter 4"
    assert "timestamp_ms" not in entries[0].fields
    assert entries[0].timestamp.timestamp() == 1718550000000 / 1000


def test_orbiter4_parser_csv(tmp_path: Path):
    path = tmp_path / "orbiter_export.csv"
    path.write_text(ORBITER_CSV)

    parser = Orbiter4Parser()
    assert parser.can_parse(path)

    entries = list(parser.parse(path))
    assert len(entries) == 1
    assert entries[0].fields["lat"] == 1.352
    assert entries[0].fields["battery_pct"] == 95.0
    assert entries[0].timestamp.timestamp() == 1718550000000 / 1000


def test_orbiter4_parser_ignores_files_without_orbiter_prefix(tmp_path: Path):
    parser = Orbiter4Parser()
    assert not parser.can_parse(tmp_path / "other_log.json")


def test_aunav_parser_extracts_topic_and_fields(tmp_path: Path):
    path = tmp_path / "robot_state.ros"
    path.write_text(AUNAV_LINE_1 + "\n" + AUNAV_LINE_2 + "\n")

    parser = AunavParser()
    assert parser.can_parse(path)

    entries = list(parser.parse(path))
    assert len(entries) == 2
    assert entries[0].message_type == "AUNAV_ROBOT_STATE"
    assert entries[0].fields["pos_x"] == 45.0
    assert entries[0].fields["arm_ext_m"] == 1.2
    assert entries[0].fields["drone_model"] == "aunav.NEO HD"
    assert entries[0].timestamp.timestamp() == 1718550000.0
