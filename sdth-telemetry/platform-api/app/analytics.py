import json
from typing import Any

import httpx
import jsonschema
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.auth import require_api_key
from app.canonical_series import load_flight_series
from app.config import settings
from app.db import db_session
from app.incidents import index_flight, list_flight_incidents
from app.schemas import INCIDENT_REPORT_SCHEMA, IncidentReportResponse, new_id

router = APIRouter(prefix="/v1", tags=["analytics"])


class ChatRequest(BaseModel):
    query: str


class ChatResponse(BaseModel):
    answer: str


def _ask_llm(prompt: str, *, response_schema: dict[str, Any] | None = None) -> str:
    payload: dict[str, Any] = {
        "model": settings.ollama_model,
        "prompt": prompt,
        "stream": False,
        "options": {"temperature": 0, "seed": 42},
    }
    if response_schema is not None:
        payload["format"] = response_schema
    with httpx.Client(base_url=settings.ollama_base_url, timeout=300.0) as client:
        response = client.post("/api/generate", json=payload)
        response.raise_for_status()
        return response.json().get("response", "")


def _load_series_and_incidents(flight_id: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    with db_session() as conn:
        flight = conn.execute("SELECT id FROM flights WHERE id = ?", (flight_id,)).fetchone()
        if not flight:
            raise HTTPException(status_code=404, detail="Flight not found")
        series, _origin = load_flight_series(conn, flight_id)
    incidents = [item for item in list_flight_incidents(flight_id) if item.get("detector") != "llm"]
    if not incidents and series:
        index_flight(flight_id)
        incidents = [item for item in list_flight_incidents(flight_id) if item.get("detector") != "llm"]
    return series, incidents


def _latest_enrichment(flight_id: str) -> dict[str, Any] | None:
    with db_session() as conn:
        row = conn.execute(
            """
            SELECT enrichment_json
            FROM normalization_enrichments
            WHERE flight_id = ? AND validation_ok = 1
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (flight_id,),
        ).fetchone()
    if not row:
        return None
    return json.loads(row["enrichment_json"])


def build_deterministic_report(
    flight_id: str,
    series: list[dict[str, Any]],
    incidents: list[dict[str, Any]],
    *,
    enrichment: dict[str, Any] | None = None,
) -> dict[str, Any]:
    first = series[0] if series else {}
    last = series[-1] if series else {}
    source = ((first.get("metadata") or {}).get("source")) or "unknown"
    start = first.get("timestamp_utc") or ""
    end = last.get("timestamp_utc") or start
    if incidents:
        mission_summary = (
            f"Recorded {source} mission {flight_id} from {start} to {end} with "
            f"{len(series)} samples and {len(incidents)} rule-detected incident(s). "
            "This is an evidence-backed summary, not a causal root-cause analysis."
        )
    else:
        mission_summary = (
            f"Recorded {source} mission {flight_id} from {start} to {end} with "
            f"{len(series)} samples. No rule-detected incidents were found. "
            "This is an evidence-backed summary, not a causal root-cause analysis."
        )

    timeline = []
    for item in incidents:
        position = item.get("evidence", {}).get("position") or {}
        timeline.append(
            {
                "timestamp_utc": item.get("started_at") or "",
                "event": f"{item.get('incident_type')}: {item.get('summary')}",
                "evidence": json.dumps(item.get("evidence") or {}, sort_keys=True),
                "lat": item.get("lat", position.get("lat")),
                "lon": item.get("lon", position.get("lon")),
                "alt_m": item.get("alt_m", position.get("alt_m")),
            }
        )

    factors = [item.get("summary") for item in incidents if item.get("summary")]
    if enrichment and enrichment.get("errors"):
        factors.extend(
            f"Model-normalized {error.get('category')}: {error.get('summary')}"
            for error in enrichment["errors"]
            if error.get("summary")
        )
    if not factors:
        factors = ["No detector or model evidence indicated a failure."]

    limitations = (
        "Confidence is limited to recorded telemetry and deterministic detectors. "
        "No live airframe, camera, RF, or vendor diagnostic session was available. "
        "Do not treat this output as a confirmed causal chain."
    )
    if enrichment and enrichment.get("limitations"):
        limitations = f"{limitations} Model note: {enrichment['limitations']}"

    follow_up = [
        "Review the marked timestamps and coordinates on the 3D replay.",
        "Compare this signature against other missions before changing procedure.",
        "Do not deploy firmware or configuration changes from this summary alone.",
    ]
    if incidents:
        follow_up.insert(0, f"Inspect the first {incidents[0]['incident_type']} interval in the flight path.")

    report = {
        "kind": "evidence_backed_incident_summary",
        "not_a_root_cause_analysis": True,
        "flight_id": flight_id,
        "mission_summary": mission_summary,
        "timeline": timeline,
        "likely_contributing_factors": factors,
        "confidence_and_limitations": limitations,
        "recommended_follow_up": follow_up,
        "model_enrichment": "available" if enrichment else "degraded",
    }
    jsonschema.validate(instance=report, schema=INCIDENT_REPORT_SCHEMA)
    return report


def _try_model_report(
    flight_id: str,
    series: list[dict[str, Any]],
    incidents: list[dict[str, Any]],
    enrichment: dict[str, Any] | None,
) -> dict[str, Any] | None:
    compact_series = [
        {
            "timestamp_utc": sample.get("timestamp_utc"),
            "position": sample.get("position"),
            "battery": sample.get("battery"),
            "attitude": sample.get("attitude"),
            "sensors": {
                key: value
                for key, value in (sample.get("sensors") or {}).items()
                if key in {"warning", "tip", "flight_mode"}
            },
        }
        for sample in series[:80]
    ]
    prompt = f"""Write an evidence-backed incident summary, not a root-cause analysis.
Use only the supplied telemetry and detector findings. Do not invent causes.
Output JSON matching the schema exactly.

Schema:
{json.dumps(INCIDENT_REPORT_SCHEMA, indent=2)}

Flight: {flight_id}
Detector incidents:
{json.dumps(incidents, indent=2)}
Telemetry samples:
{json.dumps(compact_series, indent=2)}
    Optional model error enrichment:
{json.dumps(enrichment if enrichment is not None else {}, indent=2)}
"""
    try:
        raw = _ask_llm(prompt, response_schema=INCIDENT_REPORT_SCHEMA)
        parsed = json.loads(raw)
        parsed["kind"] = "evidence_backed_incident_summary"
        parsed["not_a_root_cause_analysis"] = True
        parsed["flight_id"] = flight_id
        parsed["model_enrichment"] = "available"
        jsonschema.validate(instance=parsed, schema=INCIDENT_REPORT_SCHEMA)
        return parsed
    except Exception:
        return None


def _store_report(flight_id: str, report: dict[str, Any]) -> None:
    with db_session() as conn:
        conn.execute(
            """
            INSERT INTO incident_reports (id, flight_id, report_json, model_enrichment)
            VALUES (?, ?, ?, ?)
            """,
            (
                new_id(),
                flight_id,
                json.dumps(report),
                report["model_enrichment"],
            ),
        )


def _load_latest_report(flight_id: str) -> dict[str, Any] | None:
    with db_session() as conn:
        row = conn.execute(
            """
            SELECT report_json
            FROM incident_reports
            WHERE flight_id = ?
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (flight_id,),
        ).fetchone()
    return json.loads(row["report_json"]) if row else None


def _to_response(report: dict[str, Any]) -> IncidentReportResponse:
    text = (
        f"{report['mission_summary']}\n\n"
        "Timeline:\n"
        + "\n".join(f"- {item['timestamp_utc']}: {item['event']}" for item in report["timeline"])
        + "\n\nLikely contributing factors:\n"
        + "\n".join(f"- {factor}" for factor in report["likely_contributing_factors"])
        + f"\n\nConfidence and limitations:\n{report['confidence_and_limitations']}\n\n"
        "Recommended follow-up:\n"
        + "\n".join(f"- {step}" for step in report["recommended_follow_up"])
    )
    return IncidentReportResponse(**report, report=text)


def generate_structured_report(flight_id: str, *, allow_llm: bool = True) -> dict[str, Any]:
    series, incidents = _load_series_and_incidents(flight_id)
    enrichment = _latest_enrichment(flight_id)
    report = build_deterministic_report(
        flight_id,
        series,
        incidents,
        enrichment=enrichment,
    )
    if allow_llm:
        modeled = _try_model_report(flight_id, series, incidents, enrichment)
        if modeled is not None:
            report = modeled
        else:
            report["model_enrichment"] = "degraded" if not enrichment else report["model_enrichment"]
    _store_report(flight_id, report)
    try:
        index_flight(flight_id, include_llm_report=report["mission_summary"])
    except KeyError:
        raise HTTPException(status_code=404, detail="Flight not found")
    return report


def generate_llm_incident_text(flight_id: str) -> str:
    return _to_response(generate_structured_report(flight_id, allow_llm=True)).report


@router.post("/flights/{flight_id}/chat", response_model=ChatResponse)
def chat_with_flight_data(flight_id: str, request: ChatRequest, _: str = Depends(require_api_key)) -> ChatResponse:
    series, incidents = _load_series_and_incidents(flight_id)
    prompt = f"""You are a drone telemetry analyst. Answer only from the supplied data.
The user asked: "{request.query}"

Incidents:
{json.dumps(incidents, indent=2)}

Telemetry sample:
{json.dumps(series[:40], indent=2)}
"""
    try:
        answer = _ask_llm(prompt)
    except Exception as exc:
        answer = f"Model enrichment unavailable ({exc}). Use the structured incident report instead."
    return ChatResponse(answer=answer)


@router.post("/flights/{flight_id}/incident-report", response_model=IncidentReportResponse)
def generate_incident_report(flight_id: str, _: str = Depends(require_api_key)) -> IncidentReportResponse:
    return _to_response(generate_structured_report(flight_id, allow_llm=True))


@router.get("/flights/{flight_id}/incident-report", response_model=IncidentReportResponse)
def get_incident_report(flight_id: str, _: str = Depends(require_api_key)) -> IncidentReportResponse:
    stored = _load_latest_report(flight_id)
    if stored:
        return _to_response(stored)
    series, incidents = _load_series_and_incidents(flight_id)
    report = build_deterministic_report(
        flight_id,
        series,
        incidents,
        enrichment=_latest_enrichment(flight_id),
    )
    report["model_enrichment"] = "degraded"
    _store_report(flight_id, report)
    return _to_response(report)
