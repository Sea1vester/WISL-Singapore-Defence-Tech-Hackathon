"""
Phase 4 tests for chart_export.py
"""
from __future__ import annotations

import json

import pytest

from app.config import settings


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def db_env(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "database_path", str(tmp_path / "test.db"))
    monkeypatch.setattr(settings, "visuals_dir", str(tmp_path / "visuals"))
    from app.db import run_migrations
    run_migrations()
    return tmp_path


def _insert_flight(conn, flight_id: str) -> None:
    conn.execute(
        "INSERT INTO flights (id, source, started_at) VALUES (?, ?, ?)",
        (flight_id, "test", "2026-01-01T00:00:00Z"),
    )
    conn.commit()


def _insert_canonical_record(conn, flight_id: str, ingest_id: str, recorded_at: str, position: dict, battery: dict, attitude: dict) -> None:
    from app.schemas import new_id
    canonical = {
        "flight_id": flight_id,
        "timestamp_utc": recorded_at,
        "position": position,
        "attitude": attitude,
        "battery": battery,
        "sensors": {},
        "metadata": {},
    }
    conn.execute(
        """
        INSERT INTO canonical_records (id, ingest_id, flight_id, recorded_at, canonical_json, validation_ok)
        VALUES (?, ?, ?, ?, ?, 1)
        """,
        (new_id(), ingest_id, flight_id, recorded_at, json.dumps(canonical)),
    )
    conn.commit()


def _make_flight_with_records(conn, n: int = 10) -> str:
    from app.schemas import new_id
    import datetime

    flight_id = new_id()
    _insert_flight(conn, flight_id)
    # Insert a minimal ingest_event so canonical_records FK is satisfied
    ingest_id = new_id()
    conn.execute(
        "INSERT INTO ingest_events (id, flight_id, payload_json) VALUES (?, ?, ?)",
        (ingest_id, flight_id, "{}"),
    )
    conn.commit()
    base = datetime.datetime(2026, 1, 1, 10, 0, 0, tzinfo=datetime.timezone.utc)
    for i in range(n):
        ts = (base + datetime.timedelta(seconds=i * 5)).isoformat()
        _insert_canonical_record(
            conn,
            flight_id,
            ingest_id,
            ts,
            position={"lat": 1.35 + i * 0.001, "lon": 103.82, "alt_m": 50.0 + i},
            battery={"percent": 100.0 - i * 2, "voltage_v": 22.4},
            attitude={"roll_deg": i * 0.5, "pitch_deg": i * 0.3, "yaw_deg": i * 1.0},
        )
    return flight_id


# ---------------------------------------------------------------------------
# _extract_series tests (pure, no DB)
# ---------------------------------------------------------------------------

class TestExtractSeries:
    def test_extracts_altitude(self):
        from app.chart_export import _extract_series
        records = [
            {"recorded_at": "2026-01-01T10:00:00Z", "position": {"alt_m": 50.0}, "battery": {}, "attitude": {}},
            {"recorded_at": "2026-01-01T10:00:05Z", "position": {"alt_m": 55.0}, "battery": {}, "attitude": {}},
        ]
        series = _extract_series(records)
        assert len(series["altitude_m"]) == 2
        assert series["altitude_m"][0][1] == 50.0

    def test_skips_missing_values(self):
        from app.chart_export import _extract_series
        records = [
            {"recorded_at": "2026-01-01T10:00:00Z", "position": {}, "battery": {}, "attitude": {}},
        ]
        series = _extract_series(records)
        assert series["altitude_m"] == []
        assert series["battery_pct"] == []

    def test_skips_invalid_timestamp(self):
        from app.chart_export import _extract_series
        records = [
            {"recorded_at": "not-a-date", "position": {"alt_m": 50.0}, "battery": {}, "attitude": {}},
        ]
        series = _extract_series(records)
        assert series["altitude_m"] == []


# ---------------------------------------------------------------------------
# _render_chart tests
# ---------------------------------------------------------------------------

class TestRenderChart:
    def test_returns_png_bytes(self):
        from app.chart_export import _render_chart
        series = {"alt_m": [(1_000_000.0, 50.0), (1_000_005.0, 55.0)]}
        result = _render_chart("Test chart", series, ylabel="m")
        assert result is not None
        assert result[:4] == b"\x89PNG"

    def test_returns_none_for_empty_series(self):
        from app.chart_export import _render_chart
        result = _render_chart("Empty", {"alt_m": []}, ylabel="m")
        assert result is None


# ---------------------------------------------------------------------------
# export_charts_for_flight integration tests
# ---------------------------------------------------------------------------

class TestExportChartsForFlight:
    def test_saves_charts_for_flight_with_records(self, db_env, monkeypatch):
        from app.db import db_session
        import app.visuals as v

        with db_session() as conn:
            flight_id = _make_flight_with_records(conn)

        from app.chart_export import export_charts_for_flight
        count = export_charts_for_flight(flight_id)

        assert count >= 1  # at least altitude chart
        charts = v.list_visuals(flight_id, kind="sensor_chart")
        assert len(charts) == count
        for chart in charts:
            assert chart["source"] == "worker"
            assert chart["mime_type"] == "image/png"
            assert chart["size_bytes"] > 0

    def test_saves_up_to_three_charts(self, db_env, monkeypatch):
        from app.db import db_session
        from app.chart_export import export_charts_for_flight

        with db_session() as conn:
            flight_id = _make_flight_with_records(conn)

        count = export_charts_for_flight(flight_id)
        assert count <= 3

    def test_idempotent_does_not_duplicate(self, db_env, monkeypatch):
        from app.db import db_session
        from app.chart_export import export_charts_for_flight
        import app.visuals as v

        with db_session() as conn:
            flight_id = _make_flight_with_records(conn)

        count1 = export_charts_for_flight(flight_id)
        count2 = export_charts_for_flight(flight_id)

        assert count2 == 0  # second call is skipped
        assert len(v.list_visuals(flight_id, kind="sensor_chart")) == count1

    def test_returns_zero_for_empty_flight(self, db_env, monkeypatch):
        from app.db import db_session, run_migrations
        from app.chart_export import export_charts_for_flight
        from app.schemas import new_id

        with db_session() as conn:
            flight_id = new_id()
            _insert_flight(conn, flight_id)

        count = export_charts_for_flight(flight_id)
        assert count == 0

    def test_chart_files_exist_on_disk(self, db_env, monkeypatch):
        from app.db import db_session
        from app.chart_export import export_charts_for_flight
        import app.visuals as v

        with db_session() as conn:
            flight_id = _make_flight_with_records(conn)

        export_charts_for_flight(flight_id)
        for chart in v.list_visuals(flight_id, kind="sensor_chart"):
            path = v.resolve_visual_path(chart["id"])
            assert path is not None and path.exists()
            assert path.stat().st_size > 0
