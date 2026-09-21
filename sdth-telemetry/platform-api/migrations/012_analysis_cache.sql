CREATE TABLE IF NOT EXISTS analysis_cache (
  cache_key   TEXT PRIMARY KEY,
  created_at  TEXT DEFAULT (datetime('now')),
  model       TEXT NOT NULL,
  response_json TEXT NOT NULL
);
