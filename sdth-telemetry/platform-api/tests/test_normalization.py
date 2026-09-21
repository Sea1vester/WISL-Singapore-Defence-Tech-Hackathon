from __future__ import annotations

import json
from pathlib import Path

import app.llm as llm_module
from app.db import db_session
from app.llm import translate_payload
from app.worker import process_job
from parsers.dji_csv import parse_dji_csv_to_l1
from tests.conftest import AUTH


DEMO_LOG = Path(__file__).parents[2] / "fixtures" / "demo" / "controller_mission_alpha.csv"


def test_ingest_persists_full_schema_valid_series_with_provenance(client):
    payload = parse_dji_csv_to_l1(
        DEMO_LOG,
        flight_id="canonical-demo",
        event_id="canonical-demo-event",
    )

    response = client.post("/v1/telemetry/ingest", json=payload, headers=AUTH)
    assert response.status_code == 202

    records = client.get("/v1/flights/canonical-demo/records", headers=AUTH).json()
    assert records["total"] == 8
    assert records["items"][3]["canonical_json"]["sensors"]["warning"] == "GPS signal weak"
    assert (
        records["items"][0]["canonical_json"]["metadata"]["value_origin"]["telemetry_fields"]
        == "observed"
    )

    with db_session() as conn:
        provenance = conn.execute(
            """
            SELECT parser, source_format, schema_version, validation_status, value_origin
            FROM normalization_provenance
            """
        ).fetchall()
    assert len(provenance) == 8
    assert provenance[0]["parser"] == "api-l1"
    assert provenance[0]["validation_status"] == "schema_valid"
    assert json.loads(provenance[0]["value_origin"])["canonical_structure"] == "derived"


def test_ollama_uses_schema_constrained_deterministic_error_enrichment(monkeypatch):
    captured = {}
    enrichment = {
        "flight_id": "flight-1",
        "errors": [
            {
                "timestamp_utc": "2026-08-22T00:00:00Z",
                "code": "GPS_WEAK",
                "category": "navigation",
                "summary": "GPS signal was weak.",
                "confidence": 0.95,
            }
        ],
        "summary": "One navigation warning.",
        "limitations": "No RF measurements were supplied.",
    }

    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {"response": json.dumps(enrichment)}

    class Client:
        def __init__(self, **_kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def post(self, path, json):
            captured["path"] = path
            captured["request"] = json
            return Response()

    monkeypatch.setattr(llm_module.httpx, "Client", Client)
    parsed, _, _ = translate_payload(
        {
            "flight_id": "flight-1",
            "source": "dji-csv",
            "records": [
                {
                    "timestamp_utc": "2026-08-22T00:00:00Z",
                    "warning": "GPS signal weak",
                    "lat": 1.35,
                }
            ],
        }
    )

    assert parsed == enrichment
    assert captured["request"]["format"]["required"] == [
        "flight_id",
        "errors",
        "summary",
        "limitations",
    ]
    assert captured["request"]["options"] == {"temperature": 0, "seed": 42}
    assert "1.35" not in captured["request"]["prompt"]


def test_model_failure_degrades_enrichment_without_losing_canonical_data(
    client,
    monkeypatch,
):
    payload = parse_dji_csv_to_l1(
        DEMO_LOG,
        flight_id="degraded-demo",
        event_id="degraded-demo-event",
    )
    response = client.post("/v1/telemetry/ingest", json=payload, headers=AUTH)
    job_id = response.json()["job_id"]

    def unavailable(_payload):
        raise RuntimeError("Ollama offline")

    monkeypatch.setattr("app.worker.translate_with_repair", unavailable)
    process_job(job_id)

    status = client.get(f"/v1/ingest/{response.json()['ingest_id']}/status", headers=AUTH).json()
    assert status["status"] == "done"
    assert "Ollama offline" in status["error"]
    records = client.get("/v1/flights/degraded-demo/records", headers=AUTH).json()
    assert records["total"] == 8


def test_l1_series_sorted_by_timestamp():
    from app.canonical_series import series_from_l1_payload

    payload = {
        "flight_id": "sort-demo",
        "source": "csv-generic",
        "records": [
            {"timestamp_utc": "2026-01-01T00:00:02Z", "lat": 1.0, "lon": 2.0},
            {"timestamp_utc": "2026-01-01T00:00:00Z", "lat": 1.0, "lon": 2.0},
            {"timestamp_utc": "2026-01-01T00:00:01Z", "lat": 1.0, "lon": 2.0},
        ],
    }
    series = series_from_l1_payload(payload)
    assert [sample["timestamp_utc"] for sample in series] == [
        "2026-01-01T00:00:00Z",
        "2026-01-01T00:00:01Z",
        "2026-01-01T00:00:02Z",
    ]


def test_l1_series_keeps_order_when_timestamp_unparseable():
    from app.canonical_series import series_from_l1_payload

    payload = {
        "flight_id": "unsorted-demo",
        "source": "csv-generic",
        "records": [
            {"timestamp_utc": "2026-01-01T00:00:02Z", "lat": 1.0, "lon": 2.0},
            {"timestamp_utc": "not-a-timestamp", "lat": 1.0, "lon": 2.0},
            {"timestamp_utc": "2026-01-01T00:00:01Z", "lat": 1.0, "lon": 2.0},
        ],
    }
    series = series_from_l1_payload(payload)
    assert [sample["timestamp_utc"] for sample in series] == [
        "2026-01-01T00:00:02Z",
        "not-a-timestamp",
        "2026-01-01T00:00:01Z",
    ]
