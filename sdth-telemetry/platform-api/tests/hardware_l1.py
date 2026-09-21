"""L1 records shaped like each hardware parser in this repo.

These are the normalized ingest records those logs become *after* parsing,
which is what incident indexing actually sees.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any


def _ts(i: int, start: datetime | None = None) -> str:
    start = start or datetime(2026, 7, 16, 15, 0, 0, tzinfo=timezone.utc)
    return (start + timedelta(seconds=i)).strftime("%Y-%m-%dT%H:%M:%SZ")


def _payload(flight_id: str, source: str, records: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "flight_id": flight_id,
        "timestamp_utc": records[0].get("timestamp_utc") or _ts(0),
        "source": source,
        "event_id": f"evt-{flight_id}",
        "records": records,
    }


def dji_l1(flight_id: str = "flight-dji", *, inject: str | None = "warning") -> dict[str, Any]:
    records = []
    for i in range(8):
        record = {
            "timestamp_utc": _ts(i),
            "lat": 1.3521 + i * 0.00001,
            "lon": 103.8198,
            "alt_m": 40.0 + i,
            "roll": 1.1,
            "pitch": -0.4,
            "yaw": 45.0,
            "battery_pct": 52 - i * 0.2,
            "battery_v": 7.45,
            "drone_model": "Mini 4 Pro",
            "flight_mode": "P-GPS",
            "gps_satellites": 14,
        }
        if inject == "warning" and i == 1:
            record["warning"] = "GPS signal weak"
        if inject == "battery_low" and i >= 5:
            record["battery_pct"] = 12.0
        records.append(record)
    if inject is None:
        records.append({
            "timestamp_utc": _ts(8),
            "lat": 1.3521,
            "lon": 103.8198,
            "alt_m": 35.0,
            "flight_mode": "LAND",
            "battery_pct": 50,
            "drone_model": "Mini 4 Pro",
        })
    return _payload(flight_id, "dji-csv", records)


def px4_l1(flight_id: str = "flight-px4", *, inject: str | None = "battery_plunge") -> dict[str, Any]:
    records = []
    for i in range(8):
        record = {
            "timestamp_utc": _ts(i),
            "lat": 1.3521,
            "lon": 103.8198,
            "alt_m": 80.0,
            "roll": 2.0,
            "pitch": 1.0,
            "yaw": 10.0,
            "battery_pct": 88.0 if i < 4 else 88.0 - (i - 3) * 16.0,
            "battery_v": 15.8,
            "drone_model": "px4",
        }
        records.append(record)
    if inject != "battery_plunge":
        for record in records:
            record["battery_pct"] = 88.0
    return _payload(flight_id, "px4-ulg", records)


def ardupilot_l1(flight_id: str = "flight-ardupilot", *, inject: str | None = "attitude") -> dict[str, Any]:
    records = []
    for i in range(8):
        record = {
            "timestamp_utc": _ts(i),
            "lat": 1.35,
            "lon": 103.82,
            "alt_m": 0.0 if i < 5 else 30.0,
            "roll": 3.0,
            "pitch": 2.0,
            "yaw": 90.0,
            "battery_pct": 70.0,
            "battery_v": 16.2,
            "drone_model": "ArduCopter",
            "warning": "ERR Subsys=2 ECode=1" if inject == "attitude" and i == 4 else None,
        }
        if inject == "attitude" and i == 5:
            record["roll"] = 78.0
            record["pitch"] = -12.0
        records.append(record)
    return _payload(flight_id, "ardupilot-bin", records)


def hermes_l1(flight_id: str = "flight-hermes", *, inject: str | None = "altitude") -> dict[str, Any]:
    records = []
    for i in range(6):
        record = {
            "timestamp_utc": _ts(i),
            "lat": 1.3521 + i * 0.00002,
            "lon": 103.8198 + i * 0.00002,
            "alt_msl": 400.0 + i,
            "heading": 45.0,
            "drone_model": "Hermes 900",
            "_source_format": "hermes900_stanag",
        }
        if inject == "altitude" and i == 3:
            record["alt_msl"] = 480.0
        records.append(record)
    return _payload(flight_id, "hermes-stanag", records)


def orbiter_l1(flight_id: str = "flight-orbiter", *, inject: str | None = "gps_jump") -> dict[str, Any]:
    records = []
    for i in range(6):
        record = {
            "timestamp_utc": _ts(i),
            "lat": 1.3520 + i * 0.00003,
            "lon": 103.8197,
            "alt_m": 120.5,
            "roll_deg": 1.1,
            "pitch_deg": 0.5,
            "yaw_deg": 88.0,
            "battery_pct": 95 - i,
            "drone_model": "Orbiter 4",
        }
        if inject == "gps_jump" and i == 3:
            record["lat"] = 1.4520
            record["lon"] = 103.9197
        records.append(record)
    return _payload(flight_id, "orbiter4-json", records)


def aunav_l1(flight_id: str = "flight-aunav", *, inject: str | None = "gps_jump") -> dict[str, Any]:
    records = []
    for i in range(6):
        record = {
            "timestamp_utc": _ts(i),
            "pos_x": 45.0 + i * 0.1,
            "pos_y": 12.0,
            "pos_z": 0.0,
            "arm_ext_m": 1.2,
            "drone_model": "aunav.NEO HD",
            "_source_format": "aunav_ros",
        }
        if inject == "gps_jump" and i == 3:
            record["pos_x"] = 120.0
        records.append(record)
    return _payload(flight_id, "aunav-ros", records)


HARDWARE_CASES = (
    ("dji", dji_l1, "operator_warning"),
    ("px4", px4_l1, "battery_plunge"),
    ("ardupilot", ardupilot_l1, "attitude_shock"),
    ("hermes900", hermes_l1, "altitude_spike"),
    ("orbiter4", orbiter_l1, "gps_jump"),
    ("aunav", aunav_l1, "gps_jump"),
)
