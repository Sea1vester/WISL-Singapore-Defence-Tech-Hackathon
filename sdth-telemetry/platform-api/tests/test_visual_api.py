"""
Phase 2 tests for the visual_records HTTP endpoints.
"""
from __future__ import annotations

import io

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.main import app

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "database_path", str(tmp_path / "test.db"))
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


AUTH = {"Authorization": "Bearer test-key"}
PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100  # fake PNG


def _create_flight(client) -> str:
    """Insert a flight via the ingest endpoint and return flight_id."""
    import uuid
    flight_id = str(uuid.uuid4())
    resp = client.post(
        "/v1/telemetry/ingest",
        json={
            "flight_id": flight_id,
            "timestamp_utc": "2026-01-01T00:00:00Z",
            "source": "test-parser",
            "records": [{"lat": 1.35, "lon": 103.82}],
        },
        headers=AUTH,
    )
    assert resp.status_code in (200, 202), resp.text
    return flight_id


def _upload_visual(client, flight_id: str, kind: str = "sensor_chart") -> dict:
    resp = client.post(
        f"/v1/flights/{flight_id}/visuals",
        params={
            "kind": kind,
            "recorded_at": "2026-01-01T10:00:00Z",
            "source": "worker",
            "caption": "Test chart",
        },
        files={"file": ("chart.png", io.BytesIO(PNG_BYTES), "image/png")},
        headers=AUTH,
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


# ---------------------------------------------------------------------------
# POST /v1/flights/{flight_id}/visuals
# ---------------------------------------------------------------------------

class TestUploadVisual:
    def test_upload_returns_201_with_metadata(self, client):
        fid = _create_flight(client)
        body = _upload_visual(client, fid)

        assert body["id"]
        assert body["flight_id"] == fid
        assert body["kind"] == "sensor_chart"
        assert body["mime_type"] == "image/png"
        assert body["size_bytes"] == len(PNG_BYTES)
        assert body["caption"] == "Test chart"
        assert body["source"] == "worker"

    def test_upload_requires_auth(self, client):
        fid = _create_flight(client)
        resp = client.post(
            f"/v1/flights/{fid}/visuals",
            params={"kind": "sensor_chart", "recorded_at": "2026-01-01T10:00:00Z"},
            files={"file": ("x.png", io.BytesIO(PNG_BYTES), "image/png")},
        )
        assert resp.status_code in (401, 403)

    def test_upload_rejects_invalid_kind(self, client):
        fid = _create_flight(client)
        resp = client.post(
            f"/v1/flights/{fid}/visuals",
            params={"kind": "video_clip", "recorded_at": "2026-01-01T10:00:00Z"},
            files={"file": ("x.png", io.BytesIO(PNG_BYTES), "image/png")},
            headers=AUTH,
        )
        assert resp.status_code == 422

    def test_upload_rejects_empty_file(self, client):
        fid = _create_flight(client)
        resp = client.post(
            f"/v1/flights/{fid}/visuals",
            params={"kind": "sensor_chart", "recorded_at": "2026-01-01T10:00:00Z"},
            files={"file": ("empty.png", io.BytesIO(b""), "image/png")},
            headers=AUTH,
        )
        assert resp.status_code == 422

    def test_upload_all_visual_kinds(self, client):
        fid = _create_flight(client)
        for kind in ("cesium_screenshot", "sensor_chart", "camera_frame", "custom"):
            resp = client.post(
                f"/v1/flights/{fid}/visuals",
                params={"kind": kind, "recorded_at": "2026-01-01T10:00:00Z"},
                files={"file": ("x.png", io.BytesIO(PNG_BYTES), "image/png")},
                headers=AUTH,
            )
            assert resp.status_code == 201, f"kind={kind}: {resp.text}"


# ---------------------------------------------------------------------------
# GET /v1/flights/{flight_id}/visuals
# ---------------------------------------------------------------------------

class TestListVisuals:
    def test_list_empty_for_new_flight(self, client):
        fid = _create_flight(client)
        resp = client.get(f"/v1/flights/{fid}/visuals", headers=AUTH)
        assert resp.status_code == 200
        body = resp.json()
        assert body["items"] == []
        assert body["total"] == 0
        assert body["flight_id"] == fid

    def test_list_returns_uploaded_visuals(self, client):
        fid = _create_flight(client)
        _upload_visual(client, fid, kind="sensor_chart")
        _upload_visual(client, fid, kind="cesium_screenshot")

        resp = client.get(f"/v1/flights/{fid}/visuals", headers=AUTH)
        assert resp.status_code == 200
        assert resp.json()["total"] == 2

    def test_list_filters_by_kind(self, client):
        fid = _create_flight(client)
        _upload_visual(client, fid, kind="sensor_chart")
        _upload_visual(client, fid, kind="cesium_screenshot")

        resp = client.get(f"/v1/flights/{fid}/visuals?kind=sensor_chart", headers=AUTH)
        assert resp.status_code == 200
        items = resp.json()["items"]
        assert len(items) == 1
        assert items[0]["kind"] == "sensor_chart"

    def test_list_rejects_invalid_kind_filter(self, client):
        fid = _create_flight(client)
        resp = client.get(f"/v1/flights/{fid}/visuals?kind=bad_kind", headers=AUTH)
        assert resp.status_code == 422

    def test_list_requires_auth(self, client):
        fid = _create_flight(client)
        resp = client.get(f"/v1/flights/{fid}/visuals")
        assert resp.status_code in (401, 403)

    def test_list_pagination(self, client):
        fid = _create_flight(client)
        for _ in range(5):
            _upload_visual(client, fid)

        page = client.get(f"/v1/flights/{fid}/visuals?limit=2&offset=2", headers=AUTH)
        assert page.status_code == 200
        assert len(page.json()["items"]) == 2


# ---------------------------------------------------------------------------
# GET /v1/visuals/{visual_id}
# ---------------------------------------------------------------------------

class TestGetVisualMetadata:
    def test_returns_metadata(self, client):
        fid = _create_flight(client)
        created = _upload_visual(client, fid)
        vid = created["id"]

        resp = client.get(f"/v1/visuals/{vid}", headers=AUTH)
        assert resp.status_code == 200
        assert resp.json()["id"] == vid

    def test_404_for_missing(self, client):
        resp = client.get("/v1/visuals/no-such-id", headers=AUTH)
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# GET /v1/visuals/{visual_id}/file
# ---------------------------------------------------------------------------

class TestGetVisualFile:
    def test_returns_file_bytes(self, client):
        fid = _create_flight(client)
        created = _upload_visual(client, fid)
        vid = created["id"]

        resp = client.get(f"/v1/visuals/{vid}/file", headers=AUTH)
        assert resp.status_code == 200
        assert resp.content == PNG_BYTES
        assert resp.headers["content-type"].startswith("image/png")

    def test_404_for_missing(self, client):
        resp = client.get("/v1/visuals/no-such-id/file", headers=AUTH)
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# DELETE /v1/visuals/{visual_id}
# ---------------------------------------------------------------------------

class TestDeleteVisual:
    def test_delete_returns_204(self, client):
        fid = _create_flight(client)
        created = _upload_visual(client, fid)
        vid = created["id"]

        resp = client.delete(f"/v1/visuals/{vid}", headers=AUTH)
        assert resp.status_code == 204

        # Metadata and file should be gone
        assert client.get(f"/v1/visuals/{vid}", headers=AUTH).status_code == 404
        assert client.get(f"/v1/visuals/{vid}/file", headers=AUTH).status_code == 404

    def test_delete_404_for_missing(self, client):
        resp = client.delete("/v1/visuals/no-such-id", headers=AUTH)
        assert resp.status_code == 404

    def test_deleted_visual_no_longer_in_list(self, client):
        fid = _create_flight(client)
        v1 = _upload_visual(client, fid)
        v2 = _upload_visual(client, fid)

        client.delete(f"/v1/visuals/{v1['id']}", headers=AUTH)

        resp = client.get(f"/v1/flights/{fid}/visuals", headers=AUTH)
        ids = [item["id"] for item in resp.json()["items"]]
        assert v1["id"] not in ids
        assert v2["id"] in ids
