-- Migration: Create processed_prices table
-- Description: Stores extracted price data from PDFs and Excel files
-- Date: 2024-12-24

CREATE TABLE IF NOT EXISTS processed_prices (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    category VARCHAR(200) NOT NULL,
    subcategory VARCHAR(200),
    product VARCHAR(300) NOT NULL,
    presentation VARCHAR(200),
    units VARCHAR(100),
    price_date DATE NOT NULL,
    round INTEGER DEFAULT 1,
    min_price DECIMAL(12, 2),
    max_price DECIMAL(12, 2),
    source_type VARCHAR(20) NOT NULL,
    source_path VARCHAR(500) NOT NULL,
    download_entry_id UUID REFERENCES download_entries(id),
    extracted_pdf_id UUID REFERENCES extracted_pdfs(id),
    city VARCHAR(100) NOT NULL,
    market VARCHAR(200),
    processed_date TIMESTAMP DEFAULT NOW(),
    created_at TIMESTAMP DEFAULT NOW()
);

-- Create indexes for common queries
CREATE INDEX IF NOT EXISTS idx_processed_prices_date ON processed_prices(price_date);
CREATE INDEX IF NOT EXISTS idx_processed_prices_product ON processed_prices(product);
CREATE INDEX IF NOT EXISTS idx_processed_prices_city ON processed_prices(city);
CREATE INDEX IF NOT EXISTS idx_processed_prices_download ON processed_prices(download_entry_id);
CREATE INDEX IF NOT EXISTS idx_processed_prices_extracted ON processed_prices(extracted_pdf_id);
CREATE INDEX IF NOT EXISTS idx_processed_prices_category ON processed_prices(category);
CREATE INDEX IF NOT EXISTS idx_processed_prices_source_type ON processed_prices(source_type);

-- Composite indexes for common query patterns
CREATE INDEX IF NOT EXISTS idx_processed_prices_city_date ON processed_prices(city, price_date);
CREATE INDEX IF NOT EXISTS idx_processed_prices_product_date ON processed_prices(product, price_date);

-- Add comments
COMMENT ON TABLE processed_prices IS 'Extracted price data from SIPSA PDFs and Excel files';
COMMENT ON COLUMN processed_prices.category IS 'Main category (Frutas, Verduras, etc.)';
COMMENT ON COLUMN processed_prices.subcategory IS 'Subcategory (Cítricos, Papa, etc.) - may be empty for Excel';
COMMENT ON COLUMN processed_prices.product IS 'Product name';
COMMENT ON COLUMN processed_prices.presentation IS 'Packaging type (Kilogramo, Bulto, etc.)';
COMMENT ON COLUMN processed_prices.units IS 'Weight/quantity specification';
COMMENT ON COLUMN processed_prices.price_date IS 'Date of the price observation';
COMMENT ON COLUMN processed_prices.round IS 'Trading round (1 or 2)';
COMMENT ON COLUMN processed_prices.min_price IS 'Minimum price in Colombian pesos';
COMMENT ON COLUMN processed_prices.max_price IS 'Maximum price in Colombian pesos';
COMMENT ON COLUMN processed_prices.source_type IS 'Source type: pdf or excel';
COMMENT ON COLUMN processed_prices.source_path IS 'Path to source file in storage';
COMMENT ON COLUMN processed_prices.city IS 'City name';
COMMENT ON COLUMN processed_prices.market IS 'Market name (may be empty)';
