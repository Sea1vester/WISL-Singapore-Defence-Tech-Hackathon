"""Parse DJI FlightRecord-style CSV exports into L1 ingest JSON."""

from __future__ import annotations

import csv
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

FT_TO_M = 0.3048
MPH_TO_MS = 0.44704

DJI_CSV_MARKERS = (
    "OSD.latitude",
    "OSD.longitude",
    "BATTERY.chargeLevel",
)


def is_dji_csv(fieldnames: Iterable[str] | None) -> bool:
    fields = {f.strip() for f in (fieldnames or []) if f and f.strip()}
    return all(m in fields for m in DJI_CSV_MARKERS)


def _f(row: dict[str, str], key: str, default: float | None = None) -> float | None:
    raw = row.get(key)
    if raw is None or str(raw).strip() == "":
        return default
    try:
        return float(raw)
    except (TypeError, ValueError):
        return default


def _s(row: dict[str, str], key: str) -> str | None:
    raw = row.get(key)
    if raw is None:
        return None
    text = str(raw).strip()
    return text or None


def _boolish(row: dict[str, str], key: str) -> bool | None:
    raw = _s(row, key)
    if raw is None:
        return None
    lowered = raw.lower()
    if lowered in {"true", "1", "yes"}:
        return True
    if lowered in {"false", "0", "no"}:
        return False
    return None


def _row_timestamp_utc(row: dict[str, str]) -> str | None:
    """DJI exports use unix seconds in ``timestamps`` or misnamed ``timestamps_ns``."""
    for key in ("timestamps", "timestamps_ns"):
        value = _f(row, key)
        if value is None:
            continue
        # Heuristic: values ~1e9 are unix seconds; ~1e18 would be ns.
        if value > 1e14:
            value = value / 1e9
        try:
            return datetime.fromtimestamp(value, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
        except (OverflowError, OSError, ValueError):
            continue
    return None


def _alt_m(row: dict[str, str]) -> float | None:
    height_ft = _f(row, "OSD.height [ft]")
    altitude_ft = _f(row, "OSD.altitude [ft]")
    # Zero is a valid relative height at takeoff/landing. Switching to absolute
    # altitude there creates an artificial jump equal to the launch elevation.
    if height_ft is not None:
        return height_ft * FT_TO_M
    if altitude_ft is not None:
        return altitude_ft * FT_TO_M
    return None


def row_to_record(row: dict[str, str]) -> dict[str, Any] | None:
    lat = _f(row, "OSD.latitude")
    lon = _f(row, "OSD.longitude")
    if lat is None or lon is None:
        return None

    ts = _row_timestamp_utc(row)
    alt_m = _alt_m(row)
    record: dict[str, Any] = {
        "lat": lat,
        "lon": lon,
    }
    if alt_m is not None:
        record["alt_m"] = round(alt_m, 4)
    if ts:
        record["timestamp_utc"] = ts

    pitch = _f(row, "OSD.pitch")
    roll = _f(row, "OSD.roll")
    yaw = _f(row, "OSD.yaw")
    if pitch is not None:
        record["pitch"] = pitch
    if roll is not None:
        record["roll"] = roll
    if yaw is not None:
        record["yaw"] = yaw

    batt_pct = _f(row, "BATTERY.chargeLevel")
    batt_v = _f(row, "BATTERY.voltage [V]")
    if batt_pct is not None:
        record["battery_pct"] = batt_pct
    if batt_v is not None:
        record["battery_v"] = batt_v

    speed_mph = _f(row, "OSD.hSpeed [MPH]")
    if speed_mph is not None:
        record["speed_ms"] = round(speed_mph * MPH_TO_MS, 4)

    drone = _s(row, "OSD.droneType") or _s(row, "DETAILS.aircraftName") or _s(row, "RECOVER.aircraftName")
    if drone:
        record["drone_model"] = drone

    flyc = _s(row, "OSD.flycState")
    if flyc:
        record["flight_mode"] = flyc

    on_ground = _boolish(row, "OSD.isOnGround")
    if on_ground is not None:
        record["is_on_ground"] = on_ground

    warning = _s(row, "APP.warning")
    if warning:
        record["warning"] = warning
    tip = _s(row, "APP.tip")
    if tip:
        record["tip"] = tip

    fly_s = _f(row, "OSD.flyTime [s]")
    if fly_s is not None:
        record["fly_time_s"] = fly_s

    gps_num = _f(row, "OSD.gpsNum")
    if gps_num is not None:
        record["gps_satellites"] = int(gps_num)

    home_lat = _f(row, "HOME.latitude")
    home_lon = _f(row, "HOME.longitude")
    if home_lat is not None:
        record["home_lat"] = home_lat
    if home_lon is not None:
        record["home_lon"] = home_lon

    return record


def parse_dji_rows_to_l1(
    rows: Iterable[dict[str, Any]],
    *,
    flight_id: str | None = None,
    source: str = "dji-csv",
    event_id: str | None = None,
    skip_zero_gps: bool = True,
    max_records: int | None = None,
    stem: str = "dji",
) -> dict[str, Any]:
    """Build an L1 payload from already-loaded DJI-style row dicts."""
    flight_id = flight_id or str(uuid.uuid4())
    event_id = event_id or f"dji-{stem}-{uuid.uuid4().hex[:8]}"

    records: list[dict[str, Any]] = []
    for row in rows:
        clean = {(k or "").strip(): ("" if v is None else str(v)) for k, v in row.items()}
        record = row_to_record(clean)
        if record is None:
            continue
        if skip_zero_gps and abs(record["lat"]) < 1e-6 and abs(record["lon"]) < 1e-6:
            continue
        records.append(record)
        if max_records is not None and len(records) >= max_records:
            break

    if not records:
        raise ValueError("No usable DJI telemetry rows")

    timestamp_utc = records[0].get("timestamp_utc") or datetime.now(timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )
    return {
        "flight_id": flight_id,
        "timestamp_utc": timestamp_utc,
        "source": source,
        "event_id": event_id,
        "records": records,
    }


def parse_dji_csv_to_l1(
    path: Path | str,
    *,
    flight_id: str | None = None,
    source: str = "dji-csv",
    event_id: str | None = None,
    skip_zero_gps: bool = True,
    max_records: int | None = None,
) -> dict[str, Any]:
    """Convert a DJI FlightRecord CSV into one L1 ingest payload."""
    path = Path(path)
    with path.open(newline="", encoding="utf-8-sig", errors="replace") as fh:
        reader = csv.DictReader(fh)
        if not is_dji_csv(reader.fieldnames):
            raise ValueError(
                f"{path} does not look like a DJI FlightRecord CSV "
                f"(need {', '.join(DJI_CSV_MARKERS)})"
            )
        rows = list(reader)
    return parse_dji_rows_to_l1(
        rows,
        flight_id=flight_id,
        source=source,
        event_id=event_id,
        skip_zero_gps=skip_zero_gps,
        max_records=max_records,
        stem=path.stem,
    )
