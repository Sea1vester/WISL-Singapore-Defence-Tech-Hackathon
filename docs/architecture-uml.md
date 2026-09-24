# WISL architecture, UML

Three views. GitHub renders the Mermaid blocks; locally, any Markdown preview with Mermaid support will too. Column and file names match the code as of 24 Sep.

## 1. Component diagram

Who talks to whom, and over what.

```mermaid
flowchart LR
    subgraph Edge["Controller laptop"]
        watcher["wisl_ingest.edge<br/>LogUploader<br/><i>size-stable watch, SHA-256, manifest</i>"]
    end

    subgraph Browser["Browser"]
        console["sdth-demo console<br/>/demo/<br/><i>vanilla JS</i>"]
        replay["sdth-replay viewer<br/>/replay/?embed=1<br/><i>CesiumJS</i>"]
        console -- iframe --> replay
    end

    subgraph Platform["Platform process · uvicorn · 127.0.0.1:8010"]
        direction TB
        auth["auth.require_api_key"]
        ingest["ingest.py<br/>POST /v1/logs/upload<br/>GET /v1/uploads/{id}"]
        worker["local_worker → worker.process_raw_upload"]
        registry["parsers/registry<br/>parse_raw_log"]
        privacy["privacy.py<br/>redact, audit, retention"]
        canonical["canonical_series<br/>persist_canonical_series"]
        detectors["detectors.detect_incidents<br/><i>8 rules</i>"]
        incidents["incidents.index_flight<br/>patterns rebuild"]
        query["query.py · incident_api.py<br/>demo_api.py · bulletins.py"]
        pdf["pdf_report.py<br/>ReportLab + matplotlib"]
        tiles["tiles.py<br/>OSM tile cache"]
        static["StaticFiles<br/>/demo /replay /replay/lib"]
        db[("SQLite<br/>data/demo-console.db")]
        raw[("Raw uploads<br/>data/demo-uploads/")]
    end

    ollama["Ollama<br/>qwen2.5:7b-instruct<br/><i>optional, loopback</i>"]

    watcher -- "multipart + X-WISL-SHA256" --> ingest
    console -- "drag-and-drop" --> ingest
    console -- "/v1/* JSON" --> query
    console -- "/v1/flights/{id}/comprehensive-report" --> pdf
    replay -- "/v1/flights/{id}/path" --> query
    replay -- "/tiles/{z}/{x}/{y}" --> tiles
    Browser -- "GET" --> static

    ingest --> auth
    query --> auth
    ingest -- "bytes" --> raw
    ingest -- "raw_uploads row" --> db
    ingest -- "enqueue" --> worker
    worker --> registry
    registry -- "L1 payload" --> privacy
    privacy --> canonical
    canonical -- "canonical_records" --> db
    worker --> incidents
    incidents --> detectors
    incidents -- "incidents, incident_patterns" --> db
    query --> db
    pdf --> db
    query -. "hypotheses only" .-> ollama
```

## 2. Sequence diagram: one upload

What happens between dropping a file and "Ready to review". The `stage=` labels are the log lines printed in the launcher terminal.

```mermaid
sequenceDiagram
    autonumber
    actor Op as Operator / judge
    participant UI as Console (demo.js)
    participant API as ingest.py
    participant Q as local_worker
    participant W as worker.process_raw_upload
    participant P as parsers.registry
    participant C as canonical_series
    participant I as incidents.index_flight
    participant D as detectors
    participant DB as SQLite

    Op->>UI: drop file on Import log
    UI->>API: POST /v1/logs/upload (multipart, X-API-Key)
    API->>API: extension + size gate, stream SHA-256 to disk
    API->>DB: SELECT raw_uploads WHERE sha256 = ?
    alt digest already stored
        DB-->>API: existing row
        API-->>UI: 200 {upload_id: existing, status}
        Note over API: stage=received dedup=true
    else new digest
        API->>DB: INSERT raw_uploads (status=received)
        API->>Q: enqueue(upload_id)
        API-->>UI: 200 {upload_id, status: received}
        Note over API: stage=received dedup=false
        Q->>W: process_raw_upload(upload_id)
        W->>DB: UPDATE status=parsing
        W->>P: parse_raw_log(path, sha256, name)
        P-->>W: L1 payload, parser_key
        Note over W: stage=parsed records=N ms=…
        W->>W: privacy.redact_operator_locations
        W->>DB: INSERT flights, ingest_events (idempotency_key)
        W->>C: persist_canonical_series(L1)
        C->>DB: INSERT canonical_records (L2, validated)
        W->>DB: UPDATE raw_uploads provenance, status=normalizing
        Note over W: stage=canonical redactions=n ms=…
        W->>I: index_flight(flight_id)
        I->>DB: load L2 series
        I->>D: detect_incidents(series)
        D-->>I: [Incident]
        I->>DB: DELETE rule incidents; INSERT incidents; rebuild incident_patterns
        Note over W: stage=detected incidents=k types=…
        W->>Q: enqueue_translation_job(job_id)
        Note over W: stage=done total_ms=…
        Q->>W: process_translation_job(job_id)
        W->>DB: UPDATE status=detecting
        W->>I: index_flight(flight_id) (idempotent re-run)
        W->>DB: UPDATE status=ready
        W->>W: chart_export.export_charts_for_flight
    end
    loop until ready
        UI->>API: GET /v1/uploads/{id}
        API-->>UI: {status}
    end
    UI->>API: GET /v1/flights/{id}, /incidents, /path
    UI-->>Op: Ready to review
```

