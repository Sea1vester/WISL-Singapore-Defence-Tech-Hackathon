import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, File, Header, HTTPException, UploadFile, status

from app.auth import require_api_key
from app.config import settings
from app.db import db_session
from app.queue import enqueue_raw_upload, enqueue_translation_job
from app.schemas import (
    IngestPayload,
    IngestResponse,
    JobStatusResponse,
    RawUploadResponse,
    RawUploadStatusResponse,
    new_id,
)

router = APIRouter(prefix="/v1", tags=["ingest"])

RAW_LOG_EXTENSIONS = {
    ".bin",
    ".csv",
    ".hex",
    ".hermes",
    ".json",
    ".ros",
    ".stanag",
    ".syslog",
    ".tlog",
    ".ulg",
    ".ulog",
    ".xlsx",
    ".xml",
}
UPLOAD_CHUNK_BYTES = 1024 * 1024


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


@router.post("/logs/upload", response_model=RawUploadResponse, status_code=status.HTTP_202_ACCEPTED)
def upload_raw_log(
    file: UploadFile = File(...),
    declared_sha256: str | None = Header(default=None, alias="X-WISL-SHA256"),
    _: str = Depends(require_api_key),
) -> RawUploadResponse:
    original_name = Path(file.filename or "").name
    suffix = Path(original_name).suffix.lower()
    if not original_name or suffix not in RAW_LOG_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"Unsupported raw log extension: {suffix or '<none>'}",
        )

    upload_id = new_id()
    spool_dir = Path(settings.raw_upload_dir).resolve()
    spool_dir.mkdir(parents=True, exist_ok=True)
    temporary_path = spool_dir / f".{upload_id}.part"
    stored_path = spool_dir / f"{upload_id}{suffix}"
    digest = hashlib.sha256()
    size = 0

    try:
        with temporary_path.open("wb") as output:
            while chunk := file.file.read(UPLOAD_CHUNK_BYTES):
                size += len(chunk)
                if size > settings.raw_upload_max_bytes:
                    raise HTTPException(
                        status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                        detail=f"Raw log exceeds {settings.raw_upload_max_bytes} byte limit",
                    )
                digest.update(chunk)
                output.write(chunk)
        sha256 = digest.hexdigest()
        if declared_sha256 and declared_sha256.lower() != sha256:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="X-WISL-SHA256 does not match uploaded content",
            )

        with db_session() as conn:
            existing = conn.execute(
                "SELECT id, status FROM raw_uploads WHERE sha256 = ?",
                (sha256,),
            ).fetchone()
            if existing:
                temporary_path.unlink(missing_ok=True)
                return RawUploadResponse(
                    upload_id=existing["id"],
                    status=existing["status"],
                    sha256=sha256,
                    duplicate=True,
                )

            temporary_path.replace(stored_path)
            conn.execute(
                """
                INSERT INTO raw_uploads (
                  id, sha256, original_name, stored_path, size_bytes, status,
                  provenance_json
                ) VALUES (?, ?, ?, ?, ?, 'received', ?)
                """,
                (
                    upload_id,
                    sha256,
                    original_name,
                    str(stored_path),
                    size,
                    json.dumps({"transport": "multipart", "declared_sha256": bool(declared_sha256)}),
                ),
            )
    except Exception:
        temporary_path.unlink(missing_ok=True)
        stored_path.unlink(missing_ok=True)
        raise
    finally:
        file.file.close()

    enqueue_raw_upload(upload_id)
    return RawUploadResponse(upload_id=upload_id, status="received", sha256=sha256)


@router.get("/uploads/{upload_id}", response_model=RawUploadStatusResponse)
def raw_upload_status(
    upload_id: str,
    _: str = Depends(require_api_key),
) -> RawUploadStatusResponse:
    with db_session() as conn:
        upload = conn.execute(
            """
            SELECT id, status, original_name, size_bytes, sha256, flight_id,
                   ingest_id, error
            FROM raw_uploads
            WHERE id = ?
            """,
            (upload_id,),
        ).fetchone()
    if not upload:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Upload not found")
    return RawUploadStatusResponse(
        upload_id=upload["id"],
        status=upload["status"],
        filename=upload["original_name"],
        size_bytes=upload["size_bytes"],
        sha256=upload["sha256"],
        flight_id=upload["flight_id"],
        ingest_id=upload["ingest_id"],
        error=upload["error"],
    )
