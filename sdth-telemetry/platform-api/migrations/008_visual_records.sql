-- visual_records: one row per visual asset (screenshot, chart, camera frame)
-- linked to a flight, optionally to a specific incident or canonical record.
-- Files are stored on disk; stored_path is relative to VISUALS_DIR.
CREATE TABLE IF NOT EXISTS visual_records (
  id             TEXT PRIMARY KEY,
  flight_id      TEXT NOT NULL REFERENCES flights(id),
  incident_id    TEXT REFERENCES incidents(id),
  record_id      TEXT REFERENCES canonical_records(id),
  recorded_at    TEXT NOT NULL,
  kind           TEXT NOT NULL CHECK (kind IN (
    'cesium_screenshot',
    'sensor_chart',
    'camera_frame',
    'custom'
  )),
  stored_path    TEXT NOT NULL,
  mime_type      TEXT NOT NULL DEFAULT 'image/png',
  size_bytes     INTEGER,
  caption        TEXT,
  source         TEXT CHECK (source IN ('replay', 'parser', 'worker', 'user')),
  created_at     TEXT DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_visuals_flight    ON visual_records(flight_id, recorded_at);
CREATE INDEX IF NOT EXISTS idx_visuals_incident  ON visual_records(incident_id);
CREATE INDEX IF NOT EXISTS idx_visuals_record    ON visual_records(record_id);
CREATE INDEX IF NOT EXISTS idx_visuals_kind      ON visual_records(kind);
