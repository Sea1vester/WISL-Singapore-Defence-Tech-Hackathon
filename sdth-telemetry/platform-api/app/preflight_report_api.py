"""
FastAPI router for pre-emptive mission-planning PDF reports.

Endpoints:
  POST /v1/flights/{flight_id}/preemptive-report        - build + render + store a new report
  GET  /v1/flights/{flight_id}/preemptive-report         - most recent report's metadata + findings
  GET  /v1/preemptive-reports/{report_id}/file           - stream the PDF
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse
from pydantic import BaseModel

from app.auth import require_api_key
from app.config import settings
from app.db import db_session
from app.pdf_report import render_preemptive_report_pdf
from app.preflight_report import build_preemptive_report
from app.schemas import new_id

logger = logging.getLogger("preflight_report_api")

router = APIRouter(tags=["preemptive-reports"])


class PreemptiveReportResponse(BaseModel):
    id: str
    flight_id: str
    incident_count: int
    created_at: str | None = None
    report: dict[str, Any]


def _reports_dir() -> Path:
    root = Path(settings.reports_dir).expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    return root


def _persist(flight_id: str, report: dict[str, Any]) -> dict[str, Any]:
    report_id = new_id()
    pdf_path = _reports_dir() / f"{report_id}.pdf"
    render_preemptive_report_pdf(report, out_path=pdf_path)

    with db_session() as conn:
        conn.execute(
            """
            INSERT INTO preemptive_reports (id, flight_id, stored_path, report_json, incident_count)
            VALUES (?, ?, ?, ?, ?)
            """,
            (report_id, flight_id, str(pdf_path), json.dumps(report), report["incident_count"]),
        )
        row = conn.execute(
            "SELECT id, flight_id, incident_count, created_at FROM preemptive_reports WHERE id = ?",
            (report_id,),
        ).fetchone()
    return {**dict(row), "report": report}


@router.post(
    "/v1/flights/{flight_id}/preemptive-report",
    response_model=PreemptiveReportResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Build and store a pre-emptive mission-planning PDF for a flight",
)
def create_preemptive_report(
    flight_id: str,
    _: str = Depends(require_api_key),
) -> PreemptiveReportResponse:
    try:
        with db_session() as conn:
            report = build_preemptive_report(conn, flight_id)
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Flight not found: {exc}") from exc

    row = _persist(flight_id, report)
    return PreemptiveReportResponse(**row)


@router.get(
    "/v1/flights/{flight_id}/preemptive-report",
    response_model=PreemptiveReportResponse,
    summary="Get the most recently generated pre-emptive report for a flight",
)
def get_latest_preemptive_report(
    flight_id: str,
    _: str = Depends(require_api_key),
) -> PreemptiveReportResponse:
    with db_session() as conn:
        row = conn.execute(
            """
            SELECT id, flight_id, incident_count, created_at, report_json
            FROM preemptive_reports
            WHERE flight_id = ?
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (flight_id,),
        ).fetchone()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No report generated for this flight yet")
    data = dict(row)
    report = json.loads(data.pop("report_json"))
    return PreemptiveReportResponse(**data, report=report)


@router.get(
    "/v1/preemptive-reports/{report_id}/file",
    summary="Stream the generated PDF",
)
def get_preemptive_report_file(
    report_id: str,
    _: str = Depends(require_api_key),
) -> FileResponse:
    with db_session() as conn:
        row = conn.execute(
            "SELECT stored_path FROM preemptive_reports WHERE id = ?",
            (report_id,),
        ).fetchone()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Report not found")
    path = Path(row["stored_path"])
    if not path.exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Report PDF not found on disk")
    return FileResponse(path=str(path), media_type="application/pdf", filename=path.name)
