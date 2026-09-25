# WISL architecture atlas

**Recorded logs → canonical telemetry → reviewable evidence.**

Four views of the local demo: a layered component map, a three-part upload sequence, the data model, and the upload lifecycle. The component and sequence views are SVGs, so they display without a Mermaid plugin and stay sharp when enlarged. Expand the source sections for the detailed interface map and editable sequence definitions.

**Viewing on GitHub:** the diagrams below render directly in this page. For the standalone HTML layout, download [`architecture.html`](architecture.html) and open it in a browser. It includes an interactive backend data-flow diagram with click-to-explore details and all four reference diagrams. Its inline JavaScript works offline, without external dependencies or review-tool UI; GitHub's file viewer shows HTML source rather than running the page.

## 1. Component map

Read from top to bottom: **amber** entry points, **blue** platform processing and review, **green** persistence. The **purple** model is optional and outside the platform process. Numbered processing steps show order; the surrounding groups show responsibility, not independently deployed services.

![WISL component map: operator entry points above a three-stage local evidence pipeline, review services, storage, and an optional model.](diagrams/components.svg)

[Open the full-size component map](diagrams/components.svg). The layered map is editable directly as SVG; the detailed connection view below is Mermaid.

<details>
<summary>Detailed interface map · API routes, modules and connections</summary>

```mermaid
%%{init: {"theme":"base","themeCSS":"text { font-family: Arial, sans-serif !important; }","themeVariables":{"fontFamily":"Arial, sans-serif","fontSize":"15px","primaryColor":"#e4f0fa","primaryTextColor":"#183047","primaryBorderColor":"#8eb3cf","lineColor":"#73869a","clusterBkg":"#f6f9fc","clusterBorder":"#c8d6e2"},"flowchart":{"curve":"basis","nodeSpacing":30,"rankSpacing":60}}}%%
flowchart TB
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

    classDef entry fill:#fff3c9,stroke:#d6b85d,color:#51411b,rx:10,ry:10
    classDef service fill:#e4f0fa,stroke:#8eb3cf,color:#183047,rx:10,ry:10
    classDef evidence fill:#dceecf,stroke:#92b577,color:#294c2d
    classDef optional fill:#eee7f7,stroke:#b09ac8,color:#58406e,rx:10,ry:10
    class watcher,console,replay entry
    class auth,ingest,worker,registry,privacy,canonical,detectors,incidents,query,pdf,tiles,static service
    class db,raw evidence
    class ollama optional
    style Edge fill:#fffaf0,stroke:#e3ce92
    style Browser fill:#fffaf0,stroke:#e3ce92
    style Platform fill:#f4f8fc,stroke:#b9d2e8
```

</details>

## 2. Upload journey

One upload, shown in three acts instead of ten simultaneous lifelines. **Amber** is receipt, **blue** is canonical processing, and **green** is evidence and review. Solid arrows are calls; dashed arrows are responses. The `stage=` notes are launcher log events, not upload statuses.

### A. Receive & acknowledge

The operator drops a file in the console. The API authenticates, checks the upload, and looks up its checksum. An existing digest reuses its upload record; only new content enters the worker queue.

![Upload sequence A: the console submits a file, the API validates and checks its checksum, then reuses an existing upload or queues new content.](diagrams/upload-receive.svg)

<details>
<summary>Editable Mermaid source · receive & acknowledge</summary>

```mermaid
%%{init: {"theme":"base","themeCSS":"text { font-family: Arial, sans-serif !important; }","themeVariables":{"fontFamily":"Arial, sans-serif","fontSize":"16px","actorBkg":"#fff3c9","actorBorder":"#d6b85d","actorTextColor":"#51411b","actorLineColor":"#c5ccd4","signalColor":"#52677a","signalTextColor":"#183047","labelBoxBkgColor":"#fff8e3","labelBoxBorderColor":"#dcc98e","labelTextColor":"#51411b","loopTextColor":"#51411b","noteBkgColor":"#fff8e3","noteBorderColor":"#dcc98e","noteTextColor":"#51411b","activationBkgColor":"#f9e4a0","activationBorderColor":"#d6b85d","sequenceNumberColor":"#fff"},"sequence":{"actorFontFamily":"Arial","noteFontFamily":"Arial","messageFontFamily":"Arial","actorFontWeight":600,"mirrorActors":false,"actorMargin":45,"width":150,"height":54,"boxMargin":14,"noteMargin":18,"messageMargin":36,"diagramMarginX":28,"diagramMarginY":24}}}%%
sequenceDiagram
    autonumber
    participant UI as Console
    participant API as Upload API
    participant DB as SQLite
    participant Q as Local queue

    Note over UI: Operator drops a recorded log
    UI->>API: POST /v1/logs/upload<br/>multipart + X-API-Key
    activate API
    API->>API: Validate extension + size<br/>Stream to disk + SHA-256
    API->>DB: Find raw_uploads by checksum
    DB-->>API: Existing row or no match
    alt Checksum already stored
        API-->>UI: 202 · existing upload_id + status<br/>duplicate=true
        Note over API: stage=received · dedup=true
    else New content
        API->>DB: Save raw_uploads row<br/>status=received
        API->>Q: enqueue_raw_upload(upload_id)
        API-->>UI: 202 · new upload_id<br/>status=received
        Note over API: stage=received · dedup=false
    end
    deactivate API
```

