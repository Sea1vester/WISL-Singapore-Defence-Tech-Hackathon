"""Tests for detect_frame: VisDrone classes, {class, conf, xywh}, no track ids."""
from __future__ import annotations

from pathlib import Path

import pytest

from sdth_vision.finetune import DEFAULT_BASE_WEIGHTS
from sdth_vision.infer import (
    class_name,
    detect_frame,
    detections_have_track_ids,
    format_detections,
    normalize_detection,
)
from sdth_vision.visdrone import VISDRONE_CLASS_NAMES

FIXTURE_IMAGE = (
    Path(__file__).parent / "fixtures" / "visdrone_det" / "images" / "sample_0001.jpg"
)


def _stub_predictor(_path: Path, _conf: float, _imgsz: int):
    # Two VisDrone objects; indices 0=pedestrian, 3=car.
    return [
        (3, 0.91, (50.0, 40.0, 16.0, 12.0)),
        (0, 0.77, (20.0, 20.0, 20.0, 20.0)),
    ]


def test_class_name_maps_ten_visdrone_indices():
    assert [class_name(i) for i in range(10)] == list(VISDRONE_CLASS_NAMES)


def test_normalize_detection_schema_has_no_track_id():
    det = normalize_detection(3, 0.5, (1.0, 2.0, 3.0, 4.0))
    assert det == {"class": "car", "conf": 0.5, "xywh": (1.0, 2.0, 3.0, 4.0)}
    assert set(det.keys()) == {"class", "conf", "xywh"}


def test_format_detections_uses_visdrone_names():
    dets = format_detections(
        [
            (1, 0.4, (10.0, 10.0, 5.0, 5.0)),  # people
            ("bus", 0.6, (0.0, 0.0, 8.0, 8.0)),
        ]
    )
    assert dets[0]["class"] == "people"
    assert dets[1]["class"] == "bus"


def test_detect_frame_with_stub_predictor_is_deterministic():
    a = detect_frame(FIXTURE_IMAGE, predictor=_stub_predictor)
    b = detect_frame(FIXTURE_IMAGE, predictor=_stub_predictor)
    assert a == b
    assert a[0]["class"] == "car"
    assert a[0]["conf"] == 0.91
    assert a[1]["class"] == "pedestrian"
    assert not detections_have_track_ids(a)
    for det in a:
        assert set(det.keys()) == {"class", "conf", "xywh"}
        assert len(det["xywh"]) == 4


def test_detect_frame_default_weights_are_yolov8n_coco():
    # API default stays YOLOv8n COCO base (finetuned .pt not checked in).
    assert DEFAULT_BASE_WEIGHTS == "yolov8n.pt"


def test_detect_frame_missing_image_raises(tmp_path: Path):
    with pytest.raises(FileNotFoundError):
        detect_frame(tmp_path / "nope.jpg", predictor=_stub_predictor)


def test_detect_frame_without_ultralytics_requires_predictor():
    import importlib.util

    if importlib.util.find_spec("ultralytics") is not None:
        pytest.skip("ultralytics installed; stub path covered elsewhere")
    with pytest.raises(RuntimeError, match="ultralytics"):
        detect_frame(FIXTURE_IMAGE)
