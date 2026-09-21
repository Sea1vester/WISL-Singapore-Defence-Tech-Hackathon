"""Map generic telemetry tables (dict rows) into L1 ingest JSON.

Shared by the Excel and generic-CSV paths. Detection needs nothing beyond the
header row: a lat key plus a lon key (case-insensitive) is enough.
"""

from __future__ import annotations

import math
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

GENERIC_LAT_KEYS = ("lat", "latitude", "gps_lat", "OSD.latitude")
GENERIC_LON_KEYS = ("lon", "lng", "longitude", "gps_lon", "OSD.longitude")
GENERIC_ALT_KEYS = ("alt_m", "alt", "altitude", "altitude_m", "OSD.altitude [ft]", "OSD.height [ft]")
GENERIC_ROLL_KEYS = ("roll_deg", "roll")
GENERIC_PITCH_KEYS = ("pitch_deg", "pitch")
GENERIC_YAW_KEYS = ("yaw_deg", "yaw", "heading")
GENERIC_BATTERY_PCT_KEYS = ("battery_pct", "battery_remaining", "battery", "battery_percent")
GENERIC_BATTERY_V_KEYS = ("voltage", "voltage_v", "battery_v", "volt")
GENERIC_MODE_KEYS = ("mode", "flight_mode")
GENERIC_WARNING_KEYS = ("warning", "message")
GENERIC_TIMESTAMP_KEYS = ("timestamp_utc", "timestamp", "timestamps", "time", "datetime")
GENERIC_SECONDS_KEYS = ("sec", "time_s", "t", "flight_time", "elapsed_s")

# If every attitude value in the file fits inside |pi| + epsilon, the source
# logged radians (ArduPilot-style exports) rather than degrees.
_RADIANS_MAX_ABS = 3.2

_SYNTHETIC_EPOCH = datetime(2000, 1, 1, tzinfo=timezone.utc)


def _pick(row: dict[str, str], keys: tuple[str, ...]) -> str | None:
    lower_map = {k.lower(): k for k in row}
    for key in keys:
        if key in row and row[key] != "":
            return row[key]
        real = lower_map.get(key.lower())
        if real and row[real] != "":
            return row[real]
    return None


def _pick_key(row: dict[str, str], keys: tuple[str, ...]) -> str | None:
    lower_map = {k.lower(): k for k in row}
    for key in keys:
        if key in row:
            return key
        real = lower_map.get(key.lower())
        if real:
            return real
    return None


def _as_float(value: str | None) -> float | None:
    if value is None:
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(result):
        return None
    return result


def _attitude_in_radians(rows: list[dict[str, str]]) -> bool:
    values: list[float] = []
    for row in rows:
        for keys in (GENERIC_ROLL_KEYS, GENERIC_PITCH_KEYS, GENERIC_YAW_KEYS):
            value = _as_float(_pick(row, keys))
            if value is not None:
                values.append(value)
    return bool(values) and all(abs(v) <= _RADIANS_MAX_ABS for v in values)


def _seconds_column(rows: list[dict[str, str]]) -> str | None:
    for row in rows:
        key = _pick_key(row, GENERIC_SECONDS_KEYS)
        if key and _as_float(row.get(key)) is not None:
            return key
    return None


def _parse_generic_rows_to_l1(
    rows: list[dict[str, str]],
    *,
    flight_id: str | None = None,
    source: str = "excel-generic",
    event_id: str | None = None,
    skip_zero_gps: bool = True,
    max_records: int | None = None,
    stem: str = "excel",
) -> dict[str, Any]:
    flight_id = flight_id or str(uuid.uuid4())
    event_id = event_id or f"generic-{stem}-{uuid.uuid4().hex[:8]}"
    records: list[dict[str, Any]] = []

    attitude_rad = _attitude_in_radians(rows)
    seconds_key = _seconds_column(rows)

    for row in rows:
        lat_s = _pick(row, GENERIC_LAT_KEYS)
        lon_s = _pick(row, GENERIC_LON_KEYS)
        if lat_s is None or lon_s is None:
            continue
        try:
            lat = float(lat_s)
            lon = float(lon_s)
        except ValueError:
            continue
        if skip_zero_gps and abs(lat) < 1e-6 and abs(lon) < 1e-6:
            continue

        record: dict[str, Any] = {"lat": lat, "lon": lon}
        alt_s = _pick(row, GENERIC_ALT_KEYS)
        if alt_s is not None:
            try:
                alt = float(alt_s)
                # Heuristic: OSD height/altitude in ft if column name mentions ft
                alt_key = next(
                    (k for k in row if k.lower() in {x.lower() for x in GENERIC_ALT_KEYS} and row[k] == alt_s),
                    "",
                )
                if "ft" in alt_key.lower():
                    alt *= 0.3048
                record["alt_m"] = round(alt, 4)
            except ValueError:
                pass

        attitude_keys = (
            (GENERIC_ROLL_KEYS, "roll_deg"),
            (GENERIC_PITCH_KEYS, "pitch_deg"),
            (GENERIC_YAW_KEYS, "yaw_deg"),
        )
        attitude_seen = False
        for keys, out_key in attitude_keys:
            value = _as_float(_pick(row, keys))
            if value is None:
                continue
            attitude_seen = True
            record[out_key] = round(math.degrees(value), 4) if attitude_rad else value
        if attitude_seen and attitude_rad:
            record["attitude_units_inferred"] = "rad"

        percent = _as_float(_pick(row, GENERIC_BATTERY_PCT_KEYS))
        if percent is not None:
            record["battery_pct"] = percent
        voltage = _as_float(_pick(row, GENERIC_BATTERY_V_KEYS))
        if voltage is not None:
            record["battery_v"] = voltage

        mode = _pick(row, GENERIC_MODE_KEYS)
        if mode:
            record["flight_mode"] = mode
        warning = _pick(row, GENERIC_WARNING_KEYS)
        if warning:
            record["warning"] = warning

        ts = _pick(row, GENERIC_TIMESTAMP_KEYS)
        if ts:
            record["timestamp_utc"] = ts
        elif seconds_key is not None:
            seconds = _as_float(row.get(seconds_key))
            if seconds is not None:
                record["timestamp_utc"] = (
                    _SYNTHETIC_EPOCH + timedelta(seconds=seconds)
                ).isoformat().replace("+00:00", "Z")
                record["time_origin"] = "synthetic_relative"

        records.append(record)
        if max_records is not None and len(records) >= max_records:
            break

    if not records:
        raise ValueError(
            "Rows are not DJI FlightRecord and lack generic lat/lon columns "
            f"(tried {GENERIC_LAT_KEYS} / {GENERIC_LON_KEYS})"
        )

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
