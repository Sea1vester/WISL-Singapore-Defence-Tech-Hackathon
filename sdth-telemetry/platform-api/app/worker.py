import json
import logging
import time
from datetime import datetime, timezone
from pathlib import Path

import redis

from app.canonical_series import persist_canonical_series
from app.config import settings
from app.db import db_session, run_migrations
from app.llm import translate_with_repair
from app.privacy import apply_retention, record_audit, redact_operator_locations
from app.queue import blocking_pop_work, enqueue_translation_job
from app.schemas import new_id
from parsers.registry import parse_raw_log

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("worker")


def _set_job_status(conn, job_id: str, status: str, error: str | None = None) -> None:
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        """
        UPDATE translation_jobs
        SET status = ?, error = ?, updated_at = ?
        WHERE id = ?
        """,
        (status, error, now, job_id),
    )


def _set_upload_status(
    conn,
    upload_id: str,
    status: str,
    *,
    error: str | None = None,
    flight_id: str | None = None,
    ingest_id: str | None = None,
) -> None:
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        """
        UPDATE raw_uploads
        SET status = ?, error = ?, flight_id = COALESCE(?, flight_id),
            ingest_id = COALESCE(?, ingest_id), updated_at = ?
        WHERE id = ?
        """,
        (status, error, flight_id, ingest_id, now, upload_id),
    )


def process_raw_upload(upload_id: str) -> None:
    with db_session() as conn:
        upload = conn.execute(
            """
            SELECT id, sha256, original_name, stored_path, status
            FROM raw_uploads
            WHERE id = ?
            """,
            (upload_id,),
        ).fetchone()
        if not upload:
            logger.warning("Raw upload %s not found", upload_id)
            return
        if upload["status"] in {"normalizing", "detecting", "ready"}:
            return
        _set_upload_status(conn, upload_id, "parsing")

    try:
        payload, parser_key = parse_raw_log(
            Path(upload["stored_path"]),
            sha256=upload["sha256"],
            original_name=upload["original_name"],
        )
        redactions: list[str] = []
        if settings.redact_operator_location:
            payload, redactions = redact_operator_locations(payload)
        ingest_id = new_id()
        job_id = new_id()
        queued_job = None
        now = datetime.now(timezone.utc).isoformat()
        with db_session() as conn:
            conn.execute(
                """
                INSERT OR IGNORE INTO flights (id, source, started_at)
                VALUES (?, ?, ?)
                """,
                (payload["flight_id"], payload["source"], payload["timestamp_utc"]),
            )
            existing = conn.execute(
                "SELECT id FROM ingest_events WHERE idempotency_key = ?",
                (payload["event_id"],),
            ).fetchone()
            if existing:
                ingest_id = existing["id"]
                queued_job = conn.execute(
                    """
                    SELECT id, status FROM translation_jobs
                    WHERE ingest_id = ?
                    ORDER BY created_at DESC LIMIT 1
                    """,
                    (ingest_id,),
                ).fetchone()
                if queued_job:
                    job_id = queued_job["id"]
                else:
                    conn.execute(
                        """
                        INSERT INTO translation_jobs (id, ingest_id, status, created_at, updated_at)
                        VALUES (?, ?, 'pending', ?, ?)
                        """,
                        (job_id, ingest_id, now, now),
                    )
            else:
                conn.execute(
                    """
                    INSERT INTO ingest_events (id, flight_id, payload_json, idempotency_key)
                    VALUES (?, ?, ?, ?)
                    """,
                    (ingest_id, payload["flight_id"], json.dumps(payload), payload["event_id"]),
                )
                conn.execute(
                    """
                    INSERT INTO translation_jobs (id, ingest_id, status, created_at, updated_at)
                    VALUES (?, ?, 'pending', ?, ?)
                    """,
                    (job_id, ingest_id, now, now),
                )
            persist_canonical_series(
                conn,
                ingest_id=ingest_id,
                payload=payload,
                parser=parser_key,
                redactions=redactions,
            )
            provenance = {
                "transport": "multipart",
                "parser": parser_key,
                "source_format": payload["source"],
                "record_count": len(payload["records"]),
                "operator_location": "redacted" if redactions else "not_present",
                "redactions": redactions,
            }
            if redactions:
                record_audit(
                    conn,
                    event_type="operator_location_redacted",
                    subject=payload["flight_id"],
                    detail={"fields": redactions, "upload_id": upload_id},
                )
            apply_retention(conn, retention_days=settings.retention_days)
            conn.execute(
                "UPDATE raw_uploads SET provenance_json = ? WHERE id = ?",
                (json.dumps(provenance), upload_id),
            )
            _set_upload_status(
                conn,
                upload_id,
                "normalizing",
                flight_id=payload["flight_id"],
                ingest_id=ingest_id,
            )
        from app.incidents import index_flight

        try:
            index_flight(payload["flight_id"])
        except Exception:
            logger.exception("Immediate incident index failed for %s", payload["flight_id"])
        if not existing or not queued_job or queued_job["status"] == "pending":
            enqueue_translation_job(job_id)
    except Exception as exc:
        logger.exception("Raw upload processing failed for %s", upload_id)
        with db_session() as conn:
            _set_upload_status(conn, upload_id, "failed", error=str(exc))


