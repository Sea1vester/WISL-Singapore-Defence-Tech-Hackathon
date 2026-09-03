"""
CRUD helpers for visual_records.

All file I/O is relative to settings.visuals_dir.
Callers pass raw bytes; this module handles path allocation and DB insertion.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from app.config import settings
from app.db import db_session
from app.schemas import new_id

ALLOWED_KINDS = {"cesium_screenshot", "sensor_chart", "camera_frame", "custom"}
ALLOWED_SOURCES = {"replay", "parser", "worker", "user"}


def _visuals_root() -> Path:
    root = Path(settings.visuals_dir).expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    return root


def _flight_dir(flight_id: str) -> Path:
    d = _visuals_root() / flight_id
    d.mkdir(parents=True, exist_ok=True)
    return d


def save_visual(
    *,
    flight_id: str,
    recorded_at: str,
    kind: str,
    data: bytes,
    mime_type: str = "image/png",
    extension: str = "png",
    caption: str | None = None,
    source: str | None = None,
    incident_id: str | None = None,
    record_id: str | None = None,
) -> dict[str, Any]:
    """
    Write bytes to disk and insert a visual_records row.
    Returns the full row as a dict.
    """
    if kind not in ALLOWED_KINDS:
        raise ValueError(f"Invalid kind: {kind!r}. Must be one of {ALLOWED_KINDS}")
    if source is not None and source not in ALLOWED_SOURCES:
        raise ValueError(f"Invalid source: {source!r}. Must be one of {ALLOWED_SOURCES}")

    visual_id = new_id()
    filename = f"{visual_id}.{extension}"
    file_path = _flight_dir(flight_id) / filename
    file_path.write_bytes(data)

    # stored_path is relative to visuals_dir so it stays portable
    stored_path = f"{flight_id}/{filename}"
    size_bytes = len(data)

    with db_session() as conn:
        conn.execute(
            """
            INSERT INTO visual_records (
              id, flight_id, incident_id, record_id, recorded_at,
              kind, stored_path, mime_type, size_bytes, caption, source
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                visual_id,
                flight_id,
                incident_id,
                record_id,
                recorded_at,
                kind,
                stored_path,
                mime_type,
                size_bytes,
                caption,
                source,
            ),
        )
    return get_visual(visual_id)  # type: ignore[return-value]


def get_visual(visual_id: str) -> dict[str, Any] | None:
    """Return a visual_records row as a dict, or None if not found."""
    with db_session() as conn:
        row = conn.execute(
            "SELECT * FROM visual_records WHERE id = ?", (visual_id,)
        ).fetchone()
    return dict(row) if row else None


def list_visuals(
    flight_id: str,
    *,
    kind: str | None = None,
    incident_id: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> list[dict[str, Any]]:
    """List visual records for a flight, optionally filtered."""
    clauses = ["flight_id = ?"]
    params: list[Any] = [flight_id]
    if kind is not None:
        clauses.append("kind = ?")
        params.append(kind)
    if incident_id is not None:
        clauses.append("incident_id = ?")
        params.append(incident_id)
    where = " AND ".join(clauses)
    params.extend([limit, offset])
    with db_session() as conn:
        rows = conn.execute(
            f"SELECT * FROM visual_records WHERE {where} ORDER BY recorded_at ASC LIMIT ? OFFSET ?",
            params,
        ).fetchall()
    return [dict(r) for r in rows]


def resolve_visual_path(visual_id: str) -> Path | None:
    """
    Return the absolute path to the file for a visual record, or None if not found.
    Does not check whether the file actually exists on disk.
    """
    row = get_visual(visual_id)
    if row is None:
        return None
    return _visuals_root() / row["stored_path"]


def delete_visual(visual_id: str) -> bool:
    """
    Delete a visual record and its file from disk.
    Returns True if the record existed and was removed.
    """
    row = get_visual(visual_id)
    if row is None:
        return False
    file_path = _visuals_root() / row["stored_path"]
    try:
        file_path.unlink(missing_ok=True)
    except OSError:
        pass
    with db_session() as conn:
        conn.execute("DELETE FROM visual_records WHERE id = ?", (visual_id,))
    return True


def delete_visuals_for_flight(flight_id: str) -> int:
    """
    Delete all visual records and files for a flight.
    Returns the number of records deleted.
    """
    rows = list_visuals(flight_id, limit=10_000)
    for row in rows:
        file_path = _visuals_root() / row["stored_path"]
        try:
            file_path.unlink(missing_ok=True)
        except OSError:
            pass
    # Remove the flight directory if empty
    flight_dir = _visuals_root() / flight_id
    try:
        if flight_dir.is_dir() and not any(flight_dir.iterdir()):
            flight_dir.rmdir()
    except OSError:
        pass
    count = len(rows)
    if count:
        with db_session() as conn:
            conn.execute("DELETE FROM visual_records WHERE flight_id = ?", (flight_id,))
    return count
