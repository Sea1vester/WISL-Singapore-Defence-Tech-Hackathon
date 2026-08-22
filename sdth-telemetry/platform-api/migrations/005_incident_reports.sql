CREATE TABLE IF NOT EXISTS incident_reports (
  id                 TEXT PRIMARY KEY,
  flight_id          TEXT NOT NULL REFERENCES flights(id),
  report_json        TEXT NOT NULL,
  model_enrichment   TEXT NOT NULL,
  created_at         TEXT DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_incident_reports_flight ON incident_reports(flight_id, created_at);
