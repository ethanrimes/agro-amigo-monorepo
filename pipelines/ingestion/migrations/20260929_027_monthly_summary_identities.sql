-- Preserve every monthly-summary identity independently of the much larger
-- append-only historical_price table. Future originals and revisions add their
-- identities at insertion time; neither history nor the identity set is pruned.
CREATE TABLE IF NOT EXISTS monthly_summary_identity (
 product_name text NOT NULL,
 market_name text NOT NULL,
 unit text NOT NULL,
 PRIMARY KEY(product_name,market_name,unit)
);
INSERT INTO monthly_summary_identity(product_name,market_name,unit)
SELECT DISTINCT product_name,market_name,unit
FROM historical_price WHERE series='dane-monthly-summary'
ON CONFLICT DO NOTHING;

CREATE OR REPLACE FUNCTION retain_monthly_summary_identity() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
 INSERT INTO monthly_summary_identity(product_name,market_name,unit)
 VALUES(NEW.product_name,NEW.market_name,NEW.unit)
 ON CONFLICT DO NOTHING;
 RETURN NEW;
END $$;
DROP TRIGGER IF EXISTS retain_monthly_summary_identity ON historical_price;
CREATE TRIGGER retain_monthly_summary_identity
AFTER INSERT ON historical_price
FOR EACH ROW WHEN (NEW.series='dane-monthly-summary')
EXECUTE FUNCTION retain_monthly_summary_identity();
GRANT SELECT ON monthly_summary_identity TO agro_reader,agro_ingestor;
GRANT INSERT ON monthly_summary_identity TO agro_ingestor;
