from app.canonical_series import series_from_l1_payload
from app.detectors import (
    UXO_INCIDENT_TYPES,
    _detect_last_known_position,
    _detect_mission_incomplete,
    _detect_operator_marked,
    detect_incidents,
    _is_airborne,
)
from tests.hardware_l1 import ardupilot_l1, dji_l1, px4_l1


def test_uxo_incident_types_set():
    assert UXO_INCIDENT_TYPES == {"mission_incomplete", "last_known_position", "operator_marked_debris"}


def test_uxo_incidents_have_limitations_text():
    from datetime import datetime, timedelta, timezone

    ts_base = datetime(2026, 7, 16, 15, 0, 0, tzinfo=timezone.utc)
    series = []
    for i in range(10):
        series.append(
            {
                "timestamp_utc": (ts_base + timedelta(seconds=i)).strftime(
                    "%Y-%m-%dT%H:%M:%SZ"
                ),
                "position": {
                    "lat": 1.3521 + i * 0.00001,
                    "lon": 103.8198,
                    "alt_m": 50.0,
                },
                "flight_mode": "P-GPS",
                "sensors": {"flight_mode": "P-GPS"},
                "battery": {"percent": 80 - i},
            }
        )
    incidents = detect_incidents(series)
    uxos = [i for i in incidents if i.incident_type in UXO_INCIDENT_TYPES]
    assert len(uxos) >= 1
    for inc in uxos:
        assert (
            inc.evidence.get("limitations")
            == "warhead state unknown, treat as potential UXO, do not approach"
        )


def test_rule_a_produces_geolocated_incident():
    from datetime import datetime, timedelta, timezone

    ts_base = datetime(2026, 7, 16, 15, 0, 0, tzinfo=timezone.utc)
    series = []
    for i in range(10):
        series.append(
            {
                "timestamp_utc": (ts_base + timedelta(seconds=i)).strftime(
                    "%Y-%m-%dT%H:%M:%SZ"
                ),
                "position": {
                    "lat": 1.3521 + i * 0.00001,
                    "lon": 103.8198 + i * 0.00002,
                    "alt_m": 50.0 + i,
                },
                "flight_mode": "P-GPS",
                "sensors": {"flight_mode": "P-GPS"},
                "battery": {"percent": 80 - i},
            }
        )
    results = _detect_mission_incomplete(series)
    assert len(results) == 1
    inc = results[0]
    assert inc.incident_type == "mission_incomplete"
    assert inc.evidence.get("last_known_position") is not None
    assert inc.evidence["last_known_position"]["lat"] == 1.3521 + 9 * 0.00001
    assert inc.evidence["last_known_position"]["lon"] == 103.8198 + 9 * 0.00002
    assert inc.evidence["last_known_position"]["alt_m"] == 59.0
    assert (
        inc.evidence["sample"]["timestamp_utc"]
        == (ts_base + timedelta(seconds=9)).strftime("%Y-%m-%dT%H:%M:%SZ")
    )


def test_rule_b_produces_geolocated_incident():
    from datetime import datetime, timedelta, timezone

    ts_base = datetime(2026, 7, 16, 15, 0, 0, tzinfo=timezone.utc)
    series = []
    for i in range(40):
        series.append(
            {
                "timestamp_utc": (ts_base + timedelta(seconds=i)).strftime(
                    "%Y-%m-%dT%H:%M:%SZ"
                ),
                "position": {"lat": 1.3521, "lon": 103.8198, "alt_m": 0.0 if i < 5 else 50.0},
                "sensors": {},
                "attitude": {
                    "yaw_deg": 45.0 + i * 3.0,
                    "roll_deg": 1.0,
                    "pitch_deg": 0.5,
                },
                "battery": {"percent": 80},
            }
        )
    results = _detect_last_known_position(series)
    assert len(results) >= 1
    inc = results[0]
    assert inc.incident_type == "last_known_position"
    assert inc.evidence.get("frozen_start") is not None
    assert inc.evidence["frozen_start"]["lat"] == 1.3521
    assert inc.evidence["frozen_start"]["lon"] == 103.8198
    assert inc.evidence.get("frozen_end") is not None
    assert inc.evidence.get("elapsed_s", 0) > 30


