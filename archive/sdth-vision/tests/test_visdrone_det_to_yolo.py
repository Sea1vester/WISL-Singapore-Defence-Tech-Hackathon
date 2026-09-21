"""Tests for visdrone_det_to_yolo: drop ignored class 0, remap 1..10 -> 0..9."""
from __future__ import annotations

from pathlib import Path

import pytest

from sdth_vision.visdrone import (
    VISDRONE_CLASS_NAMES,
    convert_annotation_file,
    jpeg_size,
    parse_visdrone_annotation_line,
    visdrone_box_to_yolo,
    visdrone_det_to_yolo,
)

FIXTURE_SPLIT = Path(__file__).parent / "fixtures" / "visdrone_det"


def test_ten_visdrone_classes_drop_ignored():
    assert len(VISDRONE_CLASS_NAMES) == 10
    assert VISDRONE_CLASS_NAMES[0] == "pedestrian"
    assert VISDRONE_CLASS_NAMES[3] == "car"
    assert VISDRONE_CLASS_NAMES[9] == "motor"
    assert visdrone_box_to_yolo(0, 0, 10, 10, 0, 100, 100) is None


def test_remap_visdrone_category_to_yolo_index():
    # category 1 (pedestrian) -> 0; category 10 (motor) -> 9
    row = visdrone_box_to_yolo(10, 20, 30, 40, 1, 100, 200)
    assert row is not None
    assert row[0] == 0
    assert row[1] == pytest.approx((10 + 15) / 100)
    assert row[2] == pytest.approx((20 + 20) / 200)
    assert row[3] == pytest.approx(30 / 100)
    assert row[4] == pytest.approx(40 / 200)

    motor = visdrone_box_to_yolo(0, 0, 10, 10, 10, 100, 100)
    assert motor is not None
    assert motor[0] == 9


def test_parse_line_drops_ignored_and_keeps_objects():
    assert parse_visdrone_annotation_line("0,0,5,5,0,0,0,0", 64, 48) is None
    car = parse_visdrone_annotation_line("32,24,16,12,1,4,0,1", 64, 48)
    assert car is not None
    assert car[0] == 3  # car
    assert car[1] == pytest.approx((32 + 8) / 64)
    assert car[2] == pytest.approx((24 + 6) / 48)


def test_visdrone_det_to_yolo_fixture_split(tmp_path: Path):
    assert FIXTURE_SPLIT.is_dir()
    out = visdrone_det_to_yolo(FIXTURE_SPLIT, tmp_path / "yolo")

    label = (out / "labels" / "sample_0001.txt").read_text(encoding="utf-8").strip().splitlines()
    assert len(label) == 3  # ignored class 0 dropped

    classes = [int(line.split()[0]) for line in label]
    assert classes == [0, 3, 1]  # pedestrian, car, people

    img_w, img_h = jpeg_size(out / "images" / "sample_0001.jpg")
    assert (img_w, img_h) == (64, 48)

    # Re-parse fixture annotation independently for numeric check
    rows = convert_annotation_file(
        FIXTURE_SPLIT / "annotations" / "sample_0001.txt",
        img_w,
        img_h,
    )
    assert len(rows) == 3
    assert rows[0][0] == 0
    assert rows[0][1] == pytest.approx((10 + 10) / 64)
    assert rows[0][2] == pytest.approx((10 + 10) / 48)

    names = (out / "classes.txt").read_text(encoding="utf-8").strip().splitlines()
    assert names == list(VISDRONE_CLASS_NAMES)


def test_visdrone_det_to_yolo_requires_images_and_annotations(tmp_path: Path):
    bad = tmp_path / "empty_split"
    bad.mkdir()
    with pytest.raises(FileNotFoundError, match="images"):
        visdrone_det_to_yolo(bad)
