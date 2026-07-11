import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.main import app


@pytest.fixture()
def client(tmp_path, monkeypatch):
    db_path = tmp_path / "test.db"
    monkeypatch.setattr(settings, "database_path", str(db_path))
    monkeypatch.setattr(settings, "ingest_api_keys", "test-key")

    def noop_enqueue(_job_id: str) -> None:
        return None

    monkeypatch.setattr("app.ingest.enqueue_translation_job", noop_enqueue)

    with TestClient(app) as test_client:
        yield test_client


def test_health(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_ingest_requires_auth(client):
    payload = json.loads(Path(__file__).resolve().parents[2].joinpath("fixtures/sample_l1.json").read_text())
    response = client.post("/v1/telemetry/ingest", json=payload)
    assert response.status_code == 401


def test_ingest_accepts_payload(client):
    payload = json.loads(Path(__file__).resolve().parents[2].joinpath("fixtures/sample_l1.json").read_text())
    response = client.post(
        "/v1/telemetry/ingest",
        json=payload,
        headers={"Authorization": "Bearer test-key"},
    )
    assert response.status_code == 202
    body = response.json()
    assert body["status"] == "accepted"
    assert body["ingest_id"]
    assert body["job_id"]

    status_resp = client.get(
        f"/v1/ingest/{body['ingest_id']}/status",
        headers={"Authorization": "Bearer test-key"},
    )
    assert status_resp.status_code == 200
    assert status_resp.json()["status"] == "pending"


def test_list_flights_after_ingest(client):
    payload = json.loads(Path(__file__).resolve().parents[2].joinpath("fixtures/sample_l1.json").read_text())
    client.post(
        "/v1/telemetry/ingest",
        json=payload,
        headers={"Authorization": "Bearer test-key"},
    )
    response = client.get("/v1/flights", headers={"Authorization": "Bearer test-key"})
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 1
    assert data["items"][0]["id"] == payload["flight_id"]
