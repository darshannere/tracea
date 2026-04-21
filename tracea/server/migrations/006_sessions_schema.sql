-- 006_sessions_schema.sql: Fix sessions table to match API contract
--
-- Adds missing columns and renames total_cost_usd → total_cost so the
-- sessions API response matches the dashboard frontend model.

ALTER TABLE sessions RENAME COLUMN total_cost_usd TO total_cost;
ALTER TABLE sessions ADD COLUMN ended_at TEXT;
ALTER TABLE sessions ADD COLUMN duration_ms INTEGER DEFAULT 0;
ALTER TABLE sessions ADD COLUMN total_tokens INTEGER NOT NULL DEFAULT 0;
