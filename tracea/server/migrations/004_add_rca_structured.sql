-- 004_add_rca_structured.sql: Add structured RCA JSON column for verbose output

ALTER TABLE issues ADD COLUMN rca_structured TEXT;
