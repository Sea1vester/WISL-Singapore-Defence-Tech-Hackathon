import json

import redis

from app.config import settings


def get_redis() -> redis.Redis:
    return redis.Redis.from_url(
        settings.redis_url,
        decode_responses=True,
        socket_connect_timeout=5,
        socket_timeout=30,
        health_check_interval=30,
    )


def enqueue_translation_job(job_id: str) -> None:
    client = get_redis()
    client.rpush(settings.job_queue_key, json.dumps({"job_id": job_id}))


def enqueue_raw_upload(upload_id: str) -> None:
    client = get_redis()
    client.rpush(settings.raw_upload_queue_key, json.dumps({"upload_id": upload_id}))


def blocking_pop_job(timeout: int = 5) -> str | None:
    client = get_redis()
    result = client.blpop(settings.job_queue_key, timeout=timeout)
    if not result:
        return None
    _, payload = result
    data = json.loads(payload)
    return data["job_id"]
