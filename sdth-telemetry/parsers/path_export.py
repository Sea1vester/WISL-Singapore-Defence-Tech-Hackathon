"""Build a stable flight-path JSON for 3D visualization (Step 5 handoff)."""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any


PATH_CONTRACT_VERSION = "1.0"


def _num(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def sample_from_l1_record(record: dict[str, Any]) -> dict[str, Any] | None:
    lat = _num(record.get("lat"))
    lon = _num(record.get("lon"))
    if lat is None or lon is None:
        return None
    if abs(lat) < 1e-9 and abs(lon) < 1e-9:
        return None

    sample: dict[str, Any] = {
        "t": record.get("timestamp_utc") or record.get("t"),
        "lat": lat,
        "lon": lon,
    }
    alt = _num(record.get("alt_m", record.get("alt")))
    if alt is not None:
        sample["alt_m"] = alt

    for src, dest in (
        ("roll", "roll_deg"),
        ("pitch", "pitch_deg"),
        ("yaw", "yaw_deg"),
        ("roll_deg", "roll_deg"),
        ("pitch_deg", "pitch_deg"),
        ("yaw_deg", "yaw_deg"),
    ):
        val = _num(record.get(src))
        if val is not None and dest not in sample:
            sample[dest] = val

    batt = _num(record.get("battery_pct", record.get("percent")))
    if batt is not None:
        sample["battery_pct"] = batt
    volt = _num(record.get("battery_v", record.get("voltage_v")))
    if volt is not None:
        sample["battery_v"] = volt

    for key in ("north_m", "east_m", "up_m", "warning", "tip", "flight_mode"):
        if record.get(key) not in (None, ""):
            sample[key] = record[key]

    return sample


def sample_from_l2_record(canonical: dict[str, Any], *, recorded_at: str | None = None) -> dict[str, Any] | None:
    position = canonical.get("position") or {}
    lat = _num(position.get("lat"))
    lon = _num(position.get("lon"))
    if lat is None or lon is None:
        return None

    sample: dict[str, Any] = {
        "t": canonical.get("timestamp_utc") or recorded_at,
        "lat": lat,
        "lon": lon,
    }
    alt = _num(position.get("alt_m"))
    if alt is not None:
        sample["alt_m"] = alt

    attitude = canonical.get("attitude") or {}
    for key in ("roll_deg", "pitch_deg", "yaw_deg"):
        val = _num(attitude.get(key))
        if val is not None:
            sample[key] = val

    battery = canonical.get("battery") or {}
    pct = _num(battery.get("percent"))
    if pct is not None:
        sample["battery_pct"] = pct
    volt = _num(battery.get("voltage_v"))
    if volt is not None:
        sample["battery_v"] = volt

    sensors = canonical.get("sensors") or {}
    if isinstance(sensors, dict):
        for key in ("north_m", "east_m", "up_m", "warning", "tip", "flight_mode"):
            if sensors.get(key) not in (None, ""):
                sample[key] = sensors[key]
        extra = sensors.get("extra")
        if isinstance(extra, dict):
            for key in ("warning", "tip", "flight_mode"):
                if key not in sample and extra.get(key) not in (None, ""):
                    sample[key] = extra[key]

    return sample


def build_flight_path(
    *,
    flight_id: str,
    source: str,
    samples: list[dict[str, Any]],
    frame: str = "wgs84",
) -> dict[str, Any]:
    return {
        "contract_version": PATH_CONTRACT_VERSION,
        "flight_id": flight_id,
        "source": source,
        "frame": frame,
        "units": {
            "horizontal": "degrees_wgs84",
            "altitude": "meters",
            "attitude": "degrees",
            "battery_pct": "percent_0_100",
            "battery_v": "volts",
            "local_offset": "meters",
        },
        "count": len(samples),
        "samples": samples,
    }


def l1_payload_to_path(
    payload: dict[str, Any],
    *,
    stride: int = 1,
    max_samples: int | None = None,
) -> dict[str, Any]:
    records = payload.get("records") or []
    batch_ts = payload.get("timestamp_utc")
    samples: list[dict[str, Any]] = []
    for i, record in enumerate(records):
        if stride > 1 and i % stride != 0:
            continue
        sample = sample_from_l1_record(record)
        if sample is None:
            continue
        if not sample.get("t") and batch_ts:
            sample["t"] = batch_ts
        samples.append(sample)
        if max_samples is not None and len(samples) >= max_samples:
            break

    frame = "wgs84"
    if samples and any(k in samples[0] for k in ("north_m", "east_m", "up_m")):
        frame = "wgs84+local_ned"

    return build_flight_path(
        flight_id=str(payload.get("flight_id") or uuid.uuid4()),
        source=str(payload.get("source") or "unknown"),
        samples=samples,
        frame=frame,
    )


def path_from_l1_file(
    path: Path | str,
    *,
    stride: int = 1,
    max_samples: int | None = None,
) -> dict[str, Any]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    return l1_payload_to_path(payload, stride=stride, max_samples=max_samples)
