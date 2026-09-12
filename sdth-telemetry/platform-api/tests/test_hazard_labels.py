from datetime import datetime, timedelta, timezone

from app.detectors import DetectedIncident, detect_incidents, hazard_label


def _ts(seconds: int) -> str:
    base = datetime(2026, 7, 16, 15, 0, 0, tzinfo=timezone.utc)
    return (base + timedelta(seconds=seconds)).strftime("%Y-%m-%dT%H:%M:%SZ")


def _sample(
    seconds: int,
    *,
    lat: float = 1.3521,
    lon: float = 103.8198,
    alt_m: float = 50.0,
    flight_mode: str = "P-GPS",
    warning: str | None = None,
    roll_deg: float = 0.0,
    pitch_deg: float = 0.0,
    yaw_deg: float = 0.0,
    battery_pct: float = 80.0,
) -> dict:
    sensors: dict = {"flight_mode": flight_mode}
    if warning is not None:
        sensors["warning"] = warning
    return {
        "timestamp_utc": _ts(seconds),
        "position": {"lat": lat, "lon": lon, "alt_m": alt_m},
        "flight_mode": flight_mode,
        "sensors": sensors,
        "attitude": {"roll_deg": roll_deg, "pitch_deg": pitch_deg, "yaw_deg": yaw_deg},
        "battery": {"percent": battery_pct},
    }


def _incident(incident_type: str, *, started_at: str, summary: str = "", evidence: dict | None = None) -> DetectedIncident:
    return DetectedIncident(
        incident_type=incident_type,
        severity="warning",
        started_at=started_at,
        ended_at=started_at,
        signature=incident_type,
        summary=summary or incident_type,
        evidence=evidence or {},
    )


def test_hazard_label_jamming_from_gps_weak_warning():
    series = [_sample(i, warning="GPS signal weak. Hover with caution.") for i in range(10)]
    incident = _incident(
        "operator_warning",
        started_at=_ts(3),
        summary="GPS signal weak",
        evidence={"sample": {"warning": "GPS signal weak. Hover with caution."}},
    )
    assert hazard_label(incident, series) == "jamming"


def test_hazard_label_jamming_from_last_known_position():
    series = []
    for i in range(40):
        series.append(
            _sample(
                i,
                lat=1.3521,
                lon=103.8198,
                yaw_deg=45.0 + i * 3.0,
                roll_deg=1.0,
            )
        )
    incident = _incident(
        "last_known_position",
        started_at=_ts(10),
        evidence={"frozen_start": {"lat": 1.3521, "lon": 103.8198}, "elapsed_s": 35.0},
    )
    assert hazard_label(incident, series) == "jamming"


def test_hazard_label_compass_warning_not_jamming():
    series = [_sample(i, warning="Compass calibration required (Code: 30009).") for i in range(10)]
    incident = _incident(
        "operator_warning",
        started_at=_ts(2),
        summary="Compass calibration required",
        evidence={"sample": {"warning": "Compass calibration required (Code: 30009)."}},
    )
    assert hazard_label(incident, series) is None


def test_hazard_label_telemetry_gap_not_jamming():
    series = [
        _sample(0),
        _sample(20),
        _sample(21),
    ]
    incident = _incident(
        "telemetry_gap",
        started_at=_ts(0),
        evidence={"dt_s": 20.0},
    )
    assert hazard_label(incident, series) is None


def test_hazard_label_mechanical_failure_recovered_landing():
    series = [_sample(i) for i in range(6)]
    series.append(_sample(6, roll_deg=75.0, pitch_deg=10.0))
    series.append(_sample(7, alt_m=5.0, roll_deg=8.0, pitch_deg=2.0))
    series.append(
        _sample(
            8,
            alt_m=0.0,
            flight_mode="LAND",
            roll_deg=2.0,
            pitch_deg=1.0,
        )
    )
    incident = _incident(
        "attitude_shock",
        started_at=_ts(6),
        summary="Attitude 75.0 deg (roll/pitch crash band).",
        evidence={"sample": {"timestamp_utc": _ts(6), "attitude": {"roll_deg": 75.0, "pitch_deg": 10.0}}},
    )
    assert hazard_label(incident, series) == "mechanical_failure"


def test_hazard_label_kinetic_loss_from_mission_incomplete():
    series = [_sample(i, lat=1.3521 + i * 0.00001) for i in range(10)]
    incident = _incident(
        "mission_incomplete",
        started_at=_ts(9),
        evidence={"last_known_position": {"lat": 1.3521 + 9 * 0.00001, "lon": 103.8198, "alt_m": 50.0}},
    )
    assert hazard_label(incident, series) == "kinetic_loss"


def test_hazard_label_healthy_landing_no_kinetic_loss():
    series = [_sample(i) for i in range(5)]
    series.append(
        _sample(
            5,
            alt_m=0.0,
            flight_mode="LAND",
            battery_pct=72.0,
        )
    )
    incidents = detect_incidents(series)
    labels = [hazard_label(inc, series, incidents) for inc in incidents]
    assert "kinetic_loss" not in labels
