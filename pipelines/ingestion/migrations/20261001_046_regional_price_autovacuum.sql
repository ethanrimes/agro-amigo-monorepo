-- Historical city quotations are append-heavy. Index-only filter reads need
-- visibility-map coverage on recently imported pages, even when very few rows
-- are dead. Keep automatic maintenance responsive to both inserts and updates.
-- This changes maintenance settings only; no quotation or original is removed.
ALTER TABLE regional_price SET (
  autovacuum_vacuum_threshold = 1000,
  autovacuum_vacuum_scale_factor = 0.005,
  autovacuum_vacuum_insert_threshold = 1000,
  autovacuum_vacuum_insert_scale_factor = 0.001,
  autovacuum_analyze_threshold = 1000,
  autovacuum_analyze_scale_factor = 0.002
);
