"""
CRUD helpers for frame_census.

Stores per-frame VisDrone class counts (10 classes) plus HUD cars/people roll-ups.
Does not run detection; the vision sidecar posts a finished census blob.
"""
from __future__ import annotations

import json
from typing import Any, Mapping

from app.db import db_session

# Locked VisDrone DET names (ignored class 0 already dropped upstream).
VISDRONE_CLASS_NAMES: tuple[str, ...] = (
    "pedestrian",
    "people",
    "bicycle",
    "car",
    "van",
    "truck",
    "tricycle",
    "awning-tricycle",
    "bus",
    "motor",
)


def _normalize_census(census: Mapping[str, Any]) -> dict[str, Any]:
    """Validate and normalize a census payload for storage."""
    if "class_counts" not in census:
        raise ValueError("census must include class_counts")
    class_counts = census["class_counts"]
    if not isinstance(class_counts, Mapping):
        raise ValueError("class_counts must be a mapping")
    missing = [name for name in VISDRONE_CLASS_NAMES if name not in class_counts]
    if missing:
        raise ValueError(f"class_counts missing VisDrone classes: {missing}")
    unknown = [name for name in class_counts if name not in VISDRONE_CLASS_NAMES]
    if unknown:
        raise ValueError(f"class_counts has unknown classes: {unknown}")
    if "cars" not in census or "people" not in census:
        raise ValueError("census must include cars and people HUD roll-ups")
    cars = int(census["cars"])
    people = int(census["people"])
    normalized_counts = {name: int(class_counts[name]) for name in VISDRONE_CLASS_NAMES}
    return {
        "class_counts": normalized_counts,
        "cars": cars,
        "people": people,
    }


def _row_to_dict(row: Any) -> dict[str, Any]:
    data = dict(row)
    census = json.loads(data.pop("counts_json"))
    class_counts = census.get("class_counts") or {}
    census["class_counts"] = {
        name: int(class_counts.get(name, 0)) for name in VISDRONE_CLASS_NAMES
    }
    data["census"] = census
    return data


def attach_census(
    *,
    flight_id: str,
    recorded_at: str,
    census: Mapping[str, Any],
    visual_id: str,
) -> dict[str, Any]:
    """
    Upsert a frame_census row keyed by visual_id.

    ``census`` must include class_counts (all 10 VisDrone names), cars, and people.
    """
    if not flight_id:
        raise ValueError("flight_id is required")
    if not visual_id:
        raise ValueError("visual_id is required")
    if not recorded_at:
        raise ValueError("recorded_at is required")

    payload = _normalize_census(census)
    counts_json = json.dumps(payload, separators=(",", ":"), sort_keys=True)

    with db_session() as conn:
        visual = conn.execute(
            "SELECT id, flight_id FROM visual_records WHERE id = ?",
            (visual_id,),
        ).fetchone()
        if visual is None:
            raise KeyError(f"visual_id not found: {visual_id}")
        if visual["flight_id"] != flight_id:
            raise ValueError(
                f"visual_id {visual_id} belongs to flight {visual['flight_id']}, "
                f"not {flight_id}"
            )
        conn.execute(
            """
            INSERT INTO frame_census (visual_id, flight_id, recorded_at, counts_json)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(visual_id) DO UPDATE SET
              flight_id = excluded.flight_id,
              recorded_at = excluded.recorded_at,
              counts_json = excluded.counts_json
            """,
            (visual_id, flight_id, recorded_at, counts_json),
        )
    return get_frame_census(visual_id)  # type: ignore[return-value]


def get_frame_census(visual_id: str) -> dict[str, Any] | None:
    """Return a frame_census row with parsed ``census`` dict, or None."""
    with db_session() as conn:
        row = conn.execute(
            "SELECT visual_id, flight_id, recorded_at, counts_json, created_at "
            "FROM frame_census WHERE visual_id = ?",
            (visual_id,),
        ).fetchone()
    return _row_to_dict(row) if row else None


def list_frame_census(flight_id: str) -> list[dict[str, Any]]:
    """Return all census rows for a flight ordered by recorded_at ascending."""
    with db_session() as conn:
        rows = conn.execute(
            "SELECT visual_id, flight_id, recorded_at, counts_json, created_at "
            "FROM frame_census WHERE flight_id = ? ORDER BY recorded_at ASC",
            (flight_id,),
        ).fetchall()
    return [_row_to_dict(row) for row in rows]
