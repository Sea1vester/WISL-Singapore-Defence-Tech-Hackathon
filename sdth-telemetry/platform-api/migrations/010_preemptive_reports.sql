-- preemptive_reports: one row per generated pre-mission-planning PDF for a flight.
-- The PDF itself is stored on disk under settings.reports_dir; report_json holds
-- the same structured findings the PDF was rendered from, for API consumers that
-- want the data without the binary.
CREATE TABLE IF NOT EXISTS preemptive_reports (
  id             TEXT PRIMARY KEY,
  flight_id      TEXT NOT NULL REFERENCES flights(id),
  stored_path    TEXT NOT NULL,
  report_json    TEXT NOT NULL,
  incident_count INTEGER NOT NULL DEFAULT 0,
  created_at     TEXT DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_preemptive_reports_flight ON preemptive_reports(flight_id, created_at);
