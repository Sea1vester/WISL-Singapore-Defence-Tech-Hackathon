CREATE TABLE IF NOT EXISTS mitigation_bulletins (
  id             TEXT PRIMARY KEY,
  signature      TEXT NOT NULL,
  incident_type  TEXT NOT NULL,
  flight_count   INTEGER NOT NULL,
  bulletin_json  TEXT NOT NULL,
  created_at     TEXT DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_bulletins_signature ON mitigation_bulletins(signature);
