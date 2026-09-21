"""Tests for ingest_camera_frames: existing visuals POST, camera_frame + worker JPEG."""
from __future__ import annotations

from pathlib import Path

import httpx
import pytest

from sdth_vision.client import ingest_camera_frames

# Tiny JFIF so CI does not need VisDrone.
MINI_JPEG = (
    b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00"
    b"\xff\xd9"
)


def _mock_transport(captured: list[httpx.Request]) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        body = request.content
        return httpx.Response(
            201,
            json={
                "id": f"vis-{len(captured)}",
                "flight_id": "flight-1",
                "kind": "camera_frame",
                "source": "worker",
                "mime_type": "image/jpeg",
                "recorded_at": request.url.params.get("recorded_at"),
                "stored_path": f"flight-1/vis-{len(captured)}.jpg",
                "size_bytes": len(body),
            },
        )

    return httpx.MockTransport(handler)


def test_ingest_posts_camera_frame_jpeg_with_worker_source(tmp_path: Path):
    captured: list[httpx.Request] = []
    frame_a = tmp_path / "a.jpg"
    frame_b = tmp_path / "b.jpg"
    frame_a.write_bytes(MINI_JPEG)
    frame_b.write_bytes(MINI_JPEG + b"\x00")

    with httpx.Client(
        transport=_mock_transport(captured),
        base_url="http://api.test",
    ) as client:
        rows = ingest_camera_frames(
            "flight-1",
            [frame_a, frame_b],
            ["2026-07-11T10:00:00Z", "2026-07-11T10:00:01Z"],
            base_url="http://api.test",
            api_key="test-key",
            client=client,
        )

    assert len(rows) == 2
    assert len(captured) == 2

    for req, ts in zip(captured, ["2026-07-11T10:00:00Z", "2026-07-11T10:00:01Z"]):
        assert req.method == "POST"
        assert req.url.path == "/v1/flights/flight-1/visuals"
        assert req.url.params["kind"] == "camera_frame"
        assert req.url.params["source"] == "worker"
        assert req.url.params["recorded_at"] == ts
        assert req.headers["Authorization"] == "Bearer test-key"
        content_type = req.headers["Content-Type"]
        assert content_type.startswith("multipart/form-data")
        body = req.content
        assert b"image/jpeg" in body
        assert b"\xff\xd8" in body

    assert rows[0]["kind"] == "camera_frame"
    assert rows[0]["source"] == "worker"


def test_ingest_accepts_raw_jpeg_bytes():
    captured: list[httpx.Request] = []
    with httpx.Client(
        transport=_mock_transport(captured),
        base_url="http://api.test",
    ) as client:
        rows = ingest_camera_frames(
            "flight-1",
            [MINI_JPEG],
            ["2026-07-11T10:00:22Z"],
            base_url="http://api.test",
            api_key="k",
            client=client,
        )
    assert len(rows) == 1
    assert captured[0].url.params["kind"] == "camera_frame"


def test_ingest_rejects_length_mismatch():
    with pytest.raises(ValueError, match="length mismatch"):
        ingest_camera_frames(
            "flight-1",
            [MINI_JPEG],
            ["2026-07-11T10:00:00Z", "2026-07-11T10:00:01Z"],
            base_url="http://api.test",
            api_key="k",
        )


def test_ingest_rejects_empty_file(tmp_path: Path):
    empty = tmp_path / "empty.jpg"
    empty.write_bytes(b"")
    with pytest.raises(ValueError, match="empty"):
        ingest_camera_frames(
            "flight-1",
            [empty],
            ["2026-07-11T10:00:00Z"],
            base_url="http://api.test",
            api_key="k",
        )
