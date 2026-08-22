CREATE TABLE IF NOT EXISTS raw_uploads (
  id             TEXT PRIMARY KEY,
  sha256         TEXT NOT NULL UNIQUE,
  original_name  TEXT NOT NULL,
  stored_path    TEXT NOT NULL,
  size_bytes     INTEGER NOT NULL,
  status         TEXT NOT NULL CHECK(status IN (
    'received', 'parsing', 'normalizing', 'detecting', 'ready', 'failed'
  )),
  flight_id      TEXT REFERENCES flights(id),
  ingest_id      TEXT REFERENCES ingest_events(id),
  error          TEXT,
  provenance_json TEXT NOT NULL DEFAULT '{}',
  received_at    TEXT DEFAULT (datetime('now')),
  updated_at     TEXT DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_raw_uploads_status ON raw_uploads(status);
