import json
import re
import time
from typing import Any

import httpx
import jsonschema

from app.config import settings
from app.schemas import ERROR_ENRICHMENT_SCHEMA


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
    schema_str = json.dumps(ERROR_ENRICHMENT_SCHEMA, indent=2)
    relevant_records = []
    for record in l1_payload.get("records") or []:
        if not isinstance(record, dict):
            continue
        selected = {
            key: value
            for key, value in record.items()
            if key in {"timestamp_utc", "warning", "tip", "hex_code", "message_type", "error", "status"}
            and value not in (None, "")
        }
        if len(selected) > 1:
            relevant_records.append(selected)
    payload_str = json.dumps(
        {
            "flight_id": l1_payload.get("flight_id"),
            "source": l1_payload.get("source"),
            "error_records": relevant_records,
        },
        indent=2,
    )
    return f"""You are a telemetry error-normalization assistant.
Map unstructured warnings and vendor codes into the controlled error taxonomy.
Rules:
- Output ONLY valid JSON matching the schema.
- Do not invent errors that are absent from the input.
- Use category "unknown" when evidence is insufficient.
- State evidence limitations explicitly.

Error Enrichment JSON Schema:
{schema_str}

Input warning and error records:
{payload_str}
"""


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
                "format": ERROR_ENRICHMENT_SCHEMA,
                "options": {"temperature": 0, "seed": 42},
            },
        )
        response.raise_for_status()
        data = response.json()

    latency_ms = int((time.perf_counter() - started) * 1000)
    raw = data.get("response", "")
    parsed = _extract_json(raw)
    jsonschema.validate(instance=parsed, schema=ERROR_ENRICHMENT_SCHEMA)
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
