-- 003_add_detection_columns.sql: Extend issues table with detection metadata
-- Required by DET-08: category, severity, session_id, event_ids, rca_status,
-- plus captured_values, session aggregates, rule config snapshot

ALTER TABLE issues ADD COLUMN rule_id TEXT;
ALTER TABLE issues ADD COLUMN rule_description TEXT;
ALTER TABLE issues ADD COLUMN captured_values TEXT;
ALTER TABLE issues ADD COLUMN session_cost_total REAL DEFAULT 0;
ALTER TABLE issues ADD COLUMN session_duration_ms INTEGER DEFAULT 0;
ALTER TABLE issues ADD COLUMN session_event_count INTEGER DEFAULT 0;
ALTER TABLE issues ADD COLUMN first_event_id TEXT;
ALTER TABLE issues ADD COLUMN last_event_id TEXT;
ALTER TABLE issues ADD COLUMN error_message TEXT;
ALTER TABLE issues ADD COLUMN session_metadata TEXT;
ALTER TABLE issues ADD COLUMN rule_config_snapshot TEXT;

CREATE INDEX IF NOT EXISTS idx_issues_rule_id ON issues(rule_id);