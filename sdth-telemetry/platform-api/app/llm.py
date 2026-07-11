import json
import re
import time
from typing import Any

import httpx
import jsonschema

from app.config import settings
from app.schemas import CANONICAL_JSON_SCHEMA


def _extract_json(text: str) -> dict[str, Any]:
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if not match:
            raise
        return json.loads(match.group(0))


def build_prompt(l1_payload: dict[str, Any]) -> str:
    schema_str = json.dumps(CANONICAL_JSON_SCHEMA, indent=2)
    payload_str = json.dumps(l1_payload, indent=2)
    return f"""You are a telemetry normalization assistant.
Map the input JSON (L1 normalized telemetry) into the canonical JSON Schema (L2).
Rules:
- Output ONLY valid JSON matching the schema.
- Put unknown fields under sensors.extra.
- Never drop data silently.
- Use flight_id and timestamp_utc from the ingest envelope when mapping records.

Canonical JSON Schema:
{schema_str}

Input L1 payload:
{payload_str}

Return a single canonical JSON object for the primary record in this batch."""


def translate_payload(l1_payload: dict[str, Any]) -> tuple[dict[str, Any], int, str]:
    prompt = build_prompt(l1_payload)
    started = time.perf_counter()

    with httpx.Client(base_url=settings.ollama_base_url, timeout=300.0) as client:
        response = client.post(
            "/api/generate",
            json={
                "model": settings.ollama_model,
                "prompt": prompt,
                "stream": False,
                "format": "json",
            },
        )
        response.raise_for_status()
        data = response.json()

    latency_ms = int((time.perf_counter() - started) * 1000)
    raw = data.get("response", "")
    parsed = _extract_json(raw)
    jsonschema.validate(instance=parsed, schema=CANONICAL_JSON_SCHEMA)
    return parsed, latency_ms, settings.ollama_model


def translate_with_repair(l1_payload: dict[str, Any], max_retries: int = 2) -> tuple[dict[str, Any], int, str]:
    last_error: Exception | None = None
    payload = l1_payload

    for attempt in range(max_retries + 1):
        try:
            return translate_payload(payload)
        except Exception as exc:
            last_error = exc
            if attempt >= max_retries:
                break
            payload = {
                **l1_payload,
                "_repair_hint": f"Previous attempt failed validation: {exc}. Fix JSON to match schema.",
            }

    assert last_error is not None
    raise last_error
