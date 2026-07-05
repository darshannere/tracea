-- 015_add_retention_cascades.sql: Add ON DELETE CASCADE to foreign keys and trigger for events

-- Disable foreign key constraints temporarily to allow table rebuilds
PRAGMA foreign_keys = OFF;

-- 1. Create trigger to cascade delete events when a session is deleted
CREATE TRIGGER IF NOT EXISTS tgr_delete_session_events
AFTER DELETE ON sessions
BEGIN
    DELETE FROM events WHERE session_id = old.session_id;
END;


-- 2. Rebuild issues table to add ON DELETE CASCADE
CREATE TABLE new_issues (
    issue_id     TEXT PRIMARY KEY,
    session_id   TEXT NOT NULL,
    event_id     TEXT NOT NULL,
    rule_name    TEXT,
    issue_type   TEXT NOT NULL,
    severity     TEXT NOT NULL DEFAULT 'medium',
    detected_at  TEXT NOT NULL DEFAULT (datetime('now')),
    rca_status   TEXT NOT NULL DEFAULT 'pending',
    rca_text     TEXT,
    rule_id      TEXT,
    rule_description TEXT,
    captured_values TEXT,
    session_cost_total REAL DEFAULT 0,
    session_duration_ms INTEGER DEFAULT 0,
    session_event_count INTEGER DEFAULT 0,
    first_event_id TEXT,
    last_event_id TEXT,
    error_message TEXT,
    session_metadata TEXT,
    rule_config_snapshot TEXT,
    rca_structured TEXT,
    FOREIGN KEY (session_id) REFERENCES sessions(session_id) ON DELETE CASCADE,
    FOREIGN KEY (event_id) REFERENCES events(event_id) ON DELETE CASCADE
);

INSERT INTO new_issues (
    issue_id, session_id, event_id, rule_name, issue_type, severity,
    detected_at, rca_status, rca_text, rule_id, rule_description,
    captured_values, session_cost_total, session_duration_ms,
    session_event_count, first_event_id, last_event_id, error_message,
    session_metadata, rule_config_snapshot, rca_structured
)
SELECT
    issue_id, session_id, event_id, rule_name, issue_type, severity,
    detected_at, rca_status, rca_text, rule_id, rule_description,
    captured_values, session_cost_total, session_duration_ms,
    session_event_count, first_event_id, last_event_id, error_message,
    session_metadata, rule_config_snapshot, rca_structured
FROM issues;

DROP TABLE issues;
ALTER TABLE new_issues RENAME TO issues;

-- Recreate indexes on issues
CREATE INDEX IF NOT EXISTS idx_issues_session ON issues(session_id, detected_at DESC);
CREATE INDEX IF NOT EXISTS idx_issues_rule_id ON issues(rule_id);
CREATE UNIQUE INDEX IF NOT EXISTS idx_issues_rule_event ON issues(rule_id, event_id);


-- 3. Rebuild alerts table to add ON DELETE CASCADE
CREATE TABLE new_alerts (
    alert_id     TEXT PRIMARY KEY,
    issue_id     TEXT NOT NULL,
    route_type   TEXT NOT NULL,
    webhook_url  TEXT NOT NULL,
    status       TEXT NOT NULL DEFAULT 'pending',
    attempts     INTEGER NOT NULL DEFAULT 0,
    sent_at      TEXT,
    error        TEXT,
    FOREIGN KEY (issue_id) REFERENCES issues(issue_id) ON DELETE CASCADE
);

INSERT INTO new_alerts (
    alert_id, issue_id, route_type, webhook_url, status, attempts, sent_at, error
)
SELECT
    alert_id, issue_id, route_type, webhook_url, status, attempts, sent_at, error
FROM alerts;

DROP TABLE alerts;
ALTER TABLE new_alerts RENAME TO alerts;


-- 4. Rebuild webhook_failures table to add ON DELETE CASCADE
CREATE TABLE new_webhook_failures (
    id            TEXT PRIMARY KEY,
    issue_id      TEXT NOT NULL,
    destination_url TEXT NOT NULL,
    status_code   INTEGER,
    response_body TEXT,
    attempt_count INTEGER NOT NULL DEFAULT 0,
    created_at    TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (issue_id) REFERENCES issues(issue_id) ON DELETE CASCADE
);

INSERT INTO new_webhook_failures (
    id, issue_id, destination_url, status_code, response_body, attempt_count, created_at
)
SELECT
    id, issue_id, destination_url, status_code, response_body, attempt_count, created_at
FROM webhook_failures;

DROP TABLE webhook_failures;
ALTER TABLE new_webhook_failures RENAME TO webhook_failures;

-- Recreate indexes on webhook_failures
CREATE INDEX IF NOT EXISTS idx_webhook_failures_issue ON webhook_failures(issue_id);

-- Re-enable foreign key constraints
PRAGMA foreign_keys = ON;