def test_rule_c_produces_geolocated_incident():
    markers = [
        {
            "lat": 1.3600,
            "lon": 103.8200,
            "alt_m": 12.5,
            "timestamp_utc": "2026-07-16T15:30:00Z",
            "note": "visual confirmation",
        },
        {
            "lat": 1.3700,
            "lon": 103.8300,
            "alt_m": 0.0,
            "timestamp_utc": "2026-07-16T15:35:00Z",
            "note": "second marker",
        },
    ]
    results = _detect_operator_marked([], user_markers=markers)
    assert len(results) == 2
    for inc in results:
        assert inc.incident_type == "operator_marked_debris"
        assert inc.severity == "warning"
        assert (
            inc.evidence.get("limitations")
            == "warhead state unknown, treat as potential UXO, do not approach"
        )
    assert "1.36" in results[0].summary
    assert "1.37" in results[1].summary


def test_combined_rules_produce_all_three_uxo_types():
    from datetime import datetime, timedelta, timezone

    ts_base = datetime(2026, 7, 16, 15, 0, 0, tzinfo=timezone.utc)
    series = []
    for i in range(10):
        series.append(
            {
                "timestamp_utc": (ts_base + timedelta(seconds=i)).strftime(
                    "%Y-%m-%dT%H:%M:%SZ"
                ),
                "position": {
                    "lat": 1.3521 + i * 0.00001,
                    "lon": 103.8198,
                    "alt_m": 50.0,
                },
                "flight_mode": "P-GPS",
                "sensors": {"flight_mode": "P-GPS"},
                "battery": {"percent": 80 - i},
            }
        )
    markers = [
        {
            "lat": 1.3600,
            "lon": 103.8200,
            "alt_m": 0.0,
            "timestamp_utc": "2026-07-16T15:00:15Z",
            "note": "operator debris pin",
        }
    ]
    all_incidents = detect_incidents(series, user_markers=markers)
    types = {inc.incident_type for inc in all_incidents}
    assert "mission_incomplete" in types
    assert "operator_marked_debris" in types


def test_all_uxo_incidents_have_timestamp_and_position():
    markers = [
        {
            "lat": 1.3600,
            "lon": 103.8200,
            "alt_m": 15.0,
            "timestamp_utc": "2026-07-16T16:00:00Z",
        }
    ]
    incidents = detect_incidents([], user_markers=markers)
    for inc in incidents:
        if inc.incident_type in UXO_INCIDENT_TYPES:
            assert inc.started_at
            marker = inc.evidence.get("marker", {})
            assert marker.get("lat") == 1.3600
            assert marker.get("lon") == 103.8200
            assert marker.get("alt_m") == 15.0
            assert marker.get("timestamp_utc") == "2026-07-16T16:00:00Z"


def test_operator_warning_not_in_uxo_types():
    types = _types(dji_l1(inject="warning"))
    assert "operator_warning" not in UXO_INCIDENT_TYPES


def _types(payload) -> set[str]:
    series = series_from_l1_payload(payload)
    return {item.incident_type for item in detect_incidents(series)}


def test_battery_low_and_warning_on_dji_series():
    types = _types(dji_l1(inject="battery_low"))
    assert "battery_low" in types or "battery_critical" in types


def test_operator_warning_from_normalized_warning_field():
    types = _types(dji_l1(inject="warning"))
    assert "operator_warning" in types


def _battery_series(samples):
    """Make minimal, timestamped L2 samples for battery-window rule tests."""
    return [
        {
            "timestamp_utc": timestamp,
            "position": {"lat": 51.0, "lon": -1.0, "alt_m": 20.0},
            "attitude": {"roll_deg": 0.0, "pitch_deg": 0.0, "yaw_deg": 0.0},
            "battery": {"percent": percent},
            "sensors": {"flight_mode": "LAND"},
        }
        for timestamp, percent in samples
    ]


def _battery_plunge_count(series) -> int:
    return sum(item.incident_type == "battery_plunge" for item in detect_incidents(series))


def test_battery_plunge_window_includes_exactly_sixty_seconds():
    assert _battery_plunge_count(
        _battery_series([("2026-01-01T00:00:00Z", 100.0), ("2026-01-01T00:00:59Z", 84.0)])
    ) == 1
    assert _battery_plunge_count(
        _battery_series([("2026-01-01T00:00:00Z", 100.0), ("2026-01-01T00:01:00Z", 84.0)])
    ) == 1


