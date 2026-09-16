-- comprehensive_reports: one row per generated comprehensive mission PDF for a
-- flight. Combines the evidence-backed incident report, the pre-emptive
-- planning findings, and any fleet-wide recurring-pattern matches into one
-- document. The PDF itself is stored on disk under settings.reports_dir;
-- report_json holds the same structured findings the PDF was rendered from.
CREATE TABLE IF NOT EXISTS comprehensive_reports (
  id             TEXT PRIMARY KEY,
  flight_id      TEXT NOT NULL REFERENCES flights(id),
  stored_path    TEXT NOT NULL,
  report_json    TEXT NOT NULL,
  incident_count INTEGER NOT NULL DEFAULT 0,
  created_at     TEXT DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_comprehensive_reports_flight ON comprehensive_reports(flight_id, created_at);