</details>

### B. Turn raw bytes into canonical evidence

The local worker dispatches `process_raw_upload`. Parsing returns L1; privacy handling and canonical projection produce the validated L2 series. The diagram groups privacy and canonical code in one lifeline to keep the flow readable.

![Upload sequence B: a raw-upload worker parses L1, redacts operator locations when enabled, and persists validated L2 records and provenance.](diagrams/upload-canonical.svg)

<details>
<summary>Editable Mermaid source · canonical processing</summary>

```mermaid
%%{init: {"theme":"base","themeCSS":"text { font-family: Arial, sans-serif !important; }","themeVariables":{"fontFamily":"Arial, sans-serif","fontSize":"16px","actorBkg":"#e4f0fa","actorBorder":"#8eb3cf","actorTextColor":"#183047","actorLineColor":"#c5ccd4","signalColor":"#52677a","signalTextColor":"#183047","labelBoxBkgColor":"#f0f6fc","labelBoxBorderColor":"#b9d2e8","labelTextColor":"#183047","loopTextColor":"#183047","noteBkgColor":"#f0f6fc","noteBorderColor":"#b9d2e8","noteTextColor":"#183047","activationBkgColor":"#c9e0f2","activationBorderColor":"#8eb3cf","sequenceNumberColor":"#fff"},"sequence":{"actorFontFamily":"Arial","noteFontFamily":"Arial","messageFontFamily":"Arial","actorFontWeight":600,"mirrorActors":false,"actorMargin":45,"width":150,"height":54,"boxMargin":14,"noteMargin":18,"messageMargin":36,"diagramMarginX":28,"diagramMarginY":24}}}%%
sequenceDiagram
    autonumber
    participant W as Raw-upload worker
    participant P as Parser registry
    participant C as Privacy + canonical
    participant DB as SQLite

    Note over W: local_worker → process_raw_upload
    W->>DB: Set status=parsing
    W->>P: parse_raw_log(path, sha256, name)
    activate P
    P-->>W: L1 payload + parser_key
    deactivate P
    Note over W,P: stage=parsed · records=N
    W->>C: Redact operator / home locations<br/>when enabled
    C-->>W: Redacted L1 + redaction list
    W->>DB: Save flight, L1 ingest event<br/>and pending translation job
    W->>C: persist_canonical_series(L1)
    activate C
    C->>DB: Persist validated L2 records
    C-->>W: Canonical series persisted
    deactivate C
    W->>DB: Save provenance + redaction audit<br/>Apply retention · status=normalizing
    Note over W,DB: stage=canonical · redactions=n
```

</details>

### C. Detect, finalise & review

The indexer runs deterministic detectors, stores their evidence, and rebuilds fleet patterns. The follow-up queue job calls `process_job` and re-indexes idempotently before marking the upload ready. The console polls while background work runs; it stops on `ready` or `failed`.

![Upload sequence C: deterministic incidents are indexed, a follow-up job marks the upload ready, and the console polls for completion before loading the evidence.](diagrams/upload-review.svg)

<details>
<summary>Editable Mermaid source · detect & review</summary>

