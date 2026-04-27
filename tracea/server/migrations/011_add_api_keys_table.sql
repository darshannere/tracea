CREATE TABLE IF NOT EXISTS api_keys (
    key_hash   TEXT PRIMARY KEY,
    user_id    TEXT NOT NULL,
    name       TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    last_used  TEXT,
    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_api_keys_user_id ON api_keys(user_id);
