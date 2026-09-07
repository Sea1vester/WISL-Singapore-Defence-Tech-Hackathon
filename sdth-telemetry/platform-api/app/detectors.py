"""Rule-based incident detectors.

Rules are physics/ops thresholds on L2 canonical JSON, not vendor opcodes.

Why these numbers:
- Battery 20% / 10%: DJI, PX4, and ArduPilot all treat ~20% as low and ~10% as
  failsafe/RTH. Cruise drain is a few percent per minute at most, not 15 points
  in a minute.
- Altitude 25 m step / 20 m/s vertical: DJI max climb is ~6 m/s; a 25 m jump
  between 1 Hz samples is a spike or drop, not flight.
- Ground speed 120 m/s (air) / 15 m/s (UGV): a DJI multirotor or PX4/ArduPilot FPV
  build cruises well under 30 m/s. 120 m/s implied between samples is a GPS jump.
  A ground rig cannot do 15 m/s.
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
UXO_FROZEN_POSITION_S = 30.0
AIRBORNE_MODES = ("P-GPS", "ATTI", "LOITER", "ALTHOLD", "RTL", "SMART_RTH", "POSITION", "GUIDED", "AUTO", "ORBIT", "LAND", "FBWA", "FLIP", "ACRO", "STABILIZE", "SPORT", "MOVIE", "CINE", "TRIP")
LAND_MODES = ("LAND", "AUTO_LAND", "LANDING", "RTH_LAND")

UXO_INCIDENT_TYPES = {"mission_incomplete", "last_known_position", "operator_marked_debris"}

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


def parse_timestamp(value: str | None) -> datetime | None:
    if not value:
        return None
    text = value.replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None


def _dt_seconds(prev: dict[str, Any], curr: dict[str, Any], fallback: float = 1.0) -> float:
    a = parse_timestamp(prev.get("timestamp_utc"))
    b = parse_timestamp(curr.get("timestamp_utc"))
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
        last_end = parse_timestamp(last.ended_at) or parse_timestamp(last.started_at)
        next_start = parse_timestamp(item.started_at)
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


def _is_airborne(flight_mode: str | None) -> bool:
    if not flight_mode:
        return False
    upper = flight_mode.upper().strip()
    if upper in LAND_MODES:
        return False
    return upper in AIRBORNE_MODES or upper not in {"GROUNDED", "ON_GROUND", "DISARMED"}


def _velocity_from_series(series: list[dict[str, Any]], i: int) -> float:
    if i < 1:
        return 0.0
    prev = series[i - 1]
    curr = series[i]
    dt = _dt_seconds(prev, curr, fallback=1.0)
    if dt <= 0:
        return 0.0
    prev_pos = prev.get("position") or {}
    curr_pos = curr.get("position") or {}
    lat1, lon1 = _num(prev_pos.get("lat")), _num(prev_pos.get("lon"))
    lat2, lon2 = _num(curr_pos.get("lat")), _num(curr_pos.get("lon"))
    if None not in (lat1, lon1, lat2, lon2):
        return _haversine_m(lat1, lon1, lat2, lon2) / dt
    n1, e1 = _num(prev.get("sensors") or {}).get("north_m"), _num(prev.get("sensors") or {}).get("east_m")
    n2, e2 = _num((curr.get("sensors") or {})).get("north_m"), _num((curr.get("sensors") or {})).get("east_m")
    if None not in (n1, e1, n2, e2):
        return math.hypot(n2 - n1, e2 - e1) / dt
    return 0.0


def _imu_indicates_motion(series: list[dict[str, Any]], i: int) -> bool:
    """Heuristic: yaw or attitude is actively changing, suggesting IMU detects motion."""
    if i < 1:
        return False
    prev = series[i - 1]
    curr = series[i]
    attitude_prev = prev.get("attitude")
    attitude_curr = curr.get("attitude")
    if not isinstance(attitude_prev, dict):
        attitude_prev = {}
    if not isinstance(attitude_curr, dict):
        attitude_curr = {}
    yaw_prev = _num(attitude_prev.get("yaw_deg")) if attitude_prev else None
    yaw_curr = _num(attitude_curr.get("yaw_deg")) if attitude_curr else None
    roll_prev = _num(attitude_prev.get("roll_deg")) if attitude_prev else None
    roll_curr = _num(attitude_curr.get("roll_deg")) if attitude_curr else None
    if yaw_prev is not None and yaw_curr is not None and abs(yaw_curr - yaw_prev) > 2.0:
        return True
    if roll_prev is not None and roll_curr is not None and abs(roll_curr - roll_prev) > 2.0:
        return True
    return False


def _position_changed(pos1: dict[str, Any], pos2: dict[str, Any], threshold_m: float = 0.5) -> bool:
    lat1, lon1 = _num(pos1.get("lat")), _num(pos1.get("lon"))
    lat2, lon2 = _num(pos2.get("lat")), _num(pos2.get("lon"))
    if None in (lat1, lon1, lat2, lon2):
        return False
    return _haversine_m(lat1, lon1, lat2, lon2) > threshold_m


def _detect_mission_incomplete(series: list[dict[str, Any]]) -> list[DetectedIncident]:
    if not series:
        return []
    found: list[DetectedIncident] = []
    last_sample = series[-1]
    last_position = last_sample.get("position") or {}
    flight_mode = last_sample.get("flight_mode") or last_sample.get("sensors", {}).get("flight_mode")
    airborne = _is_airborne(str(flight_mode) if flight_mode else None)

    has_landing = False
    for sample in reversed(series):
        fm = sample.get("flight_mode") or sample.get("sensors", {}).get("flight_mode")
        if _is_airborne(str(fm) if fm else None):
            landing_fm = (fm or "").upper().strip() in LAND_MODES
            if landing_fm:
                has_landing = True
                break
        elif fm is None and not has_landing:
            continue
        else:
            break

    if airborne and not has_landing:
        lat = _num(last_position.get("lat"))
        lon = _num(last_position.get("lon"))
        alt = _num(last_position.get("alt_m"))
        ts = last_sample.get("timestamp_utc") or ""
        incident = DetectedIncident(
            incident_type="mission_incomplete",
            severity="critical",
            started_at=series[0].get("timestamp_utc", ts),
            ended_at=ts,
            signature="mission_incomplete",
            summary="Telemetry stopped while airborne; no landing record found. Possible UXO at last-known position.",
            evidence={
                "sample": {
                    "timestamp_utc": ts,
                    "flight_mode": flight_mode,
                    "position": {"lat": lat, "lon": lon, "alt_m": alt},
                },
                "limitations": "warhead state unknown, treat as potential UXO, do not approach",
            },
        )
        if None not in (lat, lon):
            incident.evidence["last_known_position"] = {"lat": lat, "lon": lon, "alt_m": alt}
        found.append(incident)
    return found


def _detect_last_known_position(series: list[dict[str, Any]]) -> list[DetectedIncident]:
    if len(series) < 3:
        return []
    found: list[DetectedIncident] = []
    frozen_start_idx: int | None = None
    frozen_start_ts: str = ""
    position = series[0].get("position") or {}
    prev_lat = _num(position.get("lat"))
    prev_lon = _num(position.get("lon"))

    for i in range(1, len(series)):
        curr = series[i]
        curr_pos = curr.get("position") or {}
        curr_lat = _num(curr_pos.get("lat"))
        curr_lon = _num(curr_pos.get("lon"))
        ts = curr.get("timestamp_utc") or ""
        vel = _velocity_from_series(series, i)
        imu_moving = _imu_indicates_motion(series, i)
        effective_vel = max(vel, 0.5) if imu_moving else vel

        if frozen_start_idx is not None:
            elapsed = (parse_timestamp(ts) - parse_timestamp(frozen_start_ts)).total_seconds() if (parse_timestamp(ts) and parse_timestamp(frozen_start_ts)) else 0
            if elapsed > UXO_FROZEN_POSITION_S and (effective_vel > 0.5 or imu_moving):
                incident = DetectedIncident(
                    incident_type="last_known_position",
                    severity="critical",
                    started_at=frozen_start_ts,
                    ended_at=ts,
                    signature="last_known_position",
                    summary=f"Position frozen for {elapsed:.0f}s while IMU indicated motion. Possible mid-air failure at last-known fix.",
                    evidence={
                        "frozen_start": {"timestamp_utc": frozen_start_ts, "lat": prev_lat, "lon": prev_lon},
                        "frozen_end": {"timestamp_utc": ts, "lat": curr_lat, "lon": curr_lon},
                        "elapsed_s": elapsed,
                        "velocity_at_freeze": vel,
                        "limitations": "warhead state unknown, treat as potential UXO, do not approach",
                    },
                )
                found.append(incident)
                frozen_start_idx = None
        else:
            pos_changed = _position_changed({"lat": prev_lat, "lon": prev_lon}, {"lat": curr_lat, "lon": curr_lon})
            if not pos_changed and (vel > 0.5 or imu_moving):
                frozen_start_idx = i
                frozen_start_ts = ts
            else:
                prev_lat = curr_lat
                prev_lon = curr_lon

    return found


def _detect_operator_marked(series: list[dict[str, Any]], user_markers: list[dict[str, Any]] | None = None) -> list[DetectedIncident]:
    if not user_markers:
        return []
    found: list[DetectedIncident] = []
    for marker in user_markers:
        incident = DetectedIncident(
            incident_type="operator_marked_debris",
            severity="warning",
            started_at=marker.get("timestamp_utc", ""),
            ended_at=marker.get("timestamp_utc", ""),
            signature="operator_marked_debris",
            summary=f"Operator marked debris at ({marker.get('lat')}, {marker.get('lon')}) alt={marker.get('alt_m', 0)} m.",
            evidence={
                "marker": marker,
                "limitations": "warhead state unknown, treat as potential UXO, do not approach",
            },
        )
        found.append(incident)
    return found


def detect_incidents(series: list[dict[str, Any]], user_markers: list[dict[str, Any]] | None = None) -> list[DetectedIncident]:
    found: list[DetectedIncident] = []
    if not series:
        rule_c = _detect_operator_marked(series, user_markers)
        found.extend(rule_c)
        return found

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
            window_start = parse_timestamp(sample.get("timestamp_utc"))
            if window_start:
                peak = prev_pct
                for older in reversed(series[: i + 1]):
                    older_ts = parse_timestamp(older.get("timestamp_utc"))
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

    rule_a = _detect_mission_incomplete(series)
    rule_b = _detect_last_known_position(series)
    rule_c = _detect_operator_marked(series, user_markers)
    found.extend(rule_a)
    found.extend(rule_b)
    found.extend(rule_c)

    return _merge(found)
