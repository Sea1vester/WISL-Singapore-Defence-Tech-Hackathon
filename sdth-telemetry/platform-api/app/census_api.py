"""
FastAPI router for frame_census.

Endpoints:
  POST /v1/flights/{flight_id}/census  - attach census to a camera_frame visual
  GET  /v1/flights/{flight_id}/census  - list census rows for a flight (prefetch)
  GET  /v1/visuals/{visual_id}/census  - get census for one visual
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from app.auth import require_api_key
from app.census import attach_census, get_frame_census, list_frame_census

router = APIRouter(tags=["census"])


class CensusPayload(BaseModel):
    class_counts: dict[str, int]
    cars: int
    people: int


class AttachCensusRequest(BaseModel):
    visual_id: str = Field(..., description="visual_records.id for the camera_frame")
    recorded_at: str = Field(..., description="ISO-8601 timestamp matching the frame")
    census: CensusPayload


class FrameCensusResponse(BaseModel):
    visual_id: str
    flight_id: str
    recorded_at: str
    census: CensusPayload
    created_at: str | None = None


class FrameCensusListResponse(BaseModel):
    flight_id: str
    items: list[FrameCensusResponse]
    total: int


def _to_response(row: dict[str, Any]) -> FrameCensusResponse:
    return FrameCensusResponse(
        visual_id=row["visual_id"],
        flight_id=row["flight_id"],
        recorded_at=row["recorded_at"],
        census=CensusPayload(**row["census"]),
        created_at=row.get("created_at"),
    )


@router.post(
    "/v1/flights/{flight_id}/census",
    response_model=FrameCensusResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Attach a frame census to a camera_frame visual",
)
def post_frame_census(
    flight_id: str,
    body: AttachCensusRequest,
    _: str = Depends(require_api_key),
) -> FrameCensusResponse:
    try:
        row = attach_census(
            flight_id=flight_id,
            recorded_at=body.recorded_at,
            census=body.census.model_dump(),
            visual_id=body.visual_id,
        )
    except KeyError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc
    return _to_response(row)


@router.get(
    "/v1/flights/{flight_id}/census",
    response_model=FrameCensusListResponse,
    summary="List frame census rows for a flight (replay prefetch)",
)
def get_flight_census(
    flight_id: str,
    _: str = Depends(require_api_key),
) -> FrameCensusListResponse:
    items = list_frame_census(flight_id)
    return FrameCensusListResponse(
        flight_id=flight_id,
        items=[_to_response(row) for row in items],
        total=len(items),
    )


@router.get(
    "/v1/visuals/{visual_id}/census",
    response_model=FrameCensusResponse,
    summary="Get frame census for a single visual",
)
def get_visual_census(
    visual_id: str,
    _: str = Depends(require_api_key),
) -> FrameCensusResponse:
    row = get_frame_census(visual_id)
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Frame census not found",
        )
    return _to_response(row)
