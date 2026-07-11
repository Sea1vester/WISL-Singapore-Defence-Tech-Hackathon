import json
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import PlainTextResponse

from app.auth import require_api_key
from app.db import db_session
from app.schemas import (
    CanonicalRecordItem,
    FlightSummary,
    FlightsListResponse,
    RecordsListResponse,
)

router = APIRouter(prefix="/v1", tags=["query"])


@router.get("/flights", response_model=FlightsListResponse)
def list_flights(
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    _: str = Depends(require_api_key),
) -> FlightsListResponse:
    with db_session() as conn:
        total = conn.execute("SELECT COUNT(*) AS c FROM flights").fetchone()["c"]
        rows = conn.execute(
            """
            SELECT id, source, started_at, ended_at, created_at
            FROM flights
            ORDER BY created_at DESC
            LIMIT ? OFFSET ?
            """,
            (limit, offset),
        ).fetchall()

    items = [FlightSummary(**dict(row)) for row in rows]
    return FlightsListResponse(items=items, total=total, offset=offset, limit=limit)


@router.get("/flights/{flight_id}/records", response_model=RecordsListResponse)
def list_flight_records(
    flight_id: str,
    offset: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    from_time: str | None = Query(default=None, alias="from"),
    to_time: str | None = Query(default=None, alias="to"),
    _: str = Depends(require_api_key),
) -> RecordsListResponse:
    clauses = ["flight_id = ?"]
    params: list[object] = [flight_id]

    if from_time:
        clauses.append("recorded_at >= ?")
        params.append(from_time)
    if to_time:
        clauses.append("recorded_at <= ?")
        params.append(to_time)

    where = " AND ".join(clauses)

    with db_session() as conn:
        flight = conn.execute("SELECT id FROM flights WHERE id = ?", (flight_id,)).fetchone()
        if not flight:
            raise HTTPException(status_code=404, detail="Flight not found")

        total = conn.execute(
            f"SELECT COUNT(*) AS c FROM canonical_records WHERE {where}",
            params,
        ).fetchone()["c"]

        rows = conn.execute(
            f"""
            SELECT id, ingest_id, flight_id, recorded_at, canonical_json,
                   llm_model, validation_ok
            FROM canonical_records
            WHERE {where}
            ORDER BY recorded_at ASC
            LIMIT ? OFFSET ?
            """,
            [*params, limit, offset],
        ).fetchall()

    items = [
        CanonicalRecordItem(
            id=row["id"],
            ingest_id=row["ingest_id"],
            flight_id=row["flight_id"],
            recorded_at=row["recorded_at"],
            canonical_json=json.loads(row["canonical_json"]),
            llm_model=row["llm_model"],
            validation_ok=bool(row["validation_ok"]),
        )
        for row in rows
    ]
    return RecordsListResponse(items=items, total=total, offset=offset, limit=limit)


@router.get("/export/flights/{flight_id}.jsonl")
def export_flight_jsonl(flight_id: str, _: str = Depends(require_api_key)) -> PlainTextResponse:
    with db_session() as conn:
        flight = conn.execute("SELECT id FROM flights WHERE id = ?", (flight_id,)).fetchone()
        if not flight:
            raise HTTPException(status_code=404, detail="Flight not found")

        rows = conn.execute(
            """
            SELECT canonical_json
            FROM canonical_records
            WHERE flight_id = ? AND validation_ok = 1
            ORDER BY recorded_at ASC
            """,
            (flight_id,),
        ).fetchall()

    lines = [row["canonical_json"] for row in rows]
    body = "\n".join(lines)
    if body:
        body += "\n"
    return PlainTextResponse(
        content=body,
        media_type="application/x-ndjson",
        headers={"Content-Disposition": f'attachment; filename="{flight_id}.jsonl"'},
    )
