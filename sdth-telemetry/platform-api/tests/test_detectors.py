from app.canonical_series import series_from_l1_payload
from app.detectors import detect_incidents
from tests.hardware_l1 import ardupilot_l1, dji_l1, px4_l1


def _types(payload) -> set[str]:
    series = series_from_l1_payload(payload)
    return {item.incident_type for item in detect_incidents(series)}


def test_battery_low_and_warning_on_dji_series():
    types = _types(dji_l1(inject="battery_low"))
    assert "battery_low" in types or "battery_critical" in types


def test_operator_warning_from_normalized_warning_field():
    types = _types(dji_l1(inject="warning"))
    assert "operator_warning" in types


def test_battery_plunge_on_px4_series():
    assert "battery_plunge" in _types(px4_l1(inject="battery_plunge"))


def test_attitude_shock_on_ardupilot_crash_attitude():
    assert "attitude_shock" in _types(ardupilot_l1(inject="attitude"))


def test_healthy_dji_has_no_rules_without_injection():
    types = _types(dji_l1(inject=None))
    assert types == set()
