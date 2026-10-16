-- Keep index visibility current after historical imports and source revisions.
-- Routine VACUUM preserves all logical observations and retained versions.
-- PostgreSQL per-table controls: https://www.postgresql.org/docs/16/sql-createtable.html
ALTER TABLE input_municipal_price SET (
  autovacuum_vacuum_threshold = 5000,
  autovacuum_vacuum_scale_factor = 0.05,
  autovacuum_vacuum_insert_threshold = 5000,
  autovacuum_vacuum_insert_scale_factor = 0.05
);
