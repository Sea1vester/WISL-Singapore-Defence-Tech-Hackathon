"""
Phase 1 tests for the visual_records migration and visuals.py CRUD helpers.

These tests run against an in-process SQLite DB (via the test client fixture)
so no Docker stack is needed.
"""
from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.main import app


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def client(tmp_path, monkeypatch):
    db_path = tmp_path / "test.db"
    monkeypatch.setattr(settings, "database_path", str(db_path))
    monkeypatch.setattr(settings, "raw_upload_dir", str(tmp_path / "uploads"))
    monkeypatch.setattr(settings, "visuals_dir", str(tmp_path / "visuals"))
    monkeypatch.setattr(settings, "ingest_api_keys", "test-key")

    def noop(_id: str) -> None:
        return None

    monkeypatch.setattr("app.ingest.enqueue_translation_job", noop)
    monkeypatch.setattr("app.ingest.enqueue_raw_upload", noop)
    monkeypatch.setattr("app.datasets.enqueue_raw_upload", noop)

    with TestClient(app) as c:
        yield c


@pytest.fixture()
def visuals_crud(tmp_path, monkeypatch):
    """Fixture that patches settings and returns the visuals module for direct CRUD testing."""
    monkeypatch.setattr(settings, "database_path", str(tmp_path / "test.db"))
    monkeypatch.setattr(settings, "visuals_dir", str(tmp_path / "visuals"))
    # Run migrations so the visual_records table exists
    from app.db import run_migrations
    run_migrations()
    import app.visuals as v
    return v


# ---------------------------------------------------------------------------
# Migration tests
# ---------------------------------------------------------------------------

class TestMigration:
    def test_visual_records_table_exists(self, visuals_crud):
        """After migrations the visual_records table must exist."""
        from app.db import db_session
        with db_session() as conn:
            rows = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='visual_records'"
            ).fetchall()
        assert rows, "visual_records table was not created by migration 008"

    def test_visual_records_indexes_exist(self, visuals_crud):
        from app.db import db_session
        with db_session() as conn:
            indexes = {
                r["name"]
                for r in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='visual_records'"
                ).fetchall()
            }
        expected = {
            "idx_visuals_flight",
            "idx_visuals_incident",
            "idx_visuals_record",
            "idx_visuals_kind",
        }
        assert expected.issubset(indexes), f"Missing indexes: {expected - indexes}"


# ---------------------------------------------------------------------------
# CRUD: save_visual
# ---------------------------------------------------------------------------

class TestSaveVisual:
    def _make_flight(self, conn):
        """Insert a minimal flights row and return its id."""
        from app.schemas import new_id
        fid = new_id()
        conn.execute(
            "INSERT INTO flights (id, source, started_at) VALUES (?, ?, ?)",
            (fid, "test-source", "2026-01-01T00:00:00Z"),
        )
        conn.commit()
        return fid

    def test_save_creates_file_and_db_row(self, tmp_path, monkeypatch):
        monkeypatch.setattr(settings, "database_path", str(tmp_path / "test.db"))
        monkeypatch.setattr(settings, "visuals_dir", str(tmp_path / "visuals"))
        from app.db import run_migrations, db_session
        run_migrations()
        import app.visuals as v

        with db_session() as conn:
            fid = self._make_flight(conn)

        result = v.save_visual(
            flight_id=fid,
            recorded_at="2026-01-01T10:00:00Z",
            kind="sensor_chart",
            data=b"\x89PNG fake",
            source="worker",
            caption="Altitude chart",
        )

        assert result["id"]
        assert result["flight_id"] == fid
        assert result["kind"] == "sensor_chart"
        assert result["source"] == "worker"
        assert result["caption"] == "Altitude chart"
        assert result["size_bytes"] == len(b"\x89PNG fake")

        # File must exist on disk
        file_path = tmp_path / "visuals" / fid / f"{result['id']}.png"
        assert file_path.exists()
        assert file_path.read_bytes() == b"\x89PNG fake"

    def test_save_rejects_invalid_kind(self, tmp_path, monkeypatch):
        monkeypatch.setattr(settings, "database_path", str(tmp_path / "test.db"))
        monkeypatch.setattr(settings, "visuals_dir", str(tmp_path / "visuals"))
        from app.db import run_migrations
        run_migrations()
        import app.visuals as v

        with pytest.raises(ValueError, match="Invalid kind"):
            v.save_visual(
                flight_id="any",
                recorded_at="2026-01-01T00:00:00Z",
                kind="video",
                data=b"bytes",
            )

    def test_save_rejects_invalid_source(self, tmp_path, monkeypatch):
        monkeypatch.setattr(settings, "database_path", str(tmp_path / "test.db"))
        monkeypatch.setattr(settings, "visuals_dir", str(tmp_path / "visuals"))
        from app.db import run_migrations, db_session
        run_migrations()
        import app.visuals as v

        with db_session() as conn:
            fid = self._make_flight(conn)

        with pytest.raises(ValueError, match="Invalid source"):
            v.save_visual(
                flight_id=fid,
                recorded_at="2026-01-01T00:00:00Z",
                kind="sensor_chart",
                data=b"bytes",
                source="unknown-source",
            )


# ---------------------------------------------------------------------------
# CRUD: get_visual / list_visuals
# ---------------------------------------------------------------------------

