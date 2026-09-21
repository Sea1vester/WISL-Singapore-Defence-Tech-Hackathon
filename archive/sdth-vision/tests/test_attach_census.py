"""Tests for attach_census client: POST /v1/flights/{id}/census."""
from __future__ import annotations

import json

import httpx
import pytest

from sdth_vision.census import census, empty_class_counts
from sdth_vision.client import attach_census
from sdth_vision.visdrone import VISDRONE_CLASS_NAMES


def _mock_transport(captured: list[httpx.Request]) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        body = json.loads(request.content.decode())
        return httpx.Response(
            201,
            json={
                "visual_id": body["visual_id"],
                "flight_id": "flight-1",
                "recorded_at": body["recorded_at"],
                "census": body["census"],
                "created_at": "2026-07-11T10:00:23Z",
            },
        )

    return httpx.MockTransport(handler)


def test_attach_census_posts_frame_census_blob():
    captured: list[httpx.Request] = []
    payload = census(
        [
            {"class": "car", "conf": 0.9, "xywh": (0, 0, 1, 1)},
            {"class": "van", "conf": 0.8, "xywh": (0, 0, 1, 1)},
            {"class": "pedestrian", "conf": 0.7, "xywh": (0, 0, 1, 1)},
        ]
    )
    with httpx.Client(
        transport=_mock_transport(captured),
        base_url="http://api.test",
    ) as client:
        row = attach_census(
            "flight-1",
            "2026-07-11T10:00:22Z",
            payload,
            "vis-42",
            base_url="http://api.test",
            api_key="test-key",
            client=client,
        )

    assert len(captured) == 1
    req = captured[0]
    assert req.method == "POST"
    assert req.url.path == "/v1/flights/flight-1/census"
    assert req.headers["Authorization"] == "Bearer test-key"
    body = json.loads(req.content.decode())
    assert body["visual_id"] == "vis-42"
    assert body["recorded_at"] == "2026-07-11T10:00:22Z"
    assert list(body["census"]["class_counts"].keys()) == list(VISDRONE_CLASS_NAMES)
    assert body["census"]["cars"] == 2
    assert body["census"]["people"] == 1
    assert row["visual_id"] == "vis-42"
    assert row["census"]["cars"] == 2


def test_attach_census_rejects_missing_ids():
    empty = {
        "class_counts": empty_class_counts(),
        "cars": 0,
        "people": 0,
    }
    with pytest.raises(ValueError, match="flight_id"):
        attach_census(
            "",
            "2026-07-11T10:00:22Z",
            empty,
            "vis-1",
            base_url="http://api.test",
            api_key="k",
        )
    with pytest.raises(ValueError, match="visual_id"):
        attach_census(
            "flight-1",
            "2026-07-11T10:00:22Z",
            empty,
            "",
            base_url="http://api.test",
            api_key="k",
        )
