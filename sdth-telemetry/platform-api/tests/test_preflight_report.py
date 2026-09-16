"""Tests for the pre-emptive mission-planning report: data assembly, PDF export, and API."""
from __future__ import annotations

import io

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.main import app

AUTH = {"Authorization": "Bearer test-key"}
JPEG_BYTES = (
    b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00"
    b"\xff\xd9"
)


def _real_jpeg_bytes(*, size=(32, 32), color=(120, 120, 120)) -> bytes:
    """A genuinely decodable JPEG, for tests that exercise image-quality metrics.
    JPEG_BYTES above is a minimal stub (SOI/APP0/EOI only, no image data) that's
    fine for API plumbing tests but not decodable by PIL."""
    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", size, color).save(buf, format="JPEG")
    return buf.getvalue()


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "database_path", str(tmp_path / "test.db"))
    monkeypatch.setattr(settings, "raw_upload_dir", str(tmp_path / "uploads"))
    monkeypatch.setattr(settings, "visuals_dir", str(tmp_path / "visuals"))
    monkeypatch.setattr(settings, "reports_dir", str(tmp_path / "reports"))
    monkeypatch.setattr(settings, "ingest_api_keys", "test-key")

    def noop(_id: str) -> None:
        return None

    monkeypatch.setattr("app.ingest.enqueue_translation_job", noop)
    monkeypatch.setattr("app.ingest.enqueue_raw_upload", noop)
    monkeypatch.setattr("app.datasets.enqueue_raw_upload", noop)

    with TestClient(app) as c:
        yield c


def _ingest_flight_with_incidents(client: TestClient, flight_id: str, *, source: str = "dji-csv") -> None:
    """A small record series that fires telemetry_gap and battery_critical/plunge."""
    records = [
        {"timestamp_utc": "2026-01-01T00:00:00Z", "lat": 1.35, "lon": 103.82, "alt_m": 30, "battery_pct": 90},
        {"timestamp_utc": "2026-01-01T00:00:01Z", "lat": 1.3501, "lon": 103.82, "alt_m": 30, "battery_pct": 88},
        {"timestamp_utc": "2026-01-01T00:00:02Z", "lat": 1.3502, "lon": 103.82, "alt_m": 30, "battery_pct": 85},
        {"timestamp_utc": "2026-01-01T00:00:22Z", "lat": 1.3503, "lon": 103.82, "alt_m": 30, "battery_pct": 8},
        {"timestamp_utc": "2026-01-01T00:00:23Z", "lat": 1.3504, "lon": 103.82, "alt_m": 30, "battery_pct": 7},
    ]
    resp = client.post(
        "/v1/telemetry/ingest",
        json={
            "flight_id": flight_id,
            "timestamp_utc": records[0]["timestamp_utc"],
            "source": source,
            "records": records,
        },
        headers=AUTH,
    )
    assert resp.status_code == 202, resp.text


