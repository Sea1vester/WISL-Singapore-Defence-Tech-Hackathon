"""Frame census: per-class VisDrone counts + HUD cars/people roll-ups.

Stores counts for all 10 VisDrone classes (ignored class 0 already dropped upstream).
HUD: ``cars = car+van+truck+bus``, ``people = pedestrian+people``.
"""
from __future__ import annotations

from typing import Any, Mapping, Sequence

from sdth_vision.visdrone import (
    CARS_CLASSES,
    PEOPLE_CLASSES,
    VISDRONE_CLASS_NAMES,
)


def empty_class_counts() -> dict[str, int]:
    """Zero counts for every stored VisDrone class (10 names, no ignored)."""
    return {name: 0 for name in VISDRONE_CLASS_NAMES}


def count_classes(detections: Sequence[Mapping[str, Any]]) -> dict[str, int]:
    """
    Tally detections by VisDrone class name.

    Unknown class names raise ValueError. Returns all 10 keys (zeros included).
    """
    counts = empty_class_counts()
    for det in detections:
        name = det["class"]
        if name not in counts:
            raise ValueError(f"unknown VisDrone class name: {name!r}")
        counts[name] += 1
    return counts


def roll_hud(class_counts: Mapping[str, int]) -> tuple[int, int]:
    """Return ``(cars, people)`` HUD roll-ups from per-class counts."""
    cars = sum(int(class_counts.get(name, 0)) for name in CARS_CLASSES)
    people = sum(int(class_counts.get(name, 0)) for name in PEOPLE_CLASSES)
    return cars, people


def census(detections: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """
    Build a frame census from ``detect_frame``-style detections.

    Returns::

        {
            "class_counts": {<10 VisDrone names>: int, ...},
            "cars": int,    # car + van + truck + bus
            "people": int,  # pedestrian + people
        }
    """
    class_counts = count_classes(detections)
    cars, people = roll_hud(class_counts)
    return {
        "class_counts": class_counts,
        "cars": cars,
        "people": people,
    }


def format_census_line(cars: int, people: int) -> str:
    """HUD string for ``#censusLine``: ``cars N · people M``."""
    return f"cars {int(cars)} · people {int(people)}"
