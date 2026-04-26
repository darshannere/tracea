-- 010_add_users_table.sql: Create users table for team management

CREATE TABLE IF NOT EXISTS users (
    user_id    TEXT PRIMARY KEY,
    name       TEXT,
    email      TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
