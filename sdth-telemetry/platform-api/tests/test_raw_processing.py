from __future__ import annotations

from pathlib import Path

from app.db import db_session
from app.worker import process_raw_upload
from tests.conftest import AUTH


DEMO_LOG = Path(__file__).parents[2] / "fixtures" / "demo" / "controller_mission_alpha.csv"


def test_raw_upload_is_parsed_server_side_and_queued_for_normalization(
    client,
    monkeypatch,
):
    response = client.post(
        "/v1/logs/upload",
        files={"file": ("controller_mission_alpha.csv", DEMO_LOG.read_bytes())},
        headers=AUTH,
    )
    upload_id = response.json()["upload_id"]
    queued_jobs: list[str] = []
    monkeypatch.setattr("app.worker.enqueue_translation_job", queued_jobs.append)

    process_raw_upload(upload_id)

    status = client.get(f"/v1/uploads/{upload_id}", headers=AUTH).json()
    assert status["status"] == "normalizing"
    assert status["flight_id"]
    assert status["ingest_id"]
    assert len(queued_jobs) == 1

    with db_session() as conn:
        event = conn.execute(
            "SELECT payload_json FROM ingest_events WHERE id = ?",
            (status["ingest_id"],),
        ).fetchone()
    assert event is not None
    assert event["payload_json"].count('"timestamp_utc"') >= 9
