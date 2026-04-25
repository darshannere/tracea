-- 009_add_user_id.sql: Add user_id for team multi-user filtering

-- Track which team member sent each event
ALTER TABLE events ADD COLUMN user_id TEXT DEFAULT '';

-- Track user on sessions for fast filtering
ALTER TABLE sessions ADD COLUMN user_id TEXT DEFAULT '';

-- Index for fast user-based session lookups
CREATE INDEX IF NOT EXISTS idx_events_user_ts
    ON events(user_id, timestamp DESC)
    WHERE user_id IS NOT NULL AND user_id != '';

-- Index for user-based session filtering
CREATE INDEX IF NOT EXISTS idx_sessions_user
    ON sessions(user_id, last_event_at DESC)
    WHERE user_id IS NOT NULL AND user_id != '';
