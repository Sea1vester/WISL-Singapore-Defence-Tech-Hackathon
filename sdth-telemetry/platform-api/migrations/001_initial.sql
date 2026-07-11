-- flights: one row per flight session
CREATE TABLE IF NOT EXISTS flights (
  id            TEXT PRIMARY KEY,
  source        TEXT NOT NULL,
  started_at    TEXT NOT NULL,
  ended_at      TEXT,
  created_at    TEXT DEFAULT (datetime('now'))
);

-- ingest_events: raw L1 payloads as received
CREATE TABLE IF NOT EXISTS ingest_events (
  id              TEXT PRIMARY KEY,
  flight_id       TEXT REFERENCES flights(id),
  received_at     TEXT DEFAULT (datetime('now')),
  payload_json    TEXT NOT NULL,
  idempotency_key TEXT UNIQUE
);

-- canonical_records: L2 output from LLM
CREATE TABLE IF NOT EXISTS canonical_records (
  id             TEXT PRIMARY KEY,
  ingest_id      TEXT REFERENCES ingest_events(id),
  flight_id      TEXT REFERENCES flights(id),
  recorded_at    TEXT NOT NULL,
  canonical_json TEXT NOT NULL,
  llm_model      TEXT,
  llm_latency_ms INTEGER,
  validation_ok  INTEGER DEFAULT 0
);

-- translation_jobs: async pipeline state
CREATE TABLE IF NOT EXISTS translation_jobs (
  id         TEXT PRIMARY KEY,
  ingest_id  TEXT REFERENCES ingest_events(id),
  status     TEXT CHECK(status IN ('pending','running','done','failed')),
  error      TEXT,
  created_at TEXT DEFAULT (datetime('now')),
  updated_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_canonical_flight_time ON canonical_records(flight_id, recorded_at);
CREATE INDEX IF NOT EXISTS idx_jobs_status ON translation_jobs(status);