```mermaid
%%{init: {"theme":"base","themeCSS":"text { font-family: Arial, sans-serif !important; }","themeVariables":{"fontFamily":"Arial, sans-serif","fontSize":"16px","actorBkg":"#dceecf","actorBorder":"#92b577","actorTextColor":"#294c2d","actorLineColor":"#c5ccd4","signalColor":"#52677a","signalTextColor":"#183047","labelBoxBkgColor":"#f1f8eb","labelBoxBorderColor":"#bad0a8","labelTextColor":"#294c2d","loopTextColor":"#294c2d","noteBkgColor":"#f1f8eb","noteBorderColor":"#bad0a8","noteTextColor":"#294c2d","activationBkgColor":"#c9e1b8","activationBorderColor":"#92b577","sequenceNumberColor":"#fff"},"sequence":{"actorFontFamily":"Arial","noteFontFamily":"Arial","messageFontFamily":"Arial","actorFontWeight":600,"mirrorActors":false,"actorMargin":45,"width":150,"height":54,"boxMargin":14,"noteMargin":18,"messageMargin":36,"diagramMarginX":28,"diagramMarginY":24}}}%%
sequenceDiagram
    autonumber
    participant UI as Console
    participant API as Review APIs
    participant W as Worker + queue
    participant I as Indexer + rules
    participant DB as SQLite

    par Background evidence processing
        W->>I: index_flight(flight_id)
        activate I
        I->>DB: Load L2 series
        DB-->>I: Canonical telemetry
        I->>I: detect_incidents(series)<br/>Eight deterministic rules
        I->>DB: Replace rule incidents<br/>Rebuild incident_patterns
        I-->>W: Incident count + types
        deactivate I
        Note over W,I: stage=detected
        W->>W: Enqueue follow-up translation job
        Note over W: stage=done · raw-upload task only
        W->>W: Queue dispatches process_job(job_id)
        W->>DB: Set status=detecting
        W->>I: index_flight(flight_id)<br/>Idempotent re-run
        I-->>W: Index complete
        W->>DB: Set status=ready
        W->>W: Export charts (best effort)
    and Console watches upload status
        loop While upload is processing
            UI->>API: GET /v1/uploads/{id}
            API->>DB: Read upload status
            DB-->>API: Status + flight_id / error
            API-->>UI: Current upload state
        end
    end
    UI->>API: On ready: GET flight,<br/>incidents and path
    API-->>UI: Stored evidence for review
    Note over UI: Ready to review<br/>On failed: show upload error instead
```

</details>

**Reading the boundaries.** A duplicate keeps its existing state; it does not necessarily mean `ready`. The `stage=done` log closes the raw-upload task, not the entire journey. Chart export happens after the `ready` update and is best effort. These sequences show the default local-demo path with ingestion model enrichment disabled; upload rejection and processing failures are summarised in the lifecycle below.

## 3. Data model

The tables the demo actually touches. JSON columns hold the parts of the schema that vary by vendor.

```mermaid
%%{init: {"theme":"base","themeCSS":"text { font-family: Arial, sans-serif !important; }","themeVariables":{"fontFamily":"Arial, sans-serif","primaryColor":"#e4f0fa","primaryTextColor":"#183047","primaryBorderColor":"#8eb3cf","lineColor":"#73869a","tertiaryColor":"#f4f8fc"}}}%%
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

The `status` column on `raw_uploads`, which is what the console polls. Requests rejected by authentication, extension, size or checksum checks do not create an upload row. Re-uploading an existing checksum returns that row in its current state, without resetting it.

```mermaid
%%{init: {"theme":"base","themeCSS":"text { font-family: Arial, sans-serif !important; }","themeVariables":{"fontFamily":"Arial, sans-serif","primaryColor":"#e4f0fa","primaryTextColor":"#183047","primaryBorderColor":"#8eb3cf","lineColor":"#73869a","tertiaryColor":"#f4f8fc"}}}%%
stateDiagram-v2
    [*] --> received : New checksum accepted
    received --> parsing : Raw-upload worker starts
    parsing --> normalizing : L1 + validated L2 persisted
    normalizing --> detecting : Follow-up process_job starts detection
    detecting --> ready : Idempotent index completes
    detecting --> failed : Indexing error
    parsing --> failed : Parse or canonical validation error
    normalizing --> failed : Raw-upload task error
    ready --> [*]
    failed --> [*]

    classDef receipt fill:#fff3c9,stroke:#d6b85d,color:#51411b
    classDef processing fill:#e4f0fa,stroke:#8eb3cf,color:#183047
    classDef success fill:#dceecf,stroke:#92b577,color:#294c2d
    classDef failure fill:#fbe3df,stroke:#d7988e,color:#7f3830
    class received receipt
    class parsing,normalizing,detecting processing
    class ready success
    class failed failure
```

## Editing & exporting

- **Component map:** edit [`diagrams/components.svg`](diagrams/components.svg). It uses native SVG text and shapes, with no external fonts or assets.
- **Sequences:** edit the Mermaid blocks above, then run `python3 docs/diagrams/render.py` from the repository root. The renderer validates all six Mermaid blocks and rebuilds the three sequence SVGs using pinned Mermaid CLI `11.12.0`. It requires Node/npm and Chrome; set `PUPPETEER_EXECUTABLE_PATH` if Chrome is not in a standard location. The first run downloads the renderer with npm, without adding an application dependency.
- **Interactive HTML:** edit the data-flow diagram and interactions in [`architecture.html`](architecture.html). The same command refreshes its embedded package/decision data from [`ARCHITECTURE.md`](ARCHITECTURE.md), the four reference diagrams, and the static backend SVG. Use `--html-only` to skip Mermaid rendering. Commit the HTML alongside the SVGs. Download and open it directly in a browser to present, explore, or print; no review tool, server, or network access is needed.

Related reading: [`ARCHITECTURE.md`](ARCHITECTURE.md) for the prose and trade-offs, [`openapi.yaml`](../sdth-telemetry/openapi/openapi.yaml) for the full API contract.
