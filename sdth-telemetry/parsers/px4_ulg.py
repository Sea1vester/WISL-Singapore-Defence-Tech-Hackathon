"""Parse PX4 / Auterion ULog (.ulg) files into L1 ingest JSON."""

from __future__ import annotations

import math
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Common PX4 SITL home (Zurich) used when logs have no GPS / ref lat-lon.
DEFAULT_ORIGIN_LAT = 47.397742
DEFAULT_ORIGIN_LON = 8.545594
R_EARTH_M = 6371000.0


def _require_pyulog():
    try:
        from pyulog import ULog  # noqa: F401
    except ImportError as exc:
        raise ImportError(
            "pyulog is required for .ulg parsing. "
            "Install with: pip install pyulog  (or use sdth-telemetry/.venv)"
        ) from exc


def _get_dataset(ulog: Any, name: str, multi_instance: int = 0) -> Any | None:
    for dataset in ulog.data_list:
        if dataset.name == name and dataset.multi_id == multi_instance:
            return dataset
    return None


def _ulog_ts_to_utc(ts_us: float, *, t0_us: float, wall_start: datetime | None) -> str:
    """ULog timestamps are microseconds since boot; map to UTC using wall_start."""
    if wall_start is None:
        # Deterministic synthetic timeline anchored at Unix epoch + relative seconds.
        seconds = max(0.0, (ts_us - t0_us) / 1e6)
        dt = datetime(1970, 1, 1, tzinfo=timezone.utc).timestamp() + seconds
        return datetime.fromtimestamp(dt, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
    seconds = max(0.0, (ts_us - t0_us) / 1e6)
    dt = wall_start.timestamp() + seconds
    return datetime.fromtimestamp(dt, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _quat_to_euler_deg(w: float, x: float, y: float, z: float) -> tuple[float, float, float]:
    """Convert PX4 quaternion (w,x,y,z) to roll/pitch/yaw degrees."""
    sinr_cosp = 2.0 * (w * x + y * z)
    cosr_cosp = 1.0 - 2.0 * (x * x + y * y)
    roll = math.atan2(sinr_cosp, cosr_cosp)

    sinp = 2.0 * (w * y - z * x)
    if abs(sinp) >= 1:
        pitch = math.copysign(math.pi / 2, sinp)
    else:
        pitch = math.asin(sinp)

    siny_cosp = 2.0 * (w * z + x * y)
    cosy_cosp = 1.0 - 2.0 * (y * y + z * z)
    yaw = math.atan2(siny_cosp, cosy_cosp)

    return (math.degrees(roll), math.degrees(pitch), math.degrees(yaw))


def _ned_to_lat_lon(
    north_m: float,
    east_m: float,
    origin_lat: float,
    origin_lon: float,
) -> tuple[float, float]:
    lat = origin_lat + math.degrees(north_m / R_EARTH_M)
    lon = origin_lon + math.degrees(east_m / (R_EARTH_M * math.cos(math.radians(origin_lat))))
    return lat, lon


def _nearest_index(timestamps: Any, target: float) -> int:
    # timestamps are monotonic; linear scan is fine for small logs, binary for large.
    import numpy as np

    idx = int(np.searchsorted(timestamps, target, side="left"))
    if idx <= 0:
        return 0
    if idx >= len(timestamps):
        return len(timestamps) - 1
    before = timestamps[idx - 1]
    after = timestamps[idx]
    return idx if abs(after - target) < abs(before - target) else idx - 1


def _extract_gps_records(ulog: Any) -> list[dict[str, Any]] | None:
    import numpy as np

    dataset = _get_dataset(ulog, "vehicle_gps_position")
    if dataset is None:
        return None
    data = dataset.data
    if not all(k in data for k in ("lat", "lon", "alt", "timestamp")):
        return None

    t = data["timestamp"]
    lat = data["lat"].astype(np.float64) / 1e7
    lon = data["lon"].astype(np.float64) / 1e7
    alt = data["alt"].astype(np.float64) / 1e3
    fix = data.get("fix_type")
    mask = np.ones(len(t), dtype=bool)
    if fix is not None:
        mask &= fix >= 3
    t, lat, lon, alt = t[mask], lat[mask], lon[mask], alt[mask]
    if len(t) == 0:
        return None

    records = []
    for i in range(len(t)):
        records.append(
            {
                "timestamp_us": float(t[i]),
                "lat": float(lat[i]),
                "lon": float(lon[i]),
                "alt_m": float(alt[i]),
                "position_frame": "gps_wgs84",
            }
        )
    return records


def _extract_local_records(
    ulog: Any,
    *,
    origin_lat: float,
    origin_lon: float,
) -> list[dict[str, Any]] | None:
    import numpy as np

    dataset = _get_dataset(ulog, "vehicle_local_position")
    if dataset is None:
        return None
    data = dataset.data
    if not all(k in data for k in ("x", "y", "z", "timestamp")):
        return None

    t = data["timestamp"]
    north = data["x"].astype(np.float64)
    east = data["y"].astype(np.float64)
    down = data["z"].astype(np.float64)

    # Prefer estimator-valid samples when any exist; many SITL/short logs mark xy_valid=0
    # even when x/y/z are populated and usable for path viz.
    mask = np.ones(len(t), dtype=bool)
    if "xy_valid" in data and "z_valid" in data:
        strict = data["xy_valid"].astype(bool) & data["z_valid"].astype(bool)
        if int(strict.sum()) > 0:
            mask = strict
    t, north, east, down = t[mask], north[mask], east[mask], down[mask]
    if len(t) == 0:
        return None

    ref_lat = data.get("ref_lat")
    ref_lon = data.get("ref_lon")
    ref_alt = data.get("ref_alt")

    records: list[dict[str, Any]] = []
    for i in range(len(t)):
        up = float(-down[i])
        o_lat, o_lon = origin_lat, origin_lon
        frame = "local_ned_projected"
        if ref_lat is not None and ref_lon is not None:
            rlat = float(ref_lat[i]) if hasattr(ref_lat, "__getitem__") else float(ref_lat)
            rlon = float(ref_lon[i]) if hasattr(ref_lon, "__getitem__") else float(ref_lon)
            if math.isfinite(rlat) and math.isfinite(rlon) and abs(rlat) > 1e-6:
                o_lat, o_lon = rlat, rlon
                frame = "local_ned_ref"
        lat, lon = _ned_to_lat_lon(float(north[i]), float(east[i]), o_lat, o_lon)
        alt_m = up
        if ref_alt is not None:
            ralt = float(ref_alt[i]) if hasattr(ref_alt, "__getitem__") else float(ref_alt)
            if math.isfinite(ralt):
                alt_m = ralt + up

        records.append(
            {
                "timestamp_us": float(t[i]),
                "lat": lat,
                "lon": lon,
                "alt_m": round(alt_m, 4),
                "north_m": round(float(north[i]), 4),
                "east_m": round(float(east[i]), 4),
                "up_m": round(up, 4),
                "position_frame": frame,
            }
        )
    return records


def _attach_attitude(ulog: Any, records: list[dict[str, Any]]) -> None:
    import numpy as np

    dataset = _get_dataset(ulog, "vehicle_attitude")
    if dataset is None or not records:
        return
    data = dataset.data
    if not all(k in data for k in ("timestamp", "q[0]", "q[1]", "q[2]", "q[3]")):
        return
    ts = data["timestamp"]
    for record in records:
        idx = _nearest_index(ts, record["timestamp_us"])
        roll, pitch, yaw = _quat_to_euler_deg(
            float(data["q[0]"][idx]),
            float(data["q[1]"][idx]),
            float(data["q[2]"][idx]),
            float(data["q[3]"][idx]),
        )
        record["roll"] = round(roll, 4)
        record["pitch"] = round(pitch, 4)
        record["yaw"] = round(yaw, 4)


def _attach_battery(ulog: Any, records: list[dict[str, Any]]) -> None:
    dataset = _get_dataset(ulog, "battery_status")
    if dataset is None or not records:
        return
    data = dataset.data
    if "timestamp" not in data:
        return
    ts = data["timestamp"]
    for record in records:
        idx = _nearest_index(ts, record["timestamp_us"])
        if "remaining" in data:
            rem = float(data["remaining"][idx])
            # PX4 remaining is usually 0..1
            record["battery_pct"] = round(rem * 100.0 if rem <= 1.0 else rem, 2)
        if "voltage_v" in data:
            record["battery_v"] = round(float(data["voltage_v"][idx]), 4)


def parse_px4_ulg_to_l1(
    path: Path | str,
    *,
    flight_id: str | None = None,
    source: str = "px4-ulg",
    event_id: str | None = None,
    origin_lat: float = DEFAULT_ORIGIN_LAT,
    origin_lon: float = DEFAULT_ORIGIN_LON,
    stride: int = 1,
    max_records: int | None = None,
    wall_start_utc: datetime | None = None,
) -> dict[str, Any]:
    """Convert a PX4/Auterion ``.ulg`` into one L1 ingest payload."""
    _require_pyulog()
    from pyulog import ULog

    path = Path(path)
    if path.suffix.lower() != ".ulg":
        raise ValueError(f"Expected a .ulg file, got {path}")

    flight_id = flight_id or str(uuid.uuid4())
    event_id = event_id or f"ulg-{path.stem[:8]}-{uuid.uuid4().hex[:8]}"

    ulog = ULog(str(path))
    records = _extract_gps_records(ulog)
    if records is None:
        records = _extract_local_records(ulog, origin_lat=origin_lat, origin_lon=origin_lon)
    if not records:
        available = sorted({d.name for d in ulog.data_list})
        raise ValueError(
            "No usable position topic (vehicle_gps_position / vehicle_local_position). "
            f"Topics: {', '.join(available[:40])}"
        )

    if stride > 1:
        records = records[::stride]
    if max_records is not None:
        records = records[:max_records]

    _attach_attitude(ulog, records)
    _attach_battery(ulog, records)

    t0 = records[0]["timestamp_us"]
    out_records: list[dict[str, Any]] = []
    for record in records:
        ts_us = record.pop("timestamp_us")
        item = {
            "lat": record["lat"],
            "lon": record["lon"],
            "alt_m": record["alt_m"],
            "timestamp_utc": _ulog_ts_to_utc(ts_us, t0_us=t0, wall_start=wall_start_utc),
            "drone_model": "px4",
            **{k: v for k, v in record.items() if k not in {"lat", "lon", "alt_m"}},
        }
        out_records.append(item)

    return {
        "flight_id": flight_id,
        "timestamp_utc": out_records[0]["timestamp_utc"],
        "source": source,
        "event_id": event_id,
        "records": out_records,
    }