def test_battery_plunge_excludes_stale_peak_after_window():
    # This is an intentional soundness correction. The prior reverse scan seeded
    # its peak from the previous sample and could report a plunge across a gap.
    assert _battery_plunge_count(
        _battery_series([("2026-01-01T00:00:00Z", 100.0), ("2026-01-01T00:01:01Z", 84.0)])
    ) == 0
    assert _battery_plunge_count(
        _battery_series([("2026-01-01T00:00:00Z", 100.0), ("2026-01-01T01:00:00Z", 80.0)])
    ) == 0


def test_battery_plunge_window_handles_missing_and_out_of_order_values():
    # A missing intervening percentage cannot support a plunge conclusion.
    assert _battery_plunge_count(
        _battery_series(
            [
                ("2026-01-01T00:00:00Z", 100.0),
                ("2026-01-01T00:00:10Z", 0.0),
                ("2026-01-01T00:00:20Z", 84.0),
            ]
        )
    ) == 0
    # Non-monotonic clocks retain the bounded reference-path behavior rather
    # than applying the monotonic deque to an invalid time sequence.
    assert _battery_plunge_count(
        _battery_series([("2026-01-01T00:00:10Z", 100.0), ("2026-01-01T00:00:00Z", 84.0)])
    ) == 1


def test_battery_plunge_on_px4_series():
    assert "battery_plunge" in _types(px4_l1(inject="battery_plunge"))


def test_attitude_shock_on_ardupilot_crash_attitude():
    assert "attitude_shock" in _types(ardupilot_l1(inject="attitude"))


def test_healthy_dji_has_no_rules_without_injection():
    types = _types(dji_l1(inject=None))
    assert types == set()


def test_mission_incomplete_rule_a():
    from app.detectors import _detect_mission_incomplete
    from datetime import datetime, timedelta, timezone

    ts_base = datetime(2026, 7, 16, 15, 0, 0, tzinfo=timezone.utc)
    series = []
    for i in range(10):
        series.append({
            "timestamp_utc": (ts_base + timedelta(seconds=i)).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "position": {"lat": 1.3521 + i * 0.00001, "lon": 103.8198, "alt_m": 50.0},
            "flight_mode": "P-GPS",
            "sensors": {"flight_mode": "P-GPS"},
            "battery": {"percent": 80 - i},
        })
    results = _detect_mission_incomplete(series)
    assert len(results) == 1
    assert results[0].incident_type == "mission_incomplete"
    assert results[0].severity == "critical"
    assert results[0].evidence.get("limitations") == "warhead state unknown, treat as potential UXO, do not approach"
    assert results[0].evidence["last_known_position"]["lat"] == 1.3521 + 9 * 0.00001


def test_mission_incomplete_no_false_positive_on_landing():
    from app.detectors import _detect_mission_incomplete

    series = [
        {"timestamp_utc": f"2026-07-16T15:00:{i:02d}Z", "flight_mode": "P-GPS", "sensors": {},
         "position": {"lat": 1.3521, "lon": 103.8198, "alt_m": 50.0}}
        for i in range(5)
    ]
    series.append({
        "timestamp_utc": "2026-07-16T15:00:05Z",
        "flight_mode": "LAND",
        "sensors": {"flight_mode": "LAND"},
        "position": {"lat": 1.3521, "lon": 103.8198, "alt_m": 0.0},
    })
    results = _detect_mission_incomplete(series)
    assert len(results) == 0


def test_last_known_position_rule_b():
    from app.detectors import _detect_last_known_position
    from datetime import datetime, timedelta, timezone

    ts_base = datetime(2026, 7, 16, 15, 0, 0, tzinfo=timezone.utc)
    series = []
    for i in range(40):
        series.append({
            "timestamp_utc": (ts_base + timedelta(seconds=i)).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "position": {"lat": 1.3521, "lon": 103.8198, "alt_m": 0.0 if i < 5 else 50.0},
            "sensors": {},
            "attitude": {"yaw_deg": 45.0 + i * 3.0, "roll_deg": 1.0, "pitch_deg": 0.5},
            "battery": {"percent": 80},
        })
    results = _detect_last_known_position(series)
    assert len(results) >= 1
    assert any(r.incident_type == "last_known_position" for r in results)
    assert results[0].evidence.get("limitations") == "warhead state unknown, treat as potential UXO, do not approach"