## 3. Data model

The tables the demo actually touches. JSON columns hold the parts of the schema that vary by vendor.

```mermaid
erDiagram
    raw_uploads {
        TEXT id PK
        TEXT sha256 UK
        TEXT original_name
        TEXT stored_path
        INTEGER size_bytes
        TEXT status "received|parsing|normalizing|detecting|ready|failed"
        TEXT flight_id FK
        TEXT ingest_id FK
        TEXT error
        TEXT provenance_json
    }
    flights {
        TEXT id PK "flight-{sha256[:20]}"
        TEXT source
        TEXT started_at
        TEXT ended_at
    }
    ingest_events {
        TEXT id PK
        TEXT flight_id FK
        TEXT payload_json "L1"
        TEXT idempotency_key UK
    }
    canonical_records {
        TEXT id PK
        TEXT ingest_id FK
        TEXT flight_id FK
        TEXT recorded_at
        TEXT canonical_json "L2: position, attitude, battery, sensors, metadata"
        INTEGER validation_ok
    }
    incidents {
        TEXT id PK
        TEXT flight_id FK
        TEXT incident_type
        TEXT severity "info|warning|critical"
        TEXT detector "rule|llm"
        TEXT started_at
        TEXT ended_at
        TEXT signature
        TEXT summary
        TEXT evidence_json "samples, position, hazard"
    }
    incident_patterns {
        TEXT id PK
        TEXT signature UK
        TEXT incident_type
        INTEGER flight_count
        INTEGER incident_count
        TEXT max_severity
    }
    mitigation_bulletins {
        TEXT id PK
        TEXT signature
        TEXT incident_type
        INTEGER flight_count
        TEXT bulletin_json
    }
    audit_events {
        TEXT id PK
        TEXT event_type
        TEXT subject
        TEXT detail_json
    }
    comprehensive_reports {
        TEXT id PK
        TEXT flight_id FK
        INTEGER incident_count
    }

    raw_uploads ||--o| flights : "resolves to"
    raw_uploads ||--o| ingest_events : "produces"
    flights ||--o{ ingest_events : "has"
    ingest_events ||--o{ canonical_records : "projects to"
    flights ||--o{ canonical_records : "L2 series"
    flights ||--o{ incidents : "flagged by"
    incidents }o--|| incident_patterns : "grouped by signature"
    incident_patterns ||--o{ mitigation_bulletins : "reviewed as"
    flights ||--o{ comprehensive_reports : "summarised in"
    flights ||--o{ audit_events : "redaction logged"
```

## 4. Upload state machine

The `status` column on `raw_uploads`, which is what the console polls.

```mermaid
stateDiagram-v2
    [*] --> received : POST /v1/logs/upload
    received --> parsing : worker picks up job
    parsing --> normalizing : L1 parsed, L2 persisted, first index_flight
    normalizing --> detecting : follow-up job picked up
    detecting --> ready : index_flight re-run, charts exported
    detecting --> failed : indexing error
    parsing --> failed : unsupported or corrupt
    normalizing --> failed : schema violation
    ready --> [*]
    failed --> [*]
    note right of received
        Same sha256 again returns
        the existing row here
    end note
```

Related reading: [`ARCHITECTURE.md`](ARCHITECTURE.md) for the prose and trade-offs, `sdth-telemetry/openapi/openapi.yaml` for the full API contract.
