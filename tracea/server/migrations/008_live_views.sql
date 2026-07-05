-- 008_observagent_support.sql: Add columns and indexes for ObservAgent-style live views

-- Short tool summary for log rows (extracted from content or set by SDK)
ALTER TABLE events ADD COLUMN tool_summary TEXT;

-- Index for fast tool event queries (the core of the live log view)
CREATE INDEX IF NOT EXISTS idx_events_tool_type_ts
    ON events(type, timestamp DESC)
    WHERE type IN ('tool_call', 'tool_result', 'error');

-- Index for agent activity lookups
CREATE INDEX IF NOT EXISTS idx_events_agent_ts
    ON events(agent_id, timestamp DESC)
    WHERE agent_id IS NOT NULL AND agent_id != '';