def _upload_camera_frame(client: TestClient, flight_id: str, recorded_at: str, *, decodable: bool = False) -> dict:
    data = _real_jpeg_bytes() if decodable else JPEG_BYTES
    resp = client.post(
        f"/v1/flights/{flight_id}/visuals",
        params={"kind": "camera_frame", "recorded_at": recorded_at, "source": "worker"},
        files={"file": ("frame.jpg", io.BytesIO(data), "image/jpeg")},
        headers=AUTH,
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


class TestPreemptiveReportMigration:
    def test_table_and_index_exist(self, client):
        from app.db import db_session

        with db_session() as conn:
            tables = {r["name"] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
            indexes = {
                r["name"]
                for r in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='preemptive_reports'"
                ).fetchall()
            }
        assert "preemptive_reports" in tables
        assert "idx_preemptive_reports_flight" in indexes


class TestBuildPreemptiveReport:
    def test_unknown_flight_raises(self, client):
        from app.db import db_session
        from app.preflight_report import build_preemptive_report

        with db_session() as conn, pytest.raises(KeyError):
            build_preemptive_report(conn, "does-not-exist")

    def test_reports_incidents_and_sections(self, client):
        from app.db import db_session
        from app.preflight_report import build_preemptive_report

        flight_id = "flight-with-incidents"
        _ingest_flight_with_incidents(client, flight_id)

        with db_session() as conn:
            report = build_preemptive_report(conn, flight_id)

        assert report["flight_id"] == flight_id
        assert report["brand"] == "dji"
        assert report["incident_count"] > 0
        assert "telemetry_gap" in report["incident_summary"]
        assert report["link_reliability"]["dropout_count"] == 1
        assert "no audio" in report["link_reliability"]["disclosure"].lower()
        assert report["camera_reliability"]["available"] is False
        assert "terrain" in report["camera_reliability"]["disclosure"].lower()
        assert len(report["recommendations"]) >= 1
        assert "human review" in report["limitations"].lower()

    def test_clean_flight_has_no_incident_recommendation(self, client):
        from app.db import db_session
        from app.preflight_report import build_preemptive_report

        flight_id = "flight-clean"
        records = [
            {"timestamp_utc": f"2026-01-01T00:00:{i:02d}Z", "lat": 1.35 + i * 0.0001, "lon": 103.82, "alt_m": 30, "battery_pct": 90 - i}
            for i in range(5)
        ]
        resp = client.post(
            "/v1/telemetry/ingest",
            json={"flight_id": flight_id, "timestamp_utc": records[0]["timestamp_utc"], "source": "dji-csv", "records": records},
            headers=AUTH,
        )
        assert resp.status_code == 202

        with db_session() as conn:
            report = build_preemptive_report(conn, flight_id)

        assert report["incident_count"] == 0
        assert "no preemptive changes" in report["recommendations"][0].lower()

    def test_camera_reliability_available_with_visuals(self, client):
        from app.db import db_session
        from app.preflight_report import build_preemptive_report

        flight_id = "flight-with-camera"
        _ingest_flight_with_incidents(client, flight_id)
        _upload_camera_frame(client, flight_id, "2026-01-01T00:00:00Z", decodable=True)
        _upload_camera_frame(client, flight_id, "2026-01-01T00:00:01Z", decodable=True)

        with db_session() as conn:
            report = build_preemptive_report(conn, flight_id)

        camera = report["camera_reliability"]
        assert camera["available"] is True
        assert camera["total_frames"] == 2
        assert len(camera["quality_samples"]) == 2
        assert all("brightness_mean" in q for q in camera["quality_samples"])

    def test_undecodable_frame_is_skipped_not_errored(self, client):
        """A corrupt/truncated frame (e.g. JPEG_BYTES, a minimal non-decodable stub)
        should be counted in total_frames but silently excluded from quality_samples,
        not raise."""
        from app.db import db_session
        from app.preflight_report import build_preemptive_report

        flight_id = "flight-camera-undecodable"
        _ingest_flight_with_incidents(client, flight_id)
        _upload_camera_frame(client, flight_id, "2026-01-01T00:00:00Z", decodable=False)

        with db_session() as conn:
            report = build_preemptive_report(conn, flight_id)

        camera = report["camera_reliability"]
        assert camera["available"] is True
        assert camera["total_frames"] == 1
        assert camera["quality_samples"] == []


class TestPreemptiveReportPdf:
    def test_render_produces_nonempty_pdf(self, client, tmp_path):
        from app.db import db_session
        from app.pdf_report import render_preemptive_report_pdf
        from app.preflight_report import build_preemptive_report

        flight_id = "flight-pdf"
        _ingest_flight_with_incidents(client, flight_id)

        with db_session() as conn:
            report = build_preemptive_report(conn, flight_id)

        out_path = tmp_path / "out.pdf"
        result = render_preemptive_report_pdf(report, out_path=out_path)
        assert result == out_path
        assert out_path.exists()
        assert out_path.stat().st_size > 500
        assert out_path.read_bytes().startswith(b"%PDF")


class TestPreemptiveReportApi:
    def test_post_creates_and_stores_report(self, client):
        flight_id = "flight-api-post"
        _ingest_flight_with_incidents(client, flight_id)

        resp = client.post(f"/v1/flights/{flight_id}/preemptive-report", headers=AUTH)
        assert resp.status_code == 201, resp.text
        body = resp.json()
        assert body["flight_id"] == flight_id
        assert body["incident_count"] > 0
        assert body["report"]["incident_summary"]

    def test_post_unknown_flight_404s(self, client):
        resp = client.post("/v1/flights/does-not-exist/preemptive-report", headers=AUTH)
        assert resp.status_code == 404

    def test_post_requires_auth(self, client):
        flight_id = "flight-api-noauth"
        _ingest_flight_with_incidents(client, flight_id)
        resp = client.post(f"/v1/flights/{flight_id}/preemptive-report")
        assert resp.status_code == 401

    def test_get_returns_most_recent(self, client):
        flight_id = "flight-api-get"
        _ingest_flight_with_incidents(client, flight_id)

        first = client.post(f"/v1/flights/{flight_id}/preemptive-report", headers=AUTH).json()
        second = client.post(f"/v1/flights/{flight_id}/preemptive-report", headers=AUTH).json()
        assert first["id"] != second["id"]

        resp = client.get(f"/v1/flights/{flight_id}/preemptive-report", headers=AUTH)
        assert resp.status_code == 200
        assert resp.json()["id"] == second["id"]

    def test_get_404s_when_no_report_yet(self, client):
        flight_id = "flight-api-no-report"
        _ingest_flight_with_incidents(client, flight_id)
        resp = client.get(f"/v1/flights/{flight_id}/preemptive-report", headers=AUTH)
        assert resp.status_code == 404

    def test_file_endpoint_streams_pdf(self, client):
        flight_id = "flight-api-file"
        _ingest_flight_with_incidents(client, flight_id)
        created = client.post(f"/v1/flights/{flight_id}/preemptive-report", headers=AUTH).json()

        resp = client.get(f"/v1/preemptive-reports/{created['id']}/file", headers=AUTH)
        assert resp.status_code == 200
        assert resp.headers["content-type"] == "application/pdf"
        assert resp.content.startswith(b"%PDF")

    def test_file_endpoint_404s_for_unknown_report(self, client):
        resp = client.get("/v1/preemptive-reports/does-not-exist/file", headers=AUTH)
        assert resp.status_code == 404


class TestComprehensiveReportMigration:
    def test_table_and_index_exist(self, client):
        from app.db import db_session

        with db_session() as conn:
            tables = {r["name"] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
            indexes = {
                r["name"]
                for r in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='comprehensive_reports'"
                ).fetchall()
            }
        assert "comprehensive_reports" in tables
        assert "idx_comprehensive_reports_flight" in indexes


class TestBuildComprehensiveReport:
    def test_unknown_flight_raises(self, client):
        from app.db import db_session
        from app.preflight_report import build_comprehensive_report

        with db_session() as conn, pytest.raises(KeyError):
            build_comprehensive_report(conn, "does-not-exist")

    def test_combines_all_three_sections(self, client, monkeypatch):
        from app.db import db_session
        from app.preflight_report import build_comprehensive_report

        # Skip the real Ollama call -- exercise the deterministic fallback path,
        # same posture as the rest of this offline-friendly test suite.
        monkeypatch.setattr("app.analytics._try_model_report", lambda *a, **k: None)

        flight_id = "flight-comprehensive"
        _ingest_flight_with_incidents(client, flight_id)

        with db_session() as conn:
            report = build_comprehensive_report(conn, flight_id, allow_llm=False)

        assert report["flight_id"] == flight_id
        assert report["brand"] == "dji"
        assert report["incident_report"]["kind"] == "evidence_backed_incident_summary"
        assert report["incident_report"]["model_enrichment"] == "degraded"
        assert report["preemptive_findings"]["incident_count"] > 0
        assert isinstance(report["recurring_pattern_matches"], list)
        assert "each section" in report["limitations"].lower()

    def test_recurring_pattern_matches_only_own_signatures(self, client, monkeypatch):
        """A flight with no signature shared by another flight should report no matches,
        even once fleet-wide patterns exist for unrelated signatures."""
        from app.db import db_session
        from app.incidents import index_flight
        from app.preflight_report import build_comprehensive_report

        monkeypatch.setattr("app.analytics._try_model_report", lambda *a, **k: None)

        _ingest_flight_with_incidents(client, "flight-shared-a")
        _ingest_flight_with_incidents(client, "flight-shared-b")
        index_flight("flight-shared-a")
        index_flight("flight-shared-b")

        with db_session() as conn:
            report = build_comprehensive_report(conn, "flight-shared-a", allow_llm=False)

        assert len(report["recurring_pattern_matches"]) > 0
        assert all(p["flight_count"] >= 2 for p in report["recurring_pattern_matches"])


class TestComprehensiveReportPdf:
    def test_render_produces_nonempty_pdf(self, client, tmp_path, monkeypatch):
        from app.db import db_session
        from app.pdf_report import render_comprehensive_report_pdf
        from app.preflight_report import build_comprehensive_report

        monkeypatch.setattr("app.analytics._try_model_report", lambda *a, **k: None)

        flight_id = "flight-comprehensive-pdf"
        _ingest_flight_with_incidents(client, flight_id)

        with db_session() as conn:
            report = build_comprehensive_report(conn, flight_id, allow_llm=False)

        out_path = tmp_path / "out.pdf"
        result = render_comprehensive_report_pdf(report, out_path=out_path)
        assert result == out_path
        assert out_path.exists()
        assert out_path.stat().st_size > 500
        assert out_path.read_bytes().startswith(b"%PDF")


class TestComprehensiveReportApi:
    def test_post_creates_and_stores_report(self, client, monkeypatch):
        monkeypatch.setattr("app.analytics._try_model_report", lambda *a, **k: None)
        flight_id = "flight-comprehensive-api-post"
        _ingest_flight_with_incidents(client, flight_id)

        resp = client.post(f"/v1/flights/{flight_id}/comprehensive-report", headers=AUTH)
        assert resp.status_code == 201, resp.text
        body = resp.json()
        assert body["flight_id"] == flight_id
        assert body["report"]["incident_report"]["flight_id"] == flight_id
        assert body["report"]["preemptive_findings"]["incident_count"] > 0

    def test_post_unknown_flight_404s(self, client):
        resp = client.post("/v1/flights/does-not-exist/comprehensive-report", headers=AUTH)
        assert resp.status_code == 404

    def test_post_requires_auth(self, client):
        flight_id = "flight-comprehensive-api-noauth"
        _ingest_flight_with_incidents(client, flight_id)
        resp = client.post(f"/v1/flights/{flight_id}/comprehensive-report")
        assert resp.status_code == 401

    def test_get_returns_most_recent(self, client, monkeypatch):
        monkeypatch.setattr("app.analytics._try_model_report", lambda *a, **k: None)
        flight_id = "flight-comprehensive-api-get"
        _ingest_flight_with_incidents(client, flight_id)

        first = client.post(f"/v1/flights/{flight_id}/comprehensive-report", headers=AUTH).json()
        second = client.post(f"/v1/flights/{flight_id}/comprehensive-report", headers=AUTH).json()
        assert first["id"] != second["id"]

        resp = client.get(f"/v1/flights/{flight_id}/comprehensive-report", headers=AUTH)
        assert resp.status_code == 200
        assert resp.json()["id"] == second["id"]

    def test_get_404s_when_no_report_yet(self, client):
        flight_id = "flight-comprehensive-api-no-report"
        _ingest_flight_with_incidents(client, flight_id)
        resp = client.get(f"/v1/flights/{flight_id}/comprehensive-report", headers=AUTH)
        assert resp.status_code == 404

    def test_file_endpoint_streams_pdf(self, client, monkeypatch):
        monkeypatch.setattr("app.analytics._try_model_report", lambda *a, **k: None)
        flight_id = "flight-comprehensive-api-file"
        _ingest_flight_with_incidents(client, flight_id)
        created = client.post(f"/v1/flights/{flight_id}/comprehensive-report", headers=AUTH).json()

        resp = client.get(f"/v1/comprehensive-reports/{created['id']}/file", headers=AUTH)
        assert resp.status_code == 200
        assert resp.headers["content-type"] == "application/pdf"
        assert resp.content.startswith(b"%PDF")

    def test_file_endpoint_404s_for_unknown_report(self, client):
        resp = client.get("/v1/comprehensive-reports/does-not-exist/file", headers=AUTH)
        assert resp.status_code == 404
