import json
import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.auth import require_api_key
from app.db import db_session
from app.config import settings

router = APIRouter(prefix="/v1", tags=["analytics"])

class ChatRequest(BaseModel):
    query: str

class ChatResponse(BaseModel):
    answer: str

class IncidentReportResponse(BaseModel):
    report: str

def _ask_llm(prompt: str) -> str:
    with httpx.Client(base_url=settings.ollama_base_url, timeout=300.0) as client:
        response = client.post(
            "/api/generate",
            json={
                "model": settings.ollama_model,
                "prompt": prompt,
                "stream": False,
            },
        )
        response.raise_for_status()
        return response.json().get("response", "")

def _get_flight_data(flight_id: str) -> list[dict]:
    with db_session() as conn:
        flight = conn.execute("SELECT id FROM flights WHERE id = ?", (flight_id,)).fetchone()
        if not flight:
            raise HTTPException(status_code=404, detail="Flight not found")
        
        rows = conn.execute(
            """
            SELECT recorded_at, canonical_json
            FROM canonical_records
            WHERE flight_id = ? AND validation_ok = 1
            ORDER BY recorded_at ASC
            LIMIT 500
            """,
            (flight_id,),
        ).fetchall()
        
    return [json.loads(row["canonical_json"]) for row in rows]

@router.post("/flights/{flight_id}/chat", response_model=ChatResponse)
def chat_with_flight_data(flight_id: str, request: ChatRequest, _: str = Depends(require_api_key)) -> ChatResponse:
    data = _get_flight_data(flight_id)
    
    prompt = f"""You are a drone telemetry data analyst.
The user asked: "{request.query}"

Here is a sample of the telemetry data (canonical JSON L2 format) for this flight:
{json.dumps(data, indent=2)}

Please provide a concise and helpful answer based on the data.
"""
    answer = _ask_llm(prompt)
    return ChatResponse(answer=answer)

@router.post("/flights/{flight_id}/incident-report", response_model=IncidentReportResponse)
def generate_incident_report(flight_id: str, _: str = Depends(require_api_key)) -> IncidentReportResponse:
    data = _get_flight_data(flight_id)
    
    prompt = f"""You are a drone safety analyst.
Please review the following telemetry data and auto-generate a plain-English incident report.
Highlight any anomalies, sudden drops in altitude, unusual battery drain, or unexpected attitude changes.
If the flight looks normal, state that no incidents were detected.

Telemetry Data:
{json.dumps(data, indent=2)}

Incident Report:
"""
    report = _ask_llm(prompt)
    return IncidentReportResponse(report=report)
