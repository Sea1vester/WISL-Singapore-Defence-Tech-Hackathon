"""Parse ArduPilot DataFlash (.bin) and MAVLink telemetry (.tlog) into L1 JSON."""

from __future__ import annotations

import math
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _require_pymavlink():
    try:
        from pymavlink import DFReader, mavutil  # noqa: F401
    except ImportError as exc:
        raise ImportError(
            "pymavlink is required for ArduPilot parsing. "
            "Install with: pip install pymavlink  (or use sdth-telemetry/.venv)"
        ) from exc


def _us_to_utc(time_us: float, *, t0_us: float) -> str:
    seconds = max(0.0, (time_us - t0_us) / 1e6)
    dt = datetime(1970, 1, 1, tzinfo=timezone.utc).timestamp() + seconds
    return datetime.fromtimestamp(dt, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _msg_time_us(msg: Any) -> float | None:
    data = msg.to_dict()
    for key in ("TimeUS", "time_usec", "TimeMS", "time_boot_ms"):
        if key in data and data[key] is not None:
            value = float(data[key])
            if key in ("TimeMS", "time_boot_ms"):
                return value * 1000.0
            return value
    return None


def parse_ardupilot_bin_to_l1(
    path: Path | str,
    *,
    flight_id: str | None = None,
    source: str = "ardupilot-bin",
    event_id: str | None = None,
    min_gps_status: int = 3,
    stride: int = 1,
    max_records: int | None = None,
) -> dict[str, Any]:
    """Convert an ArduPilot DataFlash ``.bin`` log into L1 ingest JSON."""
    _require_pymavlink()
    from pymavlink import DFReader

    path = Path(path)
    flight_id = flight_id or str(uuid.uuid4())
    event_id = event_id or f"bin-{path.stem[:12]}-{uuid.uuid4().hex[:8]}"

    log = DFReader.DFReader_binary(str(path))
    records: list[dict[str, Any]] = []
    latest_att: dict[str, Any] = {}
    latest_bat: dict[str, Any] = {}
    warnings: list[str] = []
    sample_i = 0
    t0_us: float | None = None

    while True:
        msg = log.recv_msg()
        if msg is None:
            break
        mtype = msg.get_type()
        data = msg.to_dict()
        t_us = _msg_time_us(msg)

        if mtype == "ATT":
            latest_att = {}
            if data.get("Roll") is not None:
                latest_att["roll"] = round(float(data["Roll"]), 4)
            if data.get("Pitch") is not None:
                latest_att["pitch"] = round(float(data["Pitch"]), 4)
            if data.get("Yaw") is not None:
                latest_att["yaw"] = round(float(data["Yaw"]), 4)
            continue

        if mtype in {"BAT", "BATTERY", "CURR"}:
            volt = data.get("Volt", data.get("Voltage"))
            rem = data.get("RemPct", data.get("Remaining"))
            latest_bat = {}
            if volt is not None:
                latest_bat["battery_v"] = float(volt)
            if rem is not None:
                latest_bat["battery_pct"] = float(rem)
            continue

        if mtype == "ERR":
            warnings.append(f"ERR Subsys={data.get('Subsys')} ECode={data.get('ECode')}")
            continue

        if mtype == "MSG" and data.get("Message"):
            text = str(data["Message"]).strip()
            if text:
                warnings.append(text)
            continue

        if mtype != "GPS":
            continue

        status = int(data.get("Status") or 0)
        lat = data.get("Lat")
        lon = data.get("Lng", data.get("Lon"))
        if lat is None or lon is None or status < min_gps_status:
            continue
        if abs(float(lat)) < 1e-6 and abs(float(lon)) < 1e-6:
            continue

        sample_i += 1
        if stride > 1 and (sample_i - 1) % stride != 0:
            continue

        if t_us is None:
            t_us = float(sample_i) * 1e5
        if t0_us is None:
            t0_us = t_us

        alt = data.get("Alt", data.get("RelAlt"))
        record: dict[str, Any] = {
            "lat": float(lat),
            "lon": float(lon),
            "timestamp_utc": _us_to_utc(t_us, t0_us=t0_us),
            "drone_model": "ardupilot",
            "position_frame": "gps_wgs84",
            **latest_att,
            **latest_bat,
        }
        if alt is not None:
            record["alt_m"] = round(float(alt), 4)
        if data.get("Spd") is not None:
            record["speed_ms"] = round(float(data["Spd"]), 4)
        if data.get("NSats") is not None:
            record["gps_satellites"] = int(data["NSats"])

        records.append(record)
        if max_records is not None and len(records) >= max_records:
            break

    if not records:
        raise ValueError(f"No usable GPS rows in ArduPilot DataFlash log: {path}")

    if warnings:
        records[0]["warning"] = " | ".join(warnings[:20])

    return {
        "flight_id": flight_id,
        "timestamp_utc": records[0]["timestamp_utc"],
        "source": source,
        "event_id": event_id,
        "records": records,
    }


def parse_ardupilot_tlog_to_l1(
    path: Path | str,
    *,
    flight_id: str | None = None,
    source: str = "ardupilot-tlog",
    event_id: str | None = None,
    min_fix_type: int = 3,
    stride: int = 1,
    max_records: int | None = None,
) -> dict[str, Any]:
    """Convert a MAVLink ``.tlog`` into L1 ingest JSON."""
    _require_pymavlink()
    from pymavlink import mavutil

    path = Path(path)
    flight_id = flight_id or str(uuid.uuid4())
    event_id = event_id or f"tlog-{path.stem[:12]}-{uuid.uuid4().hex[:8]}"

    mlog = mavutil.mavlink_connection(str(path))
    records: list[dict[str, Any]] = []
    latest_att: dict[str, Any] = {}
    latest_bat: dict[str, Any] = {}
    sample_i = 0
    t0_us: float | None = None
    seen_gps_raw = False

    while True:
        msg = mlog.recv_match(blocking=False)
        if msg is None:
            break
        mtype = msg.get_type()
        if mtype == "BAD_DATA":
            continue
        data = msg.to_dict()

        if mtype == "ATTITUDE":
            latest_att = {
                "roll": round(math.degrees(float(data["roll"])), 4),
                "pitch": round(math.degrees(float(data["pitch"])), 4),
                "yaw": round(math.degrees(float(data["yaw"])), 4),
            }
            continue

        if mtype == "SYS_STATUS":
            volt_mv = data.get("voltage_battery")
            rem = data.get("battery_remaining")
            latest_bat = {}
            if volt_mv not in (None, 65535):
                latest_bat["battery_v"] = round(float(volt_mv) / 1000.0, 4)
            if rem not in (None, -1):
                latest_bat["battery_pct"] = float(rem)
            continue

        pos: dict[str, Any] | None = None
        t_us = _msg_time_us(msg)
        if mtype == "GPS_RAW_INT":
            seen_gps_raw = True
            fix = int(data.get("fix_type") or 0)
            if fix < min_fix_type:
                continue
            lat = float(data["lat"]) / 1e7
            lon = float(data["lon"]) / 1e7
            if abs(lat) < 1e-6 and abs(lon) < 1e-6:
                continue
            pos = {
                "lat": lat,
                "lon": lon,
                "alt_m": float(data["alt"]) / 1000.0 if data.get("alt") is not None else None,
                "speed_ms": float(data["vel"]) / 100.0 if data.get("vel") is not None else None,
                "gps_satellites": int(data["satellites_visible"])
                if data.get("satellites_visible") is not None
                else None,
            }
        elif mtype == "GLOBAL_POSITION_INT":
            if seen_gps_raw:
                continue
            lat = float(data["lat"]) / 1e7
            lon = float(data["lon"]) / 1e7
            if abs(lat) < 1e-6 and abs(lon) < 1e-6:
                continue
            pos = {
                "lat": lat,
                "lon": lon,
                "alt_m": float(data["alt"]) / 1000.0 if data.get("alt") is not None else None,
            }

        if pos is None:
            continue

        sample_i += 1
        if stride > 1 and (sample_i - 1) % stride != 0:
            continue

        if t_us is None:
            t_us = float(sample_i) * 1e5
        if t0_us is None:
            t0_us = t_us

        record: dict[str, Any] = {
            "lat": pos["lat"],
            "lon": pos["lon"],
            "timestamp_utc": _us_to_utc(t_us, t0_us=t0_us),
            "drone_model": "ardupilot",
            "position_frame": "gps_wgs84",
            **latest_att,
            **latest_bat,
        }
        if pos.get("alt_m") is not None:
            record["alt_m"] = round(float(pos["alt_m"]), 4)
        if pos.get("speed_ms") is not None:
            record["speed_ms"] = round(float(pos["speed_ms"]), 4)
        if pos.get("gps_satellites") is not None:
            record["gps_satellites"] = pos["gps_satellites"]

        records.append(record)
        if max_records is not None and len(records) >= max_records:
            break

    if not records:
        raise ValueError(f"No usable GPS messages in ArduPilot tlog: {path}")

    return {
        "flight_id": flight_id,
        "timestamp_utc": records[0]["timestamp_utc"],
        "source": source,
        "event_id": event_id,
        "records": records,
    }
