"""Rule-based incident detectors.

Rules are physics/ops thresholds on L2 canonical JSON, not vendor opcodes.

Why these numbers:
- Battery 20% / 10%: DJI, PX4, and ArduPilot all treat ~20% as low and ~10% as
  failsafe/RTH. Cruise drain is a few percent per minute at most, not 15 points
  in a minute.
- Altitude 25 m step / 20 m/s vertical: DJI max climb is ~6 m/s; a 25 m jump
  between 1 Hz samples is a spike or drop, not flight.
- Ground speed 120 m/s (air) / 15 m/s (UGV): Hermes 900 cruise is ~60 m/s.
  120 m/s implied between samples is a GPS jump. Taurus UGV cannot do 15 m/s.
- Attitude 40 deg / 70 deg: level flight stays well under 30 deg roll/pitch.
  70 deg is tumble/crash territory.
- Gap 15 s: 1 Hz streams that go silent that long are a dropout, not jitter.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from app.brands import identify_brand
from app.path_export import _num

BATTERY_LOW_PCT = 20.0
BATTERY_CRITICAL_PCT = 10.0
BATTERY_PLUNGE_PCT = 15.0
BATTERY_PLUNGE_WINDOW_S = 60.0
ALT_JUMP_M = 25.0
ALT_RATE_MPS = 20.0
GPS_JUMP_MPS_AIR = 120.0
GPS_JUMP_MPS_GROUND = 15.0
ATTITUDE_WARN_DEG = 40.0
ATTITUDE_CRIT_DEG = 70.0
GAP_S = 15.0
MERGE_GAP_S = 5.0
EARTH_RADIUS_M = 6_371_000.0

WARNING_KEYWORDS = (
    "gps",
    "failsafe",
    "motor",
    "compass",
    "battery",
    "rtl",
    "go home",
    "link",
    "lost",
    "error",
    "weak",
)


@dataclass
class DetectedIncident:
    incident_type: str
    severity: str
    started_at: str
    ended_at: str
    signature: str
    summary: str
    evidence: dict[str, Any] = field(default_factory=dict)


def _parse_ts(value: str | None) -> datetime | None:
    if not value:
        return None
    text = value.replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None


def _dt_seconds(prev: dict[str, Any], curr: dict[str, Any], fallback: float = 1.0) -> float:
    a = _parse_ts(prev.get("timestamp_utc"))
    b = _parse_ts(curr.get("timestamp_utc"))
    if a and b:
        delta = (b - a).total_seconds()
        if delta > 0:
            return delta
    return fallback


def _haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lon2 - lon1)
    h = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2) ** 2
    return 2 * EARTH_RADIUS_M * math.asin(min(1.0, math.sqrt(h)))


def _severity_rank(value: str) -> int:
    return {"info": 0, "warning": 1, "critical": 2}.get(value, 0)


def _merge(incidents: list[DetectedIncident]) -> list[DetectedIncident]:
    if not incidents:
        return []
    ordered = sorted(incidents, key=lambda item: (item.incident_type, item.started_at))
    merged: list[DetectedIncident] = []
    for item in ordered:
        if not merged:
            merged.append(item)
            continue
        last = merged[-1]
        if last.incident_type != item.incident_type:
            merged.append(item)
            continue
        last_end = _parse_ts(last.ended_at) or _parse_ts(last.started_at)
        next_start = _parse_ts(item.started_at)
        if last_end and next_start and (next_start - last_end).total_seconds() <= MERGE_GAP_S:
            last.ended_at = item.ended_at
            if _severity_rank(item.severity) > _severity_rank(last.severity):
                last.severity = item.severity
                last.summary = item.summary
            last.evidence.setdefault("samples", [])
            if "sample" in item.evidence:
                last.evidence["samples"].append(item.evidence["sample"])
            continue
        merged.append(item)
    return merged


def _speed_limit_mps(series: list[dict[str, Any]]) -> float:
    brand = identify_brand(series[0] if series else {}, source=(series[0].get("metadata") or {}).get("source") if series else None)
    if brand.family == "ugv":
        return GPS_JUMP_MPS_GROUND
    return GPS_JUMP_MPS_AIR


def _warning_text(sample: dict[str, Any]) -> str:
    sensors = sample.get("sensors") or {}
    extra = sensors.get("extra") if isinstance(sensors.get("extra"), dict) else {}
    parts = [
        sensors.get("warning"),
        sensors.get("tip"),
        extra.get("warning"),
        extra.get("tip"),
    ]
    return " ".join(str(part) for part in parts if part).strip()


def detect_incidents(series: list[dict[str, Any]]) -> list[DetectedIncident]:
    if not series:
        return []

    found: list[DetectedIncident] = []
    speed_limit = _speed_limit_mps(series)

    for i, sample in enumerate(series):
        ts = sample.get("timestamp_utc") or ""
        battery = sample.get("battery") or {}
        percent = _num(battery.get("percent"))
        attitude = sample.get("attitude") or {}
        roll = abs(_num(attitude.get("roll_deg")) or 0.0)
        pitch = abs(_num(attitude.get("pitch_deg")) or 0.0)
        position = sample.get("position") or {}

        if percent is not None and percent > 0 and percent <= BATTERY_CRITICAL_PCT:
            found.append(
                DetectedIncident(
                    incident_type="battery_critical",
                    severity="critical",
                    started_at=ts,
                    ended_at=ts,
                    signature="battery_critical",
                    summary=f"Battery at {percent:.1f}% (failsafe band).",
                    evidence={"sample": {"timestamp_utc": ts, "battery": battery}},
                )
            )
        elif percent is not None and percent > 0 and percent <= BATTERY_LOW_PCT:
            found.append(
                DetectedIncident(
                    incident_type="battery_low",
                    severity="warning",
                    started_at=ts,
                    ended_at=ts,
                    signature="battery_low",
                    summary=f"Battery at {percent:.1f}% (low-battery band).",
                    evidence={"sample": {"timestamp_utc": ts, "battery": battery}},
                )
            )

        max_tilt = max(roll, pitch)
        if max_tilt >= ATTITUDE_CRIT_DEG:
            found.append(
                DetectedIncident(
                    incident_type="attitude_shock",
                    severity="critical",
                    started_at=ts,
                    ended_at=ts,
                    signature="attitude_shock",
                    summary=f"Attitude {max_tilt:.1f} deg (roll/pitch crash band).",
                    evidence={"sample": {"timestamp_utc": ts, "attitude": attitude}},
                )
            )
        elif max_tilt >= ATTITUDE_WARN_DEG:
            found.append(
                DetectedIncident(
                    incident_type="attitude_shock",
                    severity="warning",
                    started_at=ts,
                    ended_at=ts,
                    signature="attitude_shock",
                    summary=f"Attitude {max_tilt:.1f} deg exceeds level-flight envelope.",
                    evidence={"sample": {"timestamp_utc": ts, "attitude": attitude}},
                )
            )

        warning = _warning_text(sample)
        sensors = sample.get("sensors") or {}
        extra = sensors.get("extra") if isinstance(sensors.get("extra"), dict) else {}
        explicit_warning = sensors.get("warning") or extra.get("warning")
        if explicit_warning or (
            warning and any(keyword in warning.lower() for keyword in WARNING_KEYWORDS)
        ):
            found.append(
                DetectedIncident(
                    incident_type="operator_warning",
                    severity="warning",
                    started_at=ts,
                    ended_at=ts,
                    signature="operator_warning",
                    summary=f"Normalized warning: {warning}",
                    evidence={"sample": {"timestamp_utc": ts, "warning": warning}},
                )
            )

        if i == 0:
            continue
        prev = series[i - 1]
        dt = _dt_seconds(prev, sample)
        prev_pos = prev.get("position") or {}

        if dt >= GAP_S:
            found.append(
                DetectedIncident(
                    incident_type="telemetry_gap",
                    severity="warning",
                    started_at=prev.get("timestamp_utc") or ts,
                    ended_at=ts,
                    signature="telemetry_gap",
                    summary=f"Telemetry dropped for {dt:.1f}s.",
                    evidence={"dt_s": dt},
                )
            )

        prev_alt = _num(prev_pos.get("alt_m"))
        curr_alt = _num(position.get("alt_m"))
        if prev_alt is not None and curr_alt is not None:
            d_alt = abs(curr_alt - prev_alt)
            rate = d_alt / dt if dt else d_alt
            if d_alt >= ALT_JUMP_M or rate >= ALT_RATE_MPS:
                found.append(
                    DetectedIncident(
                        incident_type="altitude_spike",
                        severity="critical" if d_alt >= ALT_JUMP_M * 2 else "warning",
                        started_at=prev.get("timestamp_utc") or ts,
                        ended_at=ts,
                        signature="altitude_spike",
                        summary=f"Altitude jumped {d_alt:.1f} m ({rate:.1f} m/s).",
                        evidence={"d_alt_m": d_alt, "rate_mps": rate},
                    )
                )

        lat1, lon1 = _num(prev_pos.get("lat")), _num(prev_pos.get("lon"))
        lat2, lon2 = _num(position.get("lat")), _num(position.get("lon"))
        sensors = sample.get("sensors") or {}
        prev_sensors = prev.get("sensors") or {}
        if None not in (lat1, lon1, lat2, lon2) and not (lat1 == 0 and lon1 == 0 and lat2 == 0 and lon2 == 0):
            dist = _haversine_m(lat1, lon1, lat2, lon2)
            speed = dist / dt if dt else dist
            if speed >= speed_limit:
                found.append(
                    DetectedIncident(
                        incident_type="gps_jump",
                        severity="critical",
                        started_at=prev.get("timestamp_utc") or ts,
                        ended_at=ts,
                        signature="gps_jump",
                        summary=f"Position jumped {dist:.1f} m ({speed:.1f} m/s).",
                        evidence={"distance_m": dist, "speed_mps": speed, "limit_mps": speed_limit},
                    )
                )
        else:
            n1, e1 = _num(prev_sensors.get("north_m")), _num(prev_sensors.get("east_m"))
            n2, e2 = _num(sensors.get("north_m")), _num(sensors.get("east_m"))
            if None not in (n1, e1, n2, e2):
                dist = math.hypot(n2 - n1, e2 - e1)
                speed = dist / dt if dt else dist
                if speed >= speed_limit:
                    found.append(
                        DetectedIncident(
                            incident_type="gps_jump",
                            severity="critical",
                            started_at=prev.get("timestamp_utc") or ts,
                            ended_at=ts,
                            signature="gps_jump",
                            summary=f"Local position jumped {dist:.1f} m ({speed:.1f} m/s).",
                            evidence={"distance_m": dist, "speed_mps": speed, "limit_mps": speed_limit, "frame": "local"},
                        )
                    )

        prev_pct = _num((prev.get("battery") or {}).get("percent"))
        if percent is not None and prev_pct is not None and percent > 0 and prev_pct > 0:
            window_start = _parse_ts(sample.get("timestamp_utc"))
            if window_start:
                peak = prev_pct
                for older in reversed(series[: i + 1]):
                    older_ts = _parse_ts(older.get("timestamp_utc"))
                    older_pct = _num((older.get("battery") or {}).get("percent"))
                    if older_ts and (window_start - older_ts).total_seconds() > BATTERY_PLUNGE_WINDOW_S:
                        break
                    if older_pct is not None:
                        peak = max(peak, older_pct)
                drop = peak - percent
                if drop >= BATTERY_PLUNGE_PCT:
                    found.append(
                        DetectedIncident(
                            incident_type="battery_plunge",
                            severity="critical",
                            started_at=ts,
                            ended_at=ts,
                            signature="battery_plunge",
                            summary=f"Battery fell {drop:.1f} points within {BATTERY_PLUNGE_WINDOW_S:.0f}s.",
                            evidence={"drop_pct": drop, "percent": percent, "peak_pct": peak},
                        )
                    )

    return _merge(found)