def test_last_known_position_no_false_positive_when_moving():
    from app.detectors import _detect_last_known_position

    series = [
        {
            "timestamp_utc": f"2026-07-16T15:00:{i:02d}Z",
            "position": {"lat": 1.3521 + i * 0.0001, "lon": 103.8198 + i * 0.0001, "alt_m": 50.0},
            "sensors": {},
            "battery": {"percent": 80},
        }
        for i in range(5)
    ]
    results = _detect_last_known_position(series)
    assert all(r.incident_type != "last_known_position" for r in results)


def test_operator_marked_debris_rule_c():
    from app.detectors import _detect_operator_marked

    markers = [
        {
            "lat": 1.3600,
            "lon": 103.8200,
            "alt_m": 0.0,
            "timestamp_utc": "2026-07-16T15:30:00Z",
            "note": "visual confirmation of downed drone",
        },
    ]
    results = _detect_operator_marked([], user_markers=markers)
    assert len(results) == 1
    assert results[0].incident_type == "operator_marked_debris"
    assert results[0].severity == "warning"
    assert "1.36" in results[0].summary
    assert results[0].evidence.get("limitations") == "warhead state unknown, treat as potential UXO, do not approach"


def test_operator_marked_debris_empty_markers():
    from app.detectors import _detect_operator_marked
    results = _detect_operator_marked([], user_markers=None)
    assert len(results) == 0


def test_mission_incomplete_detected_via_full_detector():
    from datetime import datetime, timedelta, timezone
    from app.detectors import _detect_mission_incomplete

    ts_base = datetime(2026, 7, 16, 15, 0, 0, tzinfo=timezone.utc)
    series = []
    for i in range(5):
        series.append({
            "timestamp_utc": (ts_base + timedelta(seconds=i)).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "position": {"lat": 1.3521, "lon": 103.8198, "alt_m": 50.0},
            "flight_mode": "P-GPS",
            "sensors": {"flight_mode": "P-GPS"},
            "battery": {"percent": 95 - i * 2},
        })
    all_incidents = detect_incidents(series)
    types = {inc.incident_type for inc in all_incidents}
    assert "mission_incomplete" in types


def test_detect_incidents_accepts_user_markers():
    from app.detectors import detect_incidents
    markers = [{"lat": 1.0, "lon": 2.0, "alt_m": 0.0, "timestamp_utc": "2026-01-01T00:00:00Z"}]
    incidents = detect_incidents([], user_markers=markers)
    assert any(i.incident_type == "operator_marked_debris" for i in incidents)


def test_airborne_modes():
    assert _is_airborne("P-GPS") is True
    assert _is_airborne("ATTI") is True
    assert _is_airborne("AUTO") is True
    assert _is_airborne("LAND") is False
    assert _is_airborne("auto_land") is False
    assert _is_airborne(None) is False
    assert _is_airborne("") is False


def test_last_known_position_ignores_ground_freeze():
    from datetime import datetime, timedelta, timezone

    ts_base = datetime(2026, 7, 16, 15, 0, 0, tzinfo=timezone.utc)
    series = []
    for i in range(90):
        flying = i >= 60
        series.append({
            "timestamp_utc": (ts_base + timedelta(seconds=i)).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "position": {
                "lat": 1.3521 + (i - 60) * 0.0001 if flying else 1.3521,
                "lon": 103.8198,
                "alt_m": 60.0 if flying else 0.0,
            },
            "sensors": {},
            "attitude": {"yaw_deg": 45.0 + i * 3.0, "roll_deg": 1.0, "pitch_deg": 0.5},
            "battery": {"percent": 80},
        })
    results = _detect_last_known_position(series)
    assert all(r.incident_type != "last_known_position" for r in results)


def test_last_known_position_fires_on_midair_freeze():
    from datetime import datetime, timedelta, timezone

    ts_base = datetime(2026, 7, 16, 15, 0, 0, tzinfo=timezone.utc)
    series = []
    for i in range(50):
        climbing = i < 10
        series.append({
            "timestamp_utc": (ts_base + timedelta(seconds=i)).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "position": {
                "lat": 1.3521 + i * 0.0001 if climbing else 1.3521 + 9 * 0.0001,
                "lon": 103.8198,
                "alt_m": i * 5.0 if climbing else 50.0,
            },
            "sensors": {},
            "attitude": {"yaw_deg": 45.0 + i * 3.0, "roll_deg": 1.0, "pitch_deg": 0.5},
            "battery": {"percent": 80},
        })
    results = _detect_last_known_position(series)
    assert any(r.incident_type == "last_known_position" for r in results)


