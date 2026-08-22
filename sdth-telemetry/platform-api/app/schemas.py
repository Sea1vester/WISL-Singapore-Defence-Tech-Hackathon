from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field


class TelemetryRecord(BaseModel):
    """Flexible L1 record from teammate."""

    model_config = {"extra": "allow"}


class IngestPayload(BaseModel):
    flight_id: str
    timestamp_utc: str
    source: str
    records: list[dict[str, Any]] = Field(default_factory=list)
    event_id: str | None = None


class IngestResponse(BaseModel):
    ingest_id: str
    job_id: str
    status: str = "accepted"


class JobStatusResponse(BaseModel):
    job_id: str
    ingest_id: str
    status: str
    error: str | None = None


class RawUploadResponse(BaseModel):
    upload_id: str
    status: str
    sha256: str
    duplicate: bool = False


class RawUploadStatusResponse(BaseModel):
    upload_id: str
    status: str
    filename: str
    size_bytes: int
    sha256: str
    flight_id: str | None = None
    ingest_id: str | None = None
    error: str | None = None


class FlightSummary(BaseModel):
    id: str
    source: str
    started_at: str
    ended_at: str | None = None
    created_at: str | None = None


class FlightsListResponse(BaseModel):
    items: list[FlightSummary]
    total: int
    offset: int
    limit: int


class CanonicalRecordItem(BaseModel):
    id: str
    ingest_id: str
    flight_id: str
    recorded_at: str
    canonical_json: dict[str, Any]
    llm_model: str | None = None
    validation_ok: bool


class RecordsListResponse(BaseModel):
    items: list[CanonicalRecordItem]
    total: int
    offset: int
    limit: int


class PathSample(BaseModel):
    """One pose for 3D visualization. Extra keys allowed for overlays."""

    model_config = {"extra": "allow"}

    t: str | None = None
    lat: float
    lon: float
    alt_m: float | None = None
    roll_deg: float | None = None
    pitch_deg: float | None = None
    yaw_deg: float | None = None
    battery_pct: float | None = None
    battery_v: float | None = None


class FlightPathResponse(BaseModel):
    contract_version: str = "1.0"
    flight_id: str
    source: str
    frame: str = "wgs84"
    units: dict[str, str]
    count: int
    samples: list[dict[str, Any]]
    data_origin: str  # "l2_canonical" | "l1_ingest"


CANONICAL_JSON_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["flight_id", "timestamp_utc", "position", "attitude", "battery", "sensors", "metadata"],
    "properties": {
        "flight_id": {"type": "string"},
        "timestamp_utc": {"type": "string"},
        "position": {
            "type": "object",
            "properties": {
                "lat": {"type": "number"},
                "lon": {"type": "number"},
                "alt_m": {"type": "number"},
            },
            "required": ["lat", "lon", "alt_m"],
        },
        "attitude": {
            "type": "object",
            "properties": {
                "roll_deg": {"type": "number"},
                "pitch_deg": {"type": "number"},
                "yaw_deg": {"type": "number"},
            },
            "required": ["roll_deg", "pitch_deg", "yaw_deg"],
        },
        "battery": {
            "type": "object",
            "properties": {
                "percent": {"type": "number"},
                "voltage_v": {"type": "number"},
            },
            "required": ["percent", "voltage_v"],
        },
        "sensors": {
            "type": "object",
            "additionalProperties": True,
        },
        "metadata": {"type": "object"},
    },
    "additionalProperties": False,
}

ERROR_ENRICHMENT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["flight_id", "errors", "summary", "limitations"],
    "properties": {
        "flight_id": {"type": "string"},
        "errors": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["timestamp_utc", "code", "category", "summary", "confidence"],
                "properties": {
                    "timestamp_utc": {"type": "string"},
                    "code": {"type": "string"},
                    "category": {
                        "type": "string",
                        "enum": [
                            "battery",
                            "navigation",
                            "propulsion",
                            "communications",
                            "sensor",
                            "flight_control",
                            "unknown",
                        ],
                    },
                    "summary": {"type": "string"},
                    "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                },
                "additionalProperties": False,
            },
        },
        "summary": {"type": "string"},
        "limitations": {"type": "string"},
    },
    "additionalProperties": False,
}


INCIDENT_REPORT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": [
        "kind",
        "flight_id",
        "mission_summary",
        "timeline",
        "likely_contributing_factors",
        "confidence_and_limitations",
        "recommended_follow_up",
        "model_enrichment",
    ],
    "properties": {
        "kind": {
            "type": "string",
            "const": "evidence_backed_incident_summary",
        },
        "not_a_root_cause_analysis": {"type": "boolean"},
        "flight_id": {"type": "string"},
        "mission_summary": {"type": "string"},
        "timeline": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["timestamp_utc", "event", "evidence"],
                "properties": {
                    "timestamp_utc": {"type": "string"},
                    "event": {"type": "string"},
                    "evidence": {"type": "string"},
                    "lat": {"type": ["number", "null"]},
                    "lon": {"type": ["number", "null"]},
                    "alt_m": {"type": ["number", "null"]},
                },
            },
        },
        "likely_contributing_factors": {"type": "array", "items": {"type": "string"}},
        "confidence_and_limitations": {"type": "string"},
        "recommended_follow_up": {"type": "array", "items": {"type": "string"}},
        "model_enrichment": {"type": "string", "enum": ["available", "degraded"]},
    },
    "additionalProperties": False,
}


class IncidentReportResponse(BaseModel):
    kind: str = "evidence_backed_incident_summary"
    not_a_root_cause_analysis: bool = True
    flight_id: str
    mission_summary: str
    timeline: list[dict[str, Any]]
    likely_contributing_factors: list[str]
    confidence_and_limitations: str
    recommended_follow_up: list[str]
    model_enrichment: str
    report: str


def new_id() -> str:
    return str(uuid4())
