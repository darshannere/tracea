-- 005_webhook_failures.sql: Dead-letter table for permanent webhook failures
-- Required by ALT-07: 3 retries with exponential backoff, permanent failures land here

CREATE TABLE IF NOT EXISTS webhook_failures (
    id            TEXT PRIMARY KEY,
    issue_id      TEXT NOT NULL,
    destination_url TEXT NOT NULL,
    status_code   INTEGER,
    response_body TEXT,
    attempt_count INTEGER NOT NULL DEFAULT 0,
    created_at    TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (issue_id) REFERENCES issues(issue_id)
);

CREATE INDEX IF NOT EXISTS idx_webhook_failures_issue
    ON webhook_failures(issue_id);