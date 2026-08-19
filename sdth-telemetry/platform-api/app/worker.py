import json
import logging
import time
from datetime import datetime, timezone

import redis

from app.db import db_session, run_migrations
from app.llm import translate_with_repair
from app.queue import blocking_pop_job
from app.schemas import new_id

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

    try:
        canonical, latency_ms, model = translate_with_repair(l1_payload)
    except Exception as exc:
        logger.exception("Translation failed for job %s", job_id)
        with db_session() as conn:
            _set_job_status(conn, job_id, "failed", str(exc))
        return

    record_id = new_id()
    recorded_at = canonical.get("timestamp_utc") or l1_payload.get("timestamp_utc")

    with db_session() as conn:
        conn.execute(
            """
            INSERT INTO canonical_records (
              id, ingest_id, flight_id, recorded_at, canonical_json,
              llm_model, llm_latency_ms, validation_ok
            ) VALUES (?, ?, ?, ?, ?, ?, ?, 1)
            """,
            (
                record_id,
                ingest["id"],
                ingest["flight_id"],
                recorded_at,
                json.dumps(canonical),
                model,
                latency_ms,
            ),
        )
        _set_job_status(conn, job_id, "done")

    try:
        from app.incidents import index_flight

        index_flight(ingest["flight_id"])
    except Exception:
        logger.exception("Incident indexing failed for flight %s", ingest["flight_id"])

    logger.info("Job %s done -> canonical record %s", job_id, record_id)


def run_worker() -> None:
    run_migrations()
    logger.info("Translation worker started")
    while True:
        try:
            job_id = blocking_pop_job(timeout=5)
        except redis.RedisError as exc:
            logger.warning("Redis unavailable, retrying: %s", exc)
            time.sleep(2)
            continue
        if not job_id:
            continue
        process_job(job_id)


if __name__ == "__main__":
    run_worker()
