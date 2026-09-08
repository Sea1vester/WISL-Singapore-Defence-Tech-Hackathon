-- frame_census: per-frame VisDrone class counts attached to a camera_frame visual.
-- counts_json stores the full census blob (class_counts for 10 classes + cars/people HUD).
-- Keyed by visual_id; (flight_id, recorded_at) supports nearest-t prefetch for replay.
CREATE TABLE IF NOT EXISTS frame_census (
  visual_id      TEXT PRIMARY KEY REFERENCES visual_records(id) ON DELETE CASCADE,
  flight_id      TEXT NOT NULL REFERENCES flights(id),
  recorded_at    TEXT NOT NULL,
  counts_json    TEXT NOT NULL,
  created_at     TEXT DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_frame_census_flight ON frame_census(flight_id, recorded_at);
