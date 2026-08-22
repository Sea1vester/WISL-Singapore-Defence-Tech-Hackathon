import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.main import app


@pytest.fixture()
def client(tmp_path, monkeypatch):
    db_path = tmp_path / "test.db"
    monkeypatch.setattr(settings, "database_path", str(db_path))
    monkeypatch.setattr(settings, "raw_upload_dir", str(tmp_path / "uploads"))
    monkeypatch.setattr(settings, "ingest_api_keys", "test-key")

    def noop_enqueue(_job_id: str) -> None:
        return None

    monkeypatch.setattr("app.ingest.enqueue_translation_job", noop_enqueue)
    monkeypatch.setattr("app.ingest.enqueue_raw_upload", noop_enqueue)

    with TestClient(app) as test_client:
        yield test_client


AUTH = {"Authorization": "Bearer test-key"}
