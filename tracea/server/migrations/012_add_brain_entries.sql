-- 012_add_brain_entries.sql: Brain (company knowledge) feature

-- Track synthesis state per session (poll-based worker pattern, same as RCA)
ALTER TABLE sessions ADD COLUMN brain_status TEXT DEFAULT 'pending';

-- Brain entries: synthesized knowledge from agent sessions
CREATE TABLE IF NOT EXISTS brain_entries (
    id              TEXT PRIMARY KEY,          -- hash of category + title
    user_id         TEXT NOT NULL DEFAULT '',   -- isolation boundary (multi-tenancy)
    category        TEXT NOT NULL,             -- 'workflow' | 'error_fix' | 'codebase'
    title           TEXT NOT NULL,
    content         TEXT NOT NULL,             -- markdown body
    confidence      REAL NOT NULL DEFAULT 0.5, -- 0.0-1.0
    source_sessions TEXT NOT NULL,             -- JSON array of session_ids
    created_at      DATETIME NOT NULL DEFAULT (datetime('now')),
    updated_at      DATETIME NOT NULL DEFAULT (datetime('now')),
    hit_count       INTEGER NOT NULL DEFAULT 1 -- times this pattern was reinforced
);

-- Full-text search via native SQLite FTS5
CREATE VIRTUAL TABLE IF NOT EXISTS brain_entries_fts USING fts5(
    title, content,
    content='brain_entries',
    content_rowid='rowid'
);

-- Keep FTS5 index in sync with brain_entries
CREATE TRIGGER IF NOT EXISTS brain_entries_fts_insert AFTER INSERT ON brain_entries BEGIN
    INSERT INTO brain_entries_fts(rowid, title, content)
    VALUES (new.rowid, new.title, new.content);
END;

CREATE TRIGGER IF NOT EXISTS brain_entries_fts_update AFTER UPDATE ON brain_entries BEGIN
    INSERT INTO brain_entries_fts(brain_entries_fts, rowid, title, content)
    VALUES ('delete', old.rowid, old.title, old.content);
    INSERT INTO brain_entries_fts(rowid, title, content)
    VALUES (new.rowid, new.title, new.content);
END;

CREATE TRIGGER IF NOT EXISTS brain_entries_fts_delete AFTER DELETE ON brain_entries BEGIN
    INSERT INTO brain_entries_fts(brain_entries_fts, rowid, title, content)
    VALUES ('delete', old.rowid, old.title, old.content);
END;
