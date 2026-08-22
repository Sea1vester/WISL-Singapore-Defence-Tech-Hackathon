from __future__ import annotations

import hashlib
import sys
from pathlib import Path

from app.worker import process_job, process_raw_upload
from tests.conftest import AUTH


INGEST_SRC = Path(__file__).resolve().parents[3] / "sdth-ingestion pipeline" / "src"
if str(INGEST_SRC) not in sys.path:
    sys.path.insert(0, str(INGEST_SRC))

from wisl_ingest.edge.uploader import LogUploader  # noqa: E402

DEMO_ALPHA = Path(__file__).parents[2] / "fixtures" / "demo" / "controller_mission_alpha.csv"
DEMO_BRAVO = Path(__file__).parents[2] / "fixtures" / "demo" / "controller_mission_bravo.csv"


class ClientDestination:
    def __init__(self, client, *, fail_first: bool = False):
        self.client = client
        self.fail_first = fail_first
        self.attempts = 0
        self.responses = []

    def upload(self, path: Path, sha256: str) -> bool:
        self.attempts += 1
        if self.fail_first and self.attempts == 1:
            return False
        response = self.client.post(
            "/v1/logs/upload",
            files={"file": (path.name, path.read_bytes(), "text/csv")},
            headers={**AUTH, "X-WISL-SHA256": sha256},
        )
        self.responses.append(response)
        return response.status_code == 202


def test_controller_drop_uploads_processes_and_is_idempotent(client, tmp_path, monkeypatch):
    watch = tmp_path / "controller"
    watch.mkdir()
    (watch / "controller_mission_alpha.csv").write_bytes(DEMO_ALPHA.read_bytes())

    destination = ClientDestination(client)
    uploader = LogUploader(watch, destination)
    uploader.scan_once()
    first = uploader.scan_once()
    assert first["uploaded"] == 1
    assert destination.responses[0].status_code == 202
    upload_id = destination.responses[0].json()["upload_id"]

    queued: list[str] = []
    monkeypatch.setattr("app.worker.enqueue_translation_job", queued.append)

    process_raw_upload(upload_id)
    status = client.get(f"/v1/uploads/{upload_id}", headers=AUTH).json()
    assert status["status"] in {"normalizing", "detecting", "ready"}
    assert status["flight_id"]
    flight_id = status["flight_id"]

    monkeypatch.setattr(
        "app.worker.translate_with_repair",
        lambda _payload: (_ for _ in ()).throw(RuntimeError("Ollama offline")),
    )
    if queued:
        process_job(queued[0])
    ready = client.get(f"/v1/uploads/{upload_id}", headers=AUTH).json()
    assert ready["status"] == "ready"

    path = client.get(f"/v1/flights/{flight_id}/path", headers=AUTH).json()
    assert path["count"] >= 8
    incidents = client.get(f"/v1/flights/{flight_id}/incidents", headers=AUTH).json()["items"]
    assert any(item["incident_type"] == "operator_warning" for item in incidents)
    assert any(item.get("lat") is not None for item in incidents)
    report = client.get(f"/v1/flights/{flight_id}/incident-report", headers=AUTH).json()
    assert report["kind"] == "evidence_backed_incident_summary"
    assert report["model_enrichment"] == "degraded"

    duplicate = client.post(
        "/v1/logs/upload",
        files={"file": ("controller_mission_alpha.csv", DEMO_ALPHA.read_bytes(), "text/csv")},
        headers={**AUTH, "X-WISL-SHA256": hashlib.sha256(DEMO_ALPHA.read_bytes()).hexdigest()},
    )
    assert duplicate.json()["duplicate"] is True
    assert duplicate.json()["upload_id"] == upload_id


def test_failed_upload_is_retried_on_next_scan(client, tmp_path):
    watch = tmp_path / "controller"
    watch.mkdir()
    (watch / "controller_mission_bravo.csv").write_bytes(DEMO_BRAVO.read_bytes())
    destination = ClientDestination(client, fail_first=True)
    uploader = LogUploader(watch, destination)
    uploader.scan_once()
    first = uploader.scan_once()
    assert first["pending"] == 1
    second = uploader.scan_once()
    assert second["uploaded"] == 1
    assert destination.attempts == 2
    assert destination.responses[-1].status_code == 202
