"""Tests for frame census: 10 VisDrone class counts + HUD cars/people roll-ups."""
from __future__ import annotations

import pytest

from sdth_vision.census import (
    census,
    count_classes,
    empty_class_counts,
    format_census_line,
    roll_hud,
)
from sdth_vision.visdrone import (
    CARS_CLASSES,
    PEOPLE_CLASSES,
    VISDRONE_CLASS_NAMES,
)


def test_empty_class_counts_has_exactly_ten_visdrone_names():
    counts = empty_class_counts()
    assert list(counts.keys()) == list(VISDRONE_CLASS_NAMES)
    assert len(counts) == 10
    assert all(v == 0 for v in counts.values())
    assert "ignored" not in counts


def test_count_classes_tallies_detections():
    dets = [
        {"class": "car", "conf": 0.9, "xywh": (1, 1, 1, 1)},
        {"class": "car", "conf": 0.8, "xywh": (2, 2, 2, 2)},
        {"class": "pedestrian", "conf": 0.7, "xywh": (3, 3, 3, 3)},
        {"class": "bicycle", "conf": 0.6, "xywh": (4, 4, 4, 4)},
    ]
    counts = count_classes(dets)
    assert counts["car"] == 2
    assert counts["pedestrian"] == 1
    assert counts["bicycle"] == 1
    assert counts["van"] == 0
    assert sum(counts.values()) == 4


def test_count_classes_rejects_unknown_name():
    with pytest.raises(ValueError, match="unknown"):
        count_classes([{"class": "ignored", "conf": 1.0, "xywh": (0, 0, 1, 1)}])


def test_roll_hud_cars_and_people_sets():
    assert CARS_CLASSES == frozenset({"car", "van", "truck", "bus"})
    assert PEOPLE_CLASSES == frozenset({"pedestrian", "people"})

    counts = empty_class_counts()
    counts.update(
        {
            "car": 2,
            "van": 1,
            "truck": 1,
            "bus": 1,
            "pedestrian": 3,
            "people": 2,
            "bicycle": 9,  # not in HUD roll-ups
            "motor": 4,
        }
    )
    cars, people = roll_hud(counts)
    assert cars == 5
    assert people == 5


def test_census_schema_and_rollups():
    dets = [
        {"class": "truck", "conf": 0.9, "xywh": (0, 0, 1, 1)},
        {"class": "bus", "conf": 0.8, "xywh": (0, 0, 1, 1)},
        {"class": "people", "conf": 0.7, "xywh": (0, 0, 1, 1)},
        {"class": "pedestrian", "conf": 0.6, "xywh": (0, 0, 1, 1)},
        {"class": "motor", "conf": 0.5, "xywh": (0, 0, 1, 1)},
    ]
    result = census(dets)
    assert set(result.keys()) == {"class_counts", "cars", "people"}
    assert list(result["class_counts"].keys()) == list(VISDRONE_CLASS_NAMES)
    assert result["cars"] == 2  # truck + bus
    assert result["people"] == 2  # people + pedestrian
    assert result["class_counts"]["motor"] == 1
    assert result["class_counts"]["car"] == 0


def test_census_empty_detections():
    result = census([])
    assert result["cars"] == 0
    assert result["people"] == 0
    assert all(v == 0 for v in result["class_counts"].values())


def test_format_census_line_matches_hud():
    assert format_census_line(3, 7) == "cars 3 · people 7"
