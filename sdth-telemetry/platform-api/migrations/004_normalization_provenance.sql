CREATE TABLE IF NOT EXISTS normalization_provenance (
  canonical_record_id TEXT PRIMARY KEY REFERENCES canonical_records(id) ON DELETE CASCADE,
  parser              TEXT NOT NULL,
  source_format       TEXT NOT NULL,
  schema_version      TEXT NOT NULL,
  validation_status   TEXT NOT NULL,
  value_origin        TEXT NOT NULL,
  created_at          TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS normalization_enrichments (
  id              TEXT PRIMARY KEY,
  ingest_id       TEXT NOT NULL REFERENCES ingest_events(id),
  flight_id       TEXT NOT NULL REFERENCES flights(id),
  enrichment_json TEXT NOT NULL,
  llm_model        TEXT,
  llm_latency_ms   INTEGER,
  validation_ok    INTEGER NOT NULL DEFAULT 0,
  created_at       TEXT DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_enrichments_flight ON normalization_enrichments(flight_id);
