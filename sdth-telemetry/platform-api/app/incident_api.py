"""HTTP API for incident indexing, patterns, and fleet reliability."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from app.auth import require_api_key
from app.brands import brand_catalog
from app.bulletins import build_mitigation_bulletin, list_bulletins
from app.db import db_session
from app.edge_bench import run_edge_benchmark
from app.incidents import index_flight, list_flight_incidents, list_patterns, reliability_report

router = APIRouter(prefix="/v1", tags=["incidents"])


class IndexIncidentsRequest(BaseModel):
    include_llm: bool = False
    llm_report: str | None = Field(default=None, description="Optional pre-generated LLM report to persist")


class IndexIncidentsResponse(BaseModel):
    flight_id: str
    brand: str
    brand_name: str
    sample_count: int
    sample_origin: str
    incident_count: int
    rule_incident_count: int
    duration_ms: int
    pattern_count: int


@router.get("/hardware/brands")
def list_hardware_brands(_: str = Depends(require_api_key)) -> dict[str, Any]:
    return {"items": brand_catalog()}


@router.post("/flights/{flight_id}/index-incidents", response_model=IndexIncidentsResponse)
def index_incidents(
    flight_id: str,
    body: IndexIncidentsRequest | None = None,
    _: str = Depends(require_api_key),
) -> IndexIncidentsResponse:
    with db_session() as conn:
        flight = conn.execute("SELECT id FROM flights WHERE id = ?", (flight_id,)).fetchone()
        if not flight:
            raise HTTPException(status_code=404, detail="Flight not found")
    payload = body or IndexIncidentsRequest()
    llm_report = payload.llm_report
    if payload.include_llm and not llm_report:
        from app.analytics import generate_llm_incident_text

        llm_report = generate_llm_incident_text(flight_id)
    try:
        result = index_flight(flight_id, include_llm_report=llm_report)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Flight not found") from exc
    return IndexIncidentsResponse(**result)


@router.get("/flights/{flight_id}/incidents")
def get_flight_incidents(
    flight_id: str,
    include_visuals: bool = Query(default=True, description="Attach visual thumbnail metadata to each incident"),
    _: str = Depends(require_api_key),
) -> dict[str, Any]:
    with db_session() as conn:
        flight = conn.execute("SELECT id FROM flights WHERE id = ?", (flight_id,)).fetchone()
        if not flight:
            raise HTTPException(status_code=404, detail="Flight not found")
    items = list_flight_incidents(flight_id)
    if include_visuals:
        from app.visuals import list_visuals

        # Build a map of incident_id -> list of visual metadata dicts
        all_visuals = list_visuals(flight_id, limit=1000)
        visuals_by_incident: dict[str | None, list[dict[str, Any]]] = {}
        for v in all_visuals:
            key = v.get("incident_id")
            visuals_by_incident.setdefault(key, []).append({
                "id": v["id"],
                "kind": v["kind"],
                "mime_type": v["mime_type"],
                "caption": v.get("caption"),
                "recorded_at": v["recorded_at"],
                "file_url": f"/v1/visuals/{v['id']}/file",
            })
        for item in items:
            incident_id = item.get("id")
            item["visuals"] = visuals_by_incident.get(incident_id, [])
    return {"flight_id": flight_id, "count": len(items), "items": items}


@router.get("/incidents/patterns")
def get_incident_patterns(
    min_flights: int = Query(2, ge=1, le=1000),
    _: str = Depends(require_api_key),
) -> dict[str, Any]:
    items = list_patterns(min_flights=min_flights)
    return {"min_flights": min_flights, "count": len(items), "items": items}


@router.get("/reliability")
def get_reliability(_: str = Depends(require_api_key)) -> dict[str, Any]:
    return reliability_report()


class CreateBulletinRequest(BaseModel):
    signature: str


@router.post("/mitigation-bulletins")
def create_mitigation_bulletin(
    body: CreateBulletinRequest,
    _: str = Depends(require_api_key),
) -> dict[str, Any]:
    try:
        return build_mitigation_bulletin(body.signature)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="No recurring pattern for that signature") from exc


@router.get("/mitigation-bulletins")
def get_mitigation_bulletins(_: str = Depends(require_api_key)) -> dict[str, Any]:
    items = list_bulletins()
    return {"count": len(items), "items": items}


@router.post("/reliability/edge-benchmark")
def edge_benchmark(
    sample_count: int = Query(2000, ge=100, le=20000),
    _: str = Depends(require_api_key),
) -> dict[str, Any]:
    return run_edge_benchmark(sample_count=sample_count)