def test_attitude_shock_requires_airborne_sample():
    from datetime import datetime, timedelta, timezone

    ts_base = datetime(2026, 7, 16, 15, 0, 0, tzinfo=timezone.utc)

    def build(alt_m: float) -> list[dict]:
        series = []
        for i in range(10):
            series.append({
                "timestamp_utc": (ts_base + timedelta(seconds=i)).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "position": {"lat": 1.3521, "lon": 103.8198, "alt_m": alt_m},
                "sensors": {},
                "attitude": {"roll_deg": 50.0 if i == 5 else 1.0, "pitch_deg": 0.5, "yaw_deg": 45.0},
                "battery": {"percent": 80},
            })
        return series

    ground_types = {inc.incident_type for inc in detect_incidents(build(0.0))}
    assert "attitude_shock" not in ground_types

    airborne = build(30.0)
    # ground reference comes from the first samples, so start on the ground
    for i, sample in enumerate(airborne):
        if i < 5:
            sample["position"]["alt_m"] = 0.0
    air_types = {inc.incident_type for inc in detect_incidents(airborne)}
    assert "attitude_shock" in air_types


def test_last_known_position_ignores_hover_jitter():
    import random
    from datetime import datetime, timedelta, timezone

    rng = random.Random(7)
    ts_base = datetime(2026, 7, 16, 15, 0, 0, tzinfo=timezone.utc)
    series = []
    lat = 1.3521
    for i in range(95):
        if i >= 5:
            lat += rng.uniform(2e-6, 4e-6) * (1 if i % 2 else -1)  # ~0.2-0.4 m wander
        series.append({
            "timestamp_utc": (ts_base + timedelta(seconds=i)).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "position": {"lat": lat, "lon": 103.8198, "alt_m": 0.0 if i < 5 else 50.0},
            "sensors": {},
            "attitude": {"yaw_deg": 45.0 + i * 3.0, "roll_deg": 1.0, "pitch_deg": 0.5},
            "battery": {"percent": 80},
        })
    results = _detect_last_known_position(series)
    assert all(r.incident_type != "last_known_position" for r in results)


def test_last_known_position_exact_fix_then_movement():
    from datetime import datetime, timedelta, timezone

    ts_base = datetime(2026, 7, 16, 15, 0, 0, tzinfo=timezone.utc)
    frozen_lat, frozen_lon = 1.3521, 103.8198
    series = []
    for i in range(60):
        moving = i >= 50
        series.append({
            "timestamp_utc": (ts_base + timedelta(seconds=i)).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "position": {
                "lat": frozen_lat + (i - 50) * 0.0001 if moving else frozen_lat,
                "lon": frozen_lon,
                "alt_m": 0.0 if i < 5 else 50.0,
            },
            "sensors": {},
            "attitude": {"yaw_deg": 45.0 + i * 3.0, "roll_deg": 1.0, "pitch_deg": 0.5},
            "battery": {"percent": 80},
        })
    results = [r for r in _detect_last_known_position(series) if r.incident_type == "last_known_position"]
    assert len(results) == 1
    inc = results[0]
    last_frozen_ts = (ts_base + timedelta(seconds=50)).strftime("%Y-%m-%dT%H:%M:%SZ")
    assert inc.evidence["frozen_end"]["timestamp_utc"] == last_frozen_ts
    assert inc.evidence["frozen_end"]["lat"] == frozen_lat
    assert inc.evidence["frozen_end"]["lon"] == frozen_lon


def test_last_known_position_static_attitude_is_parked_not_frozen():
    from datetime import datetime, timedelta, timezone

    ts_base = datetime(2026, 7, 16, 15, 0, 0, tzinfo=timezone.utc)
    series = []
    for i in range(50):
        moving = i >= 45
        series.append({
            "timestamp_utc": (ts_base + timedelta(seconds=i)).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "position": {
                "lat": 1.3521 + (i - 45) * 0.0001 if moving else 1.3521,
                "lon": 103.8198,
                "alt_m": 0.0 if i < 5 else 50.0,
            },
            "sensors": {},
            "attitude": {"yaw_deg": 45.0, "roll_deg": 1.0, "pitch_deg": 0.5},
            "battery": {"percent": 80},
        })
    results = _detect_last_known_position(series)
    assert all(r.incident_type != "last_known_position" for r in results)
