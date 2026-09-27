-- Product filters must retain every separately stored historical classification.
-- Include its small path array to avoid a random heap read for every city quote.
CREATE INDEX IF NOT EXISTS regional_classification_lookup_cover
  ON regional_classification(document_id,source_locator) INCLUDE(category_path);
