"""Single-process demo queue. Redis remains the default deployment path.

The SQLite job records are the recovery source; this worker must run in one
Uvicorn process. It deliberately does not coordinate multiple API processes.
"""
from concurrent.futures import ThreadPoolExecutor
import logging
import threading

from app.db import db_session

_lock = threading.RLock()
_executor = None
_pending: set[tuple[str, str]] = set()
_drained = threading.Condition(_lock)
logger = logging.getLogger("sdth.local_worker")


def submit(kind: str, job_id: str) -> None:
    global _executor
    with _lock:
        key = (kind, job_id)
        if key in _pending:
            return
        if _executor is None:
            _executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="wisl-demo")
        _pending.add(key)
        _executor.submit(_run, kind, job_id)


def _run(kind: str, job_id: str) -> None:
    try:
        from app.worker import process_job, process_raw_upload
        (process_raw_upload if kind == "raw_upload" else process_job)(job_id)
    except Exception:
        logger.exception("Demo job failed: %s %s", kind, job_id)
    finally:
        with _lock:
            _pending.discard((kind, job_id))
            _drained.notify_all()


def recover() -> None:
    with db_session() as conn:
        # A prior process may have stopped midway. Deterministic IDs and raw
        # content hashes allow retries without inventing extra flight records.
        conn.execute("UPDATE translation_jobs SET status='pending' WHERE status='running'")
        conn.execute("UPDATE raw_uploads SET status='received' WHERE status='parsing'")
        conn.execute("""UPDATE translation_jobs SET status='pending' WHERE ingest_id IN
            (SELECT ingest_id FROM raw_uploads WHERE status IN ('normalizing','detecting'))""")
        raw = conn.execute("SELECT id FROM raw_uploads WHERE status='received'").fetchall()
        jobs = conn.execute("SELECT id FROM translation_jobs WHERE status='pending'").fetchall()
    for row in raw:
        submit("raw_upload", row["id"])
    for row in jobs:
        submit("translation", row["id"])


def stop() -> None:
    global _executor
    with _drained:
        while _pending:
            _drained.wait()
        executor, _executor = _executor, None
    if executor is not None:
        executor.shutdown(wait=True)
