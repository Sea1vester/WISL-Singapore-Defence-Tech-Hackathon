CREATE TABLE IF NOT EXISTS audit_events (
  id          TEXT PRIMARY KEY,
  event_type  TEXT NOT NULL,
  subject     TEXT,
  detail_json TEXT NOT NULL,
  created_at  TEXT DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_audit_events_type ON audit_events(event_type, created_at);
