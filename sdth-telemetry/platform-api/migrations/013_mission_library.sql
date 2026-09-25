CREATE TABLE IF NOT EXISTS mission_folders (
    id TEXT PRIMARY KEY,
    parent_id TEXT REFERENCES mission_folders(id),
    name TEXT NOT NULL,
    name_key TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_mission_folder_name
    ON mission_folders(COALESCE(parent_id, ''), name_key);

CREATE TABLE IF NOT EXISTS mission_folder_entries (
    flight_id TEXT PRIMARY KEY REFERENCES flights(id) ON DELETE CASCADE,
    folder_id TEXT NOT NULL REFERENCES mission_folders(id)
);

CREATE INDEX IF NOT EXISTS idx_mission_folder_entries ON mission_folder_entries(folder_id);
