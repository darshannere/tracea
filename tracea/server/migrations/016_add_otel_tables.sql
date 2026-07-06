-- 016_add_otel_tables.sql: Tables for OTLP-ingested traces and metrics.
--
-- Events flow into the existing `events` table (already has role/content
-- columns from 001). These two tables hold signals that don't fit the
-- per-call event model: span trees (parent/child nesting) and aggregate
-- metrics (cost/token/duration rollups).

CREATE TABLE IF NOT EXISTS spans (
    trace_id       TEXT NOT NULL,
    span_id        TEXT NOT NULL,
    parent_span_id TEXT,
    session_id     TEXT,
    name           TEXT,
    kind           TEXT,
    start_time     TEXT NOT NULL,
    end_time       TEXT,
    attributes     TEXT DEFAULT '{}',
    PRIMARY KEY (trace_id, span_id)
);

CREATE INDEX IF NOT EXISTS idx_spans_session ON spans(session_id);
CREATE INDEX IF NOT EXISTS idx_spans_trace   ON spans(trace_id);

CREATE TABLE IF NOT EXISTS metrics (
    metric_id  TEXT PRIMARY KEY,
    session_id TEXT,
    name       TEXT NOT NULL,
    value      REAL,
    attributes TEXT DEFAULT '{}',
    timestamp  TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_metrics_session ON metrics(session_id, name);