class TestGetAndList:
    def _setup(self, tmp_path, monkeypatch):
        monkeypatch.setattr(settings, "database_path", str(tmp_path / "test.db"))
        monkeypatch.setattr(settings, "visuals_dir", str(tmp_path / "visuals"))
        from app.db import run_migrations, db_session
        run_migrations()
        import app.visuals as v
        from app.schemas import new_id

        with db_session() as conn:
            fid = new_id()
            conn.execute(
                "INSERT INTO flights (id, source, started_at) VALUES (?, ?, ?)",
                (fid, "test", "2026-01-01T00:00:00Z"),
            )
            conn.commit()
        return v, fid

    def test_get_returns_none_for_missing(self, tmp_path, monkeypatch):
        v, _ = self._setup(tmp_path, monkeypatch)
        assert v.get_visual("nonexistent-id") is None

    def test_list_returns_saved_visuals(self, tmp_path, monkeypatch):
        v, fid = self._setup(tmp_path, monkeypatch)

        v.save_visual(flight_id=fid, recorded_at="2026-01-01T10:00:00Z", kind="sensor_chart", data=b"c1")
        v.save_visual(flight_id=fid, recorded_at="2026-01-01T11:00:00Z", kind="cesium_screenshot", data=b"c2")

        all_visuals = v.list_visuals(fid)
        assert len(all_visuals) == 2

        charts = v.list_visuals(fid, kind="sensor_chart")
        assert len(charts) == 1
        assert charts[0]["kind"] == "sensor_chart"

    def test_list_empty_for_unknown_flight(self, tmp_path, monkeypatch):
        v, _ = self._setup(tmp_path, monkeypatch)
        assert v.list_visuals("no-such-flight") == []

    def test_list_offset_and_limit(self, tmp_path, monkeypatch):
        v, fid = self._setup(tmp_path, monkeypatch)
        for i in range(5):
            v.save_visual(
                flight_id=fid,
                recorded_at=f"2026-01-01T{10 + i:02d}:00:00Z",
                kind="sensor_chart",
                data=b"data",
            )
        page = v.list_visuals(fid, limit=2, offset=2)
        assert len(page) == 2


# ---------------------------------------------------------------------------
# CRUD: delete_visual / delete_visuals_for_flight
# ---------------------------------------------------------------------------

class TestDelete:
    def _setup(self, tmp_path, monkeypatch):
        monkeypatch.setattr(settings, "database_path", str(tmp_path / "test.db"))
        monkeypatch.setattr(settings, "visuals_dir", str(tmp_path / "visuals"))
        from app.db import run_migrations, db_session
        run_migrations()
        import app.visuals as v
        from app.schemas import new_id

        with db_session() as conn:
            fid = new_id()
            conn.execute(
                "INSERT INTO flights (id, source, started_at) VALUES (?, ?, ?)",
                (fid, "test", "2026-01-01T00:00:00Z"),
            )
            conn.commit()
        return v, fid, tmp_path

    def test_delete_visual_removes_file_and_row(self, tmp_path, monkeypatch):
        v, fid, tp = self._setup(tmp_path, monkeypatch)
        row = v.save_visual(flight_id=fid, recorded_at="2026-01-01T10:00:00Z", kind="sensor_chart", data=b"png")
        vid = row["id"]
        file_path = tp / "visuals" / fid / f"{vid}.png"

        assert file_path.exists()
        assert v.delete_visual(vid) is True
        assert not file_path.exists()
        assert v.get_visual(vid) is None

    def test_delete_visual_returns_false_for_missing(self, tmp_path, monkeypatch):
        v, _, _ = self._setup(tmp_path, monkeypatch)
        assert v.delete_visual("no-such-id") is False

    def test_delete_visuals_for_flight_removes_all(self, tmp_path, monkeypatch):
        v, fid, tp = self._setup(tmp_path, monkeypatch)
        for i in range(3):
            v.save_visual(
                flight_id=fid,
                recorded_at=f"2026-01-01T{10 + i:02d}:00:00Z",
                kind="sensor_chart",
                data=b"data",
            )

        count = v.delete_visuals_for_flight(fid)
        assert count == 3
        assert v.list_visuals(fid) == []
        # Flight directory should be gone
        assert not (tp / "visuals" / fid).exists()

    def test_delete_visuals_for_flight_noop_if_empty(self, tmp_path, monkeypatch):
        v, fid, _ = self._setup(tmp_path, monkeypatch)
        assert v.delete_visuals_for_flight(fid) == 0


# ---------------------------------------------------------------------------
# resolve_visual_path
# ---------------------------------------------------------------------------

class TestResolveVisualPath:
    def test_resolves_correct_absolute_path(self, tmp_path, monkeypatch):
        monkeypatch.setattr(settings, "database_path", str(tmp_path / "test.db"))
        monkeypatch.setattr(settings, "visuals_dir", str(tmp_path / "visuals"))
        from app.db import run_migrations, db_session
        run_migrations()
        import app.visuals as v
        from app.schemas import new_id

        with db_session() as conn:
            fid = new_id()
            conn.execute(
                "INSERT INTO flights (id, source, started_at) VALUES (?, ?, ?)",
                (fid, "test", "2026-01-01T00:00:00Z"),
            )
            conn.commit()

        row = v.save_visual(
            flight_id=fid, recorded_at="2026-01-01T00:00:00Z", kind="sensor_chart", data=b"x"
        )
        path = v.resolve_visual_path(row["id"])
        assert path is not None
        assert path.is_absolute()
        assert path.exists()

    def test_returns_none_for_missing(self, tmp_path, monkeypatch):
        monkeypatch.setattr(settings, "database_path", str(tmp_path / "test.db"))
        monkeypatch.setattr(settings, "visuals_dir", str(tmp_path / "visuals"))
        from app.db import run_migrations
        run_migrations()
        import app.visuals as v

        assert v.resolve_visual_path("missing") is None
