"""
FastAPI router for visual_records.

Endpoints:
  GET    /v1/flights/{flight_id}/visuals          - list metadata
  POST   /v1/flights/{flight_id}/visuals          - upload a visual (multipart)
  GET    /v1/visuals/{visual_id}                  - get single record metadata
  GET    /v1/visuals/{visual_id}/file             - stream the actual file
  DELETE /v1/visuals/{visual_id}                  - remove record + file
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, status
from fastapi.responses import FileResponse
from pydantic import BaseModel

from app.auth import require_api_key
from app.visuals import (
    delete_visual,
    get_visual,
    list_visuals,
    resolve_visual_path,
    save_visual,
    ALLOWED_KINDS,
    ALLOWED_SOURCES,
)

router = APIRouter(tags=["visuals"])

_MIME_TO_EXT = {
    "image/png": "png",
    "image/jpeg": "jpg",
    "image/gif": "gif",
    "image/webp": "webp",
}


# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------

class VisualRecordResponse(BaseModel):
    id: str
    flight_id: str
    incident_id: str | None = None
    record_id: str | None = None
    recorded_at: str
    kind: str
    stored_path: str
    mime_type: str
    size_bytes: int | None = None
    caption: str | None = None
    source: str | None = None
    created_at: str | None = None


class VisualsListResponse(BaseModel):
    items: list[VisualRecordResponse]
    total: int
    flight_id: str


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _row_to_response(row: dict[str, Any]) -> VisualRecordResponse:
    return VisualRecordResponse(**row)


def _require_visual(visual_id: str) -> dict[str, Any]:
    row = get_visual(visual_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Visual record not found")
    return row


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get(
    "/v1/flights/{flight_id}/visuals",
    response_model=VisualsListResponse,
    summary="List visual records for a flight",
)
def list_flight_visuals(
    flight_id: str,
    kind: str | None = Query(default=None, description=f"Filter by kind: {', '.join(sorted(ALLOWED_KINDS))}"),
    incident_id: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    _: str = Depends(require_api_key),
) -> VisualsListResponse:
    if kind is not None and kind not in ALLOWED_KINDS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid kind '{kind}'. Must be one of: {sorted(ALLOWED_KINDS)}",
        )
    rows = list_visuals(flight_id, kind=kind, incident_id=incident_id, limit=limit, offset=offset)
    return VisualsListResponse(
        items=[_row_to_response(r) for r in rows],
        total=len(rows),
        flight_id=flight_id,
    )


@router.post(
    "/v1/flights/{flight_id}/visuals",
    response_model=VisualRecordResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Upload a visual record for a flight",
)
async def upload_visual(
    flight_id: str,
    file: UploadFile,
    kind: str = Query(description=f"One of: {', '.join(sorted(ALLOWED_KINDS))}"),
    recorded_at: str = Query(description="ISO-8601 timestamp this visual corresponds to"),
    caption: str | None = Query(default=None),
    source: str | None = Query(default=None, description=f"One of: {', '.join(sorted(ALLOWED_SOURCES))}"),
    incident_id: str | None = Query(default=None),
    record_id: str | None = Query(default=None),
    _: str = Depends(require_api_key),
) -> VisualRecordResponse:
    if kind not in ALLOWED_KINDS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid kind '{kind}'. Must be one of: {sorted(ALLOWED_KINDS)}",
        )
    if source is not None and source not in ALLOWED_SOURCES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid source '{source}'. Must be one of: {sorted(ALLOWED_SOURCES)}",
        )

    mime_type = file.content_type or "image/png"
    extension = _MIME_TO_EXT.get(mime_type, "bin")
    data = await file.read()

    if not data:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="File is empty")

    try:
        row = save_visual(
            flight_id=flight_id,
            recorded_at=recorded_at,
            kind=kind,
            data=data,
            mime_type=mime_type,
            extension=extension,
            caption=caption,
            source=source,
            incident_id=incident_id,
            record_id=record_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc

    return _row_to_response(row)


@router.get(
    "/v1/visuals/{visual_id}",
    response_model=VisualRecordResponse,
    summary="Get metadata for a single visual record",
)
def get_visual_metadata(
    visual_id: str,
    _: str = Depends(require_api_key),
) -> VisualRecordResponse:
    row = _require_visual(visual_id)
    return _row_to_response(row)


@router.get(
    "/v1/visuals/{visual_id}/file",
    summary="Stream the visual file",
)
def get_visual_file(
    visual_id: str,
    _: str = Depends(require_api_key),
) -> FileResponse:
    row = _require_visual(visual_id)
    path = resolve_visual_path(visual_id)
    if path is None or not path.exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Visual file not found on disk")
    return FileResponse(
        path=str(path),
        media_type=row["mime_type"],
        filename=path.name,
    )


@router.delete(
    "/v1/visuals/{visual_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a visual record and its file",
)
def delete_visual_record(
    visual_id: str,
    _: str = Depends(require_api_key),
) -> None:
    _require_visual(visual_id)  # 404 if missing
    delete_visual(visual_id)
