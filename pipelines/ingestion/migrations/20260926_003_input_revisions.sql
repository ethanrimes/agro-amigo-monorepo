-- Keep replay ordering separate from equal-price source attribution.
-- This small mutable index has no price values and never replaces originals.
CREATE TABLE IF NOT EXISTS input_revision (
 id text NOT NULL,
 department text NOT NULL,
 municipality text NOT NULL,
 observed_on date NOT NULL,
 retrieved_at timestamptz NOT NULL,
 PRIMARY KEY(id,department,municipality,observed_on)
);
DROP TRIGGER IF EXISTS retain_history ON input_revision;
CREATE TRIGGER retain_history BEFORE DELETE OR TRUNCATE ON input_revision
FOR EACH STATEMENT EXECUTE FUNCTION prevent_history_removal();
GRANT SELECT,INSERT,UPDATE ON input_revision TO agro_ingestor;
GRANT SELECT ON input_revision TO agro_reader;
REVOKE DELETE,TRUNCATE ON input_revision FROM agro_ingestor,agro_reader;
