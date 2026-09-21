"""HTTP client wrappers for the vision sidecar.

Uses the existing visuals upload path. Does not invent a new ingest API.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping, Sequence

import httpx

FrameInput = Path | str | bytes


def _read_jpeg(item: FrameInput) -> bytes:
    if isinstance(item, bytes):
        data = item
    else:
        data = Path(item).read_bytes()
    if not data:
        raise ValueError("camera frame file is empty")
    return data


def ingest_camera_frames(
    flight_id: str,
    files: Sequence[FrameInput],
    timestamps: Sequence[str],
    *,
    base_url: str,
    api_key: str,
    client: httpx.Client | None = None,
) -> list[dict[str, Any]]:
    """
    Upload JPEG camera frames via POST /v1/flights/{id}/visuals.

    Always uses kind=camera_frame and source=worker.
    ``files`` and ``timestamps`` must be the same length (one recorded_at per frame).
    """
    if len(files) != len(timestamps):
        raise ValueError(
            f"files and timestamps length mismatch: {len(files)} != {len(timestamps)}"
        )
    if not flight_id:
        raise ValueError("flight_id is required")

    own_client = client is None
    http = client or httpx.Client(base_url=base_url.rstrip("/"), timeout=60.0)
    headers = {"Authorization": f"Bearer {api_key}"}
    results: list[dict[str, Any]] = []

    try:
        for index, (frame, recorded_at) in enumerate(zip(files, timestamps)):
            data = _read_jpeg(frame)
            filename = f"frame_{index:04d}.jpg"
            if isinstance(frame, (Path, str)):
                filename = Path(frame).name or filename
            response = http.post(
                f"/v1/flights/{flight_id}/visuals",
                params={
                    "kind": "camera_frame",
                    "recorded_at": recorded_at,
                    "source": "worker",
                },
                files={"file": (filename, data, "image/jpeg")},
                headers=headers,
            )
            response.raise_for_status()
            results.append(response.json())
    finally:
        if own_client:
            http.close()

    return results


def attach_census(
    flight_id: str,
    recorded_at: str,
    census: Mapping[str, Any],
    visual_id: str,
    *,
    base_url: str,
    api_key: str,
    client: httpx.Client | None = None,
) -> dict[str, Any]:
    """
    Persist a frame census via POST /v1/flights/{id}/census.

    ``census`` is the blob from ``sdth_vision.census`` (class_counts + cars/people).
    Rows land in ``frame_census`` keyed by ``visual_id``.
    """
    if not flight_id:
        raise ValueError("flight_id is required")
    if not visual_id:
        raise ValueError("visual_id is required")
    if not recorded_at:
        raise ValueError("recorded_at is required")
    if not isinstance(census, Mapping):
        raise ValueError("census must be a mapping")

    own_client = client is None
    http = client or httpx.Client(base_url=base_url.rstrip("/"), timeout=60.0)
    headers = {"Authorization": f"Bearer {api_key}"}
    try:
        response = http.post(
            f"/v1/flights/{flight_id}/census",
            json={
                "visual_id": visual_id,
                "recorded_at": recorded_at,
                "census": dict(census),
            },
            headers=headers,
        )
        response.raise_for_status()
        return response.json()
    finally:
        if own_client:
            http.close()
