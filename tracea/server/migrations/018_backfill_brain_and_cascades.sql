-- 018_backfill_brain_and_cascades.sql
-- Backfill brain_status for pre-012 sessions (DEFAULT only applies on INSERT,
-- so existing rows got NULL) and add cascade-delete triggers for spans,
-- metrics, and brain_entries so retention cleanup does not orphan rows.

-- 1. Backfill brain_status NULL → 'pending' so the synthesizer picks them up.
UPDATE sessions SET brain_status = 'pending' WHERE brain_status IS NULL;

-- 2. Cascade-delete spans when a session is deleted (retention).
CREATE TRIGGER IF NOT EXISTS tgr_delete_session_spans
AFTER DELETE ON sessions
BEGIN
    DELETE FROM spans WHERE session_id = old.session_id;
END;

-- 3. Cascade-delete metrics when a session is deleted (retention).
CREATE TRIGGER IF NOT EXISTS tgr_delete_session_metrics
AFTER DELETE ON sessions
BEGIN
    DELETE FROM metrics WHERE session_id = old.session_id;
END;

-- 4. Cascade-delete brain_entries whose source_sessions array contained the
--    deleted session. brain_entries.source_sessions is a JSON array of ids;
--    remove entries that reference the deleted session. (We delete the whole
--    row because a brain entry's value depends on its full source set.)
CREATE TRIGGER IF NOT EXISTS tgr_delete_session_brain_entries
AFTER DELETE ON sessions
BEGIN
    DELETE FROM brain_entries
    WHERE EXISTS (
        SELECT 1 FROM json_each(brain_entries.source_sessions)
        WHERE value = old.session_id
    );
END;
