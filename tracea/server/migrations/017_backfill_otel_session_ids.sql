-- Claude Code sends session.id in span-level / metric data-point attributes,
-- not resource attributes. Earlier ingest missed it, leaving spans keyed to
-- phantom "trace-<id>" sessions and metrics with an empty session_id.
-- Backfill from the stored attributes JSON and remove the phantom sessions.

UPDATE spans
SET session_id = json_extract(attributes, '$.span."session.id"')
WHERE json_extract(attributes, '$.span."session.id"') IS NOT NULL;

UPDATE metrics
SET session_id = json_extract(attributes, '$.attributes."session.id"')
WHERE (session_id IS NULL OR session_id = '')
  AND json_extract(attributes, '$.attributes."session.id"') IS NOT NULL;

-- Span-derived tool events in phantom sessions are contentless duplicates of
-- hook events; drop them along with their now-empty phantom sessions.
DELETE FROM events
WHERE session_id LIKE 'trace-%'
  AND json_extract(metadata, '$.source') = 'span';

DELETE FROM sessions
WHERE session_id LIKE 'trace-%'
  AND NOT EXISTS (SELECT 1 FROM events e WHERE e.session_id = sessions.session_id);
