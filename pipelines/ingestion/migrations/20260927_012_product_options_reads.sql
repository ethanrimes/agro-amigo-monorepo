-- Filter dimensions and classification identities are needed across all dates.
-- Serve those bounded product reads without fetching every historical heap row.
CREATE INDEX IF NOT EXISTS regional_product_options_cover
  ON regional_price(product_id,observed_on)
  INCLUDE(market_name,presentation,quantity,source_unit,document_id,source_locator);