def process_job(job_id: str) -> None:
    with db_session() as conn:
        job = conn.execute(
            "SELECT id, ingest_id, status FROM translation_jobs WHERE id = ?",
            (job_id,),
        ).fetchone()
        if not job:
            logger.warning("Job %s not found", job_id)
            return
        if job["status"] in {"done", "running"}:
            return

        _set_job_status(conn, job_id, "running")

        ingest = conn.execute(
            "SELECT id, flight_id, payload_json FROM ingest_events WHERE id = ?",
            (job["ingest_id"],),
        ).fetchone()
        if not ingest:
            _set_job_status(conn, job_id, "failed", "Ingest event missing")
            return

    l1_payload = json.loads(ingest["payload_json"])

    enrichment = None
    enrichment_error = None
    latency_ms = 0
    model = settings.ollama_model
    try:
        enrichment, latency_ms, model = translate_with_repair(l1_payload)
    except Exception as exc:
        enrichment_error = f"Model enrichment unavailable: {exc}"
        logger.warning("%s", enrichment_error)

    enrichment_id = new_id()
    with db_session() as conn:
        if enrichment is not None:
            conn.execute(
                """
                INSERT INTO normalization_enrichments (
                  id, ingest_id, flight_id, enrichment_json,
                  llm_model, llm_latency_ms, validation_ok
                ) VALUES (?, ?, ?, ?, ?, ?, 1)
                """,
                (
                    enrichment_id,
                    ingest["id"],
                    ingest["flight_id"],
                    json.dumps(enrichment),
                    model,
                    latency_ms,
                ),
            )
        _set_job_status(conn, job_id, "done", enrichment_error)
        upload = conn.execute(
            "SELECT id FROM raw_uploads WHERE ingest_id = ?",
            (ingest["id"],),
        ).fetchone()
        if upload:
            _set_upload_status(
                conn,
                upload["id"],
                "detecting",
                error=enrichment_error,
            )

    try:
        from app.incidents import index_flight

        index_flight(ingest["flight_id"])
        if upload:
            with db_session() as conn:
                _set_upload_status(
                    conn,
                    upload["id"],
                    "ready",
                    error=enrichment_error,
                )
    except Exception as exc:
        logger.exception("Incident indexing failed for flight %s", ingest["flight_id"])
        if upload:
            with db_session() as conn:
                _set_upload_status(conn, upload["id"], "failed", error=str(exc))

    logger.info(
        "Job %s done; deterministic series retained, enrichment=%s",
        job_id,
        "available" if enrichment is not None else "degraded",
    )


def run_worker() -> None:
    run_migrations()
    logger.info("Translation worker started")
    while True:
        try:
            work = blocking_pop_work(timeout=5)
        except redis.RedisError as exc:
            logger.warning("Redis unavailable, retrying: %s", exc)
            time.sleep(2)
            continue
        if not work:
            continue
        work_type, work_id = work
        if work_type == "raw_upload":
            process_raw_upload(work_id)
        else:
            process_job(work_id)


if __name__ == "__main__":
    run_worker()
