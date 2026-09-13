import json

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import PlainTextResponse

from app.auth import require_api_key
from app.db import db_session
from app.path_export import (
    PATH_CONTRACT_VERSION,
    build_flight_path,
    l1_payload_to_path,
    sample_from_l2_record,
)
from app.schemas import (
    CanonicalRecordItem,
    FlightPathResponse,
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
            SELECT f.id, f.source, f.started_at, f.ended_at, f.created_at,
                (SELECT r.original_name FROM raw_uploads r WHERE r.flight_id=f.id
                 ORDER BY r.received_at LIMIT 1) AS original_filename
            FROM flights f
            ORDER BY f.created_at DESC
            LIMIT ? OFFSET ?
            """,
            (limit, offset),
        ).fetchall()

    items = [FlightSummary(**dict(row)) for row in rows]
    return FlightsListResponse(items=items, total=total, offset=offset, limit=limit)


@router.get("/flights/{flight_id}", response_model=FlightSummary)
def get_flight(
    flight_id: str,
    include_visuals: bool = Query(default=True, description="Attach visual thumbnail summary"),
    _: str = Depends(require_api_key),
) -> FlightSummary:
    with db_session() as conn:
        row = conn.execute(
            "SELECT id, source, started_at, ended_at, created_at FROM flights WHERE id = ?",
            (flight_id,),
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Flight not found")
    summary = FlightSummary(**dict(row))
    if include_visuals:
        from app.visuals import list_visuals
        visuals = list_visuals(flight_id, limit=50)
        summary.visuals = [
            {
                "id": v["id"],
                "kind": v["kind"],
                "mime_type": v["mime_type"],
                "caption": v.get("caption"),
                "recorded_at": v["recorded_at"],
                "file_url": f"/v1/visuals/{v['id']}/file",
            }
            for v in visuals
        ]
    return summary


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


@router.get("/flights/{flight_id}/path", response_model=FlightPathResponse)
def get_flight_path(
    flight_id: str,
    stride: int = Query(1, ge=1, le=1000),
    max_samples: int = Query(20000, ge=1, le=100000),
    prefer: str = Query("auto", pattern="^(auto|l2|l1)$"),
    _: str = Depends(require_api_key),
) -> FlightPathResponse:
    """
    Stable 3D-viz handoff.

    Returns ordered samples: ``{t, lat, lon, alt_m, ...}``.
    Prefers L2 canonical records; falls back to stored L1 ingest payloads
    so visualization works before LLM translation finishes.
    """
    with db_session() as conn:
        flight = conn.execute(
            "SELECT id, source FROM flights WHERE id = ?",
            (flight_id,),
        ).fetchone()
        if not flight:
            raise HTTPException(status_code=404, detail="Flight not found")

        samples: list[dict] = []
        data_origin = "l2_canonical"
        frame = "wgs84"

        use_l2 = prefer in {"auto", "l2"}
        use_l1 = prefer in {"auto", "l1"}

        if use_l2:
            rows = conn.execute(
                """
                SELECT recorded_at, canonical_json
                FROM canonical_records
                WHERE flight_id = ? AND validation_ok = 1
                ORDER BY recorded_at ASC
                """,
                (flight_id,),
            ).fetchall()
            for i, row in enumerate(rows):
                if i % stride != 0:
                    continue
                canonical = json.loads(row["canonical_json"])
                sample = sample_from_l2_record(canonical, recorded_at=row["recorded_at"])
                if sample is None:
                    continue
                samples.append(sample)
                if len(samples) >= max_samples:
                    break
            if samples and any("north_m" in s for s in samples[:5]):
                frame = "wgs84+local_ned"

        if not samples and use_l1:
            data_origin = "l1_ingest"
            events = conn.execute(
                """
                SELECT payload_json
                FROM ingest_events
                WHERE flight_id = ?
                ORDER BY rowid ASC
                """,
                (flight_id,),
            ).fetchall()
            merged_records: list[dict] = []
            source = flight["source"]
            batch_ts: str | None = None
            for event in events:
                payload = json.loads(event["payload_json"])
                source = payload.get("source") or source
                if not batch_ts:
                    batch_ts = payload.get("timestamp_utc")
                merged_records.extend(payload.get("records") or [])
            path = l1_payload_to_path(
                {
                    "flight_id": flight_id,
                    "source": source,
                    "timestamp_utc": batch_ts,
                    "records": merged_records,
                },
                stride=stride,
                max_samples=max_samples,
            )
            samples = path["samples"]
            frame = path["frame"]

        path_doc = build_flight_path(
            flight_id=flight_id,
            source=flight["source"],
            samples=samples,
            frame=frame,
        )

    return FlightPathResponse(
        contract_version=PATH_CONTRACT_VERSION,
        flight_id=path_doc["flight_id"],
        source=path_doc["source"],
        frame=path_doc["frame"],
        units=path_doc["units"],
        count=path_doc["count"],
        samples=path_doc["samples"],
        data_origin=data_origin,
    )


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
