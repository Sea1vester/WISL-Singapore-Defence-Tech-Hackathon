"""Tests for frame_census migration 009 and attach_census helpers/API."""
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

VISDRONE_CLASS_NAMES = (
    "pedestrian",
    "people",
    "bicycle",
    "car",
    "van",
    "truck",
    "tricycle",
    "awning-tricycle",
    "bus",
    "motor",
)


def _empty_counts(**overrides: int) -> dict[str, int]:
    counts = {name: 0 for name in VISDRONE_CLASS_NAMES}
    counts.update(overrides)
    return counts


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


def _create_flight(client: TestClient) -> str:
    import uuid

    flight_id = str(uuid.uuid4())
    resp = client.post(
        "/v1/telemetry/ingest",
        json={
            "flight_id": flight_id,
            "timestamp_utc": "2026-07-11T10:00:00Z",
            "source": "test-parser",
            "records": [{"lat": 1.35, "lon": 103.82}],
        },
        headers=AUTH,
    )
    assert resp.status_code in (200, 202), resp.text
    return flight_id


def _upload_camera_frame(client: TestClient, flight_id: str, recorded_at: str) -> dict:
    resp = client.post(
        f"/v1/flights/{flight_id}/visuals",
        params={
            "kind": "camera_frame",
            "recorded_at": recorded_at,
            "source": "worker",
        },
        files={"file": ("frame.jpg", io.BytesIO(JPEG_BYTES), "image/jpeg")},
        headers=AUTH,
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


class TestFrameCensusMigration:
    def test_frame_census_table_and_index_exist(self, client):
        from app.db import db_session

        with db_session() as conn:
            tables = {
                r["name"]
                for r in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ).fetchall()
            }
            indexes = {
                r["name"]
                for r in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='index' "
                    "AND tbl_name='frame_census'"
                ).fetchall()
            }
        assert "frame_census" in tables
        assert "idx_frame_census_flight" in indexes


class TestAttachCensusCrud:
    def test_attach_stores_ten_classes_and_hud(self, client):
        from app.census import attach_census, get_frame_census

        flight_id = _create_flight(client)
        visual = _upload_camera_frame(client, flight_id, "2026-07-11T10:00:22Z")
        census = {
            "class_counts": _empty_counts(car=2, van=1, pedestrian=3, people=1),
            "cars": 3,
            "people": 4,
        }
        row = attach_census(
            flight_id=flight_id,
            recorded_at="2026-07-11T10:00:22Z",
            census=census,
            visual_id=visual["id"],
        )
        assert row["visual_id"] == visual["id"]
        assert row["flight_id"] == flight_id
        assert row["recorded_at"] == "2026-07-11T10:00:22Z"
        assert list(row["census"]["class_counts"].keys()) == list(VISDRONE_CLASS_NAMES)
        assert row["census"]["cars"] == 3
        assert row["census"]["people"] == 4
        assert "ignored" not in row["census"]["class_counts"]

        fetched = get_frame_census(visual["id"])
        assert fetched is not None
        assert fetched["census"]["class_counts"]["car"] == 2

    def test_attach_rejects_unknown_class(self, client):
        from app.census import attach_census

        flight_id = _create_flight(client)
        visual = _upload_camera_frame(client, flight_id, "2026-07-11T10:00:22Z")
        bad = {
            "class_counts": {**_empty_counts(), "ignored": 1},
            "cars": 0,
            "people": 0,
        }
        with pytest.raises(ValueError, match="unknown"):
            attach_census(
                flight_id=flight_id,
                recorded_at="2026-07-11T10:00:22Z",
                census=bad,
                visual_id=visual["id"],
            )


class TestAttachCensusApi:
    def test_post_and_get_frame_census(self, client):
        flight_id = _create_flight(client)
        visual = _upload_camera_frame(client, flight_id, "2026-07-11T10:00:22Z")
        body = {
            "visual_id": visual["id"],
            "recorded_at": "2026-07-11T10:00:22Z",
            "census": {
                "class_counts": _empty_counts(truck=1, bus=1, pedestrian=2),
                "cars": 2,
                "people": 2,
            },
        }
        resp = client.post(
            f"/v1/flights/{flight_id}/census",
            json=body,
            headers=AUTH,
        )
        assert resp.status_code == 201, resp.text
        data = resp.json()
        assert data["visual_id"] == visual["id"]
        assert data["census"]["cars"] == 2
        assert data["census"]["people"] == 2

        listed = client.get(f"/v1/flights/{flight_id}/census", headers=AUTH)
        assert listed.status_code == 200
        payload = listed.json()
        assert payload["total"] == 1
        assert payload["items"][0]["visual_id"] == visual["id"]

        one = client.get(f"/v1/visuals/{visual['id']}/census", headers=AUTH)
        assert one.status_code == 200
        assert one.json()["census"]["class_counts"]["truck"] == 1

    def test_post_404_for_missing_visual(self, client):
        flight_id = _create_flight(client)
        resp = client.post(
            f"/v1/flights/{flight_id}/census",
            json={
                "visual_id": "missing-visual",
                "recorded_at": "2026-07-11T10:00:22Z",
                "census": {
                    "class_counts": _empty_counts(),
                    "cars": 0,
                    "people": 0,
                },
            },
            headers=AUTH,
        )
        assert resp.status_code == 404
