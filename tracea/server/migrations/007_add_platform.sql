-- 007_add_platform.sql: Add platform column to sessions table
--
-- Platform is derived from event metadata (e.g. integration="tracea-mcp" → Claude Code)
-- or falls back to the AI provider (openai, anthropic, etc.)

ALTER TABLE sessions ADD COLUMN platform TEXT NOT NULL DEFAULT '';
