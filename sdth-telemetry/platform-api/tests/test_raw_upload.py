from __future__ import annotations

import hashlib
from pathlib import Path

from app.config import settings
from tests.conftest import AUTH


def test_raw_upload_is_stored_with_generated_name_and_status(client):
    content = b"timestamps,OSD.latitude,OSD.longitude\n1,1.35,103.82\n"
    sha256 = hashlib.sha256(content).hexdigest()

    response = client.post(
        "/v1/logs/upload",
        files={"file": ("../../controller.csv", content, "text/csv")},
        headers={**AUTH, "X-WISL-SHA256": sha256},
    )

    assert response.status_code == 202, response.text
    body = response.json()
    assert body["status"] == "received"
    assert body["sha256"] == sha256
    stored = list(Path(settings.raw_upload_dir).glob("*.csv"))
    assert len(stored) == 1
    assert stored[0].name != "controller.csv"
    assert stored[0].read_bytes() == content

    status = client.get(f"/v1/uploads/{body['upload_id']}", headers=AUTH)
    assert status.status_code == 200
    assert status.json()["filename"] == "controller.csv"
    assert status.json()["size_bytes"] == len(content)


def test_raw_upload_is_idempotent_by_content_hash(client):
    content = b"same raw log"
    first = client.post(
        "/v1/logs/upload",
        files={"file": ("flight.ulg", content)},
        headers=AUTH,
    ).json()
    second = client.post(
        "/v1/logs/upload",
        files={"file": ("renamed.ulg", content)},
        headers=AUTH,
    )

    assert second.status_code == 202
    assert second.json()["duplicate"] is True
    assert second.json()["upload_id"] == first["upload_id"]


def test_raw_upload_rejects_bad_hash_extension_and_oversize(client, monkeypatch):
    bad_hash = client.post(
        "/v1/logs/upload",
        files={"file": ("flight.csv", b"content")},
        headers={**AUTH, "X-WISL-SHA256": "0" * 64},
    )
    assert bad_hash.status_code == 422

    unsupported = client.post(
        "/v1/logs/upload",
        files={"file": ("flight.exe", b"content")},
        headers=AUTH,
    )
    assert unsupported.status_code == 415

    monkeypatch.setattr(settings, "raw_upload_max_bytes", 3)
    oversized = client.post(
        "/v1/logs/upload",
        files={"file": ("flight.bin", b"four")},
        headers=AUTH,
    )
    assert oversized.status_code == 413
