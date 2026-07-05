-- 014_make_detection_idempotent.sql: Create unique index to ensure rule execution is idempotent
CREATE UNIQUE INDEX IF NOT EXISTS idx_issues_rule_event
    ON issues(rule_id, event_id);
