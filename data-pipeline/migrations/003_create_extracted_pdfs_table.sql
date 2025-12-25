-- Migration: Create extracted_pdfs table
-- Description: Tracks PDFs extracted from ZIP files
-- Date: 2024-12-24

CREATE TABLE IF NOT EXISTS extracted_pdfs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    download_entry_id UUID REFERENCES download_entries(id) ON DELETE CASCADE,
    original_zip_path VARCHAR(500),
    pdf_filename VARCHAR(500) NOT NULL,
    storage_path VARCHAR(500) NOT NULL,
    city VARCHAR(100),
    market VARCHAR(200),
    pdf_date DATE,
    processed_status BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- Create indexes for common queries
CREATE INDEX IF NOT EXISTS idx_extracted_pdfs_download ON extracted_pdfs(download_entry_id);
CREATE INDEX IF NOT EXISTS idx_extracted_pdfs_processed ON extracted_pdfs(processed_status);
CREATE INDEX IF NOT EXISTS idx_extracted_pdfs_city ON extracted_pdfs(city);
CREATE INDEX IF NOT EXISTS idx_extracted_pdfs_date ON extracted_pdfs(pdf_date);

-- Add comments
COMMENT ON TABLE extracted_pdfs IS 'Tracks PDFs extracted from downloaded ZIP files';
COMMENT ON COLUMN extracted_pdfs.download_entry_id IS 'Reference to parent download entry';
COMMENT ON COLUMN extracted_pdfs.original_zip_path IS 'Storage path of source ZIP file';
COMMENT ON COLUMN extracted_pdfs.pdf_filename IS 'Original PDF filename';
COMMENT ON COLUMN extracted_pdfs.storage_path IS 'Path to extracted PDF in storage';
COMMENT ON COLUMN extracted_pdfs.city IS 'City parsed from filename';
COMMENT ON COLUMN extracted_pdfs.market IS 'Market parsed from filename';
COMMENT ON COLUMN extracted_pdfs.pdf_date IS 'Date parsed from filename';
COMMENT ON COLUMN extracted_pdfs.processed_status IS 'True when price data has been extracted';
