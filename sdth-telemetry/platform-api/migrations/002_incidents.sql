-- incidents: one detected failure window (rule) or one LLM report per flight
CREATE TABLE IF NOT EXISTS incidents (
  id             TEXT PRIMARY KEY,
  flight_id      TEXT NOT NULL REFERENCES flights(id),
  source         TEXT NOT NULL,
  brand          TEXT NOT NULL,
  incident_type  TEXT NOT NULL,
  severity       TEXT NOT NULL CHECK (severity IN ('info', 'warning', 'critical')),
  detector       TEXT NOT NULL CHECK (detector IN ('rule', 'llm')),
  started_at     TEXT NOT NULL,
  ended_at       TEXT,
  signature      TEXT NOT NULL,
  summary        TEXT NOT NULL,
  evidence_json  TEXT NOT NULL,
  created_at     TEXT DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_incidents_flight ON incidents(flight_id, started_at);
CREATE INDEX IF NOT EXISTS idx_incidents_signature ON incidents(signature);
CREATE INDEX IF NOT EXISTS idx_incidents_brand_type ON incidents(brand, incident_type);
CREATE INDEX IF NOT EXISTS idx_incidents_detector ON incidents(detector);

-- incident_patterns: recurring signatures across missions (rebuilt after each index)
CREATE TABLE IF NOT EXISTS incident_patterns (
  id              TEXT PRIMARY KEY,
  signature       TEXT UNIQUE NOT NULL,
  incident_type   TEXT NOT NULL,
  flight_count    INTEGER NOT NULL,
  incident_count  INTEGER NOT NULL,
  first_seen_at   TEXT,
  last_seen_at    TEXT,
  max_severity    TEXT,
  summary         TEXT,
  updated_at      TEXT
);

CREATE INDEX IF NOT EXISTS idx_patterns_flight_count ON incident_patterns(flight_count DESC);

-- incident_index_runs: audit + edge timing for each indexing pass
CREATE TABLE IF NOT EXISTS incident_index_runs (
  id              TEXT PRIMARY KEY,
  flight_id       TEXT NOT NULL REFERENCES flights(id),
  status          TEXT NOT NULL CHECK (status IN ('done', 'failed')),
  sample_count    INTEGER,
  incident_count  INTEGER,
  duration_ms     INTEGER,
  error           TEXT,
  created_at      TEXT DEFAULT (datetime('now'))
);
