-- 001_initial.sql: Create core schema tables

-- Events: the source of truth
CREATE TABLE IF NOT EXISTS events (
    event_id       TEXT PRIMARY KEY,
    session_id     TEXT NOT NULL,
    agent_id       TEXT,
    sequence       INTEGER NOT NULL DEFAULT 0,
    timestamp      TEXT NOT NULL,
    schema_version TEXT NOT NULL DEFAULT '1',
    type           TEXT NOT NULL,
    provider       TEXT,
    model          TEXT,
    role           TEXT,
    content        TEXT,
    tool_call_id   TEXT,
    tool_name      TEXT,
    status_code    INTEGER,
    error          TEXT,
    duration_ms    INTEGER,
    input_tokens   INTEGER DEFAULT 0,
    output_tokens  INTEGER DEFAULT 0,
    total_tokens   INTEGER DEFAULT 0,
    cost_usd       REAL,
    metadata       TEXT DEFAULT '{}',
    created_at     TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Indexes for events
CREATE INDEX IF NOT EXISTS idx_events_session
    ON events(session_id, sequence);
CREATE INDEX IF NOT EXISTS idx_events_created
    ON events(created_at DESC);

-- Sessions: derived, upserted on each new event
CREATE TABLE IF NOT EXISTS sessions (
    session_id      TEXT PRIMARY KEY,
    agent_id        TEXT,
    started_at      TEXT,
    last_event_at   TEXT,
    event_count     INTEGER NOT NULL DEFAULT 0,
    issue_count     INTEGER NOT NULL DEFAULT 0,
    total_cost_usd  REAL NOT NULL DEFAULT 0.0
);

-- Issues: output of detection engine (Phase 3+)
CREATE TABLE IF NOT EXISTS issues (
    issue_id     TEXT PRIMARY KEY,
    session_id   TEXT NOT NULL,
    event_id     TEXT NOT NULL,
    rule_name    TEXT,
    issue_type   TEXT NOT NULL,
    severity     TEXT NOT NULL DEFAULT 'medium',
    detected_at  TEXT NOT NULL DEFAULT (datetime('now')),
    rca_status   TEXT NOT NULL DEFAULT 'pending',
    rca_text     TEXT,
    FOREIGN KEY (session_id) REFERENCES sessions(session_id),
    FOREIGN KEY (event_id) REFERENCES events(event_id)
);

CREATE INDEX IF NOT EXISTS idx_issues_session
    ON issues(session_id, detected_at DESC);

-- Alerts: delivery log
CREATE TABLE IF NOT EXISTS alerts (
    alert_id     TEXT PRIMARY KEY,
    issue_id     TEXT NOT NULL,
    route_type   TEXT NOT NULL,
    webhook_url  TEXT NOT NULL,
    status       TEXT NOT NULL DEFAULT 'pending',
    attempts     INTEGER NOT NULL DEFAULT 0,
    sent_at      TEXT,
    error        TEXT,
    FOREIGN KEY (issue_id) REFERENCES issues(issue_id)
);

-- Schema migrations tracker
CREATE TABLE IF NOT EXISTS schema_migrations (
    version    TEXT PRIMARY KEY,
    applied_at TEXT NOT NULL DEFAULT (datetime('now'))
);
