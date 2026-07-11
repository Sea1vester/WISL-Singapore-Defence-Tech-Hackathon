import json
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status

from app.auth import require_api_key
from app.db import db_session
from app.queue import enqueue_translation_job
from app.schemas import IngestPayload, IngestResponse, JobStatusResponse, new_id

router = APIRouter(prefix="/v1", tags=["ingest"])


def _upsert_flight(conn, flight_id: str, source: str, timestamp_utc: str) -> None:
    row = conn.execute("SELECT id FROM flights WHERE id = ?", (flight_id,)).fetchone()
    if row:
        return
    conn.execute(
        """
        INSERT INTO flights (id, source, started_at)
        VALUES (?, ?, ?)
        """,
        (flight_id, source, timestamp_utc),
    )


@router.post("/telemetry/ingest", response_model=IngestResponse, status_code=status.HTTP_202_ACCEPTED)
def ingest_telemetry(payload: IngestPayload, _: str = Depends(require_api_key)) -> IngestResponse:
    ingest_id = new_id()
    job_id = new_id()
    idempotency_key = payload.event_id
    payload_json = json.dumps(payload.model_dump())

    with db_session() as conn:
        if idempotency_key:
            existing = conn.execute(
                "SELECT id FROM ingest_events WHERE idempotency_key = ?",
                (idempotency_key,),
            ).fetchone()
            if existing:
                job = conn.execute(
                    "SELECT id, status FROM translation_jobs WHERE ingest_id = ? ORDER BY created_at DESC LIMIT 1",
                    (existing["id"],),
                ).fetchone()
                return IngestResponse(
                    ingest_id=existing["id"],
                    job_id=job["id"] if job else new_id(),
                    status="duplicate",
                )

        _upsert_flight(conn, payload.flight_id, payload.source, payload.timestamp_utc)

        try:
            conn.execute(
                """
                INSERT INTO ingest_events (id, flight_id, payload_json, idempotency_key)
                VALUES (?, ?, ?, ?)
                """,
                (ingest_id, payload.flight_id, payload_json, idempotency_key),
            )
        except Exception as exc:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Duplicate ingest") from exc

        now = datetime.now(timezone.utc).isoformat()
        conn.execute(
            """
            INSERT INTO translation_jobs (id, ingest_id, status, created_at, updated_at)
            VALUES (?, ?, 'pending', ?, ?)
            """,
            (job_id, ingest_id, now, now),
        )

    enqueue_translation_job(job_id)
    return IngestResponse(ingest_id=ingest_id, job_id=job_id, status="accepted")


@router.get("/ingest/{ingest_id}/status", response_model=JobStatusResponse)
def ingest_status(ingest_id: str, _: str = Depends(require_api_key)) -> JobStatusResponse:
    with db_session() as conn:
        job = conn.execute(
            """
            SELECT id, ingest_id, status, error
            FROM translation_jobs
            WHERE ingest_id = ?
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (ingest_id,),
        ).fetchone()

    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ingest not found")

    return JobStatusResponse(
        job_id=job["id"],
        ingest_id=job["ingest_id"],
        status=job["status"],
        error=job["error"],
    )
