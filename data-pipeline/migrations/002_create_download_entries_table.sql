-- Migration: Create download_entries table
-- Description: Tracks downloaded files from DANE SIPSA website
-- Date: 2024-12-24

CREATE TABLE IF NOT EXISTS download_entries (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    row_name VARCHAR(500) NOT NULL,
    row_date DATE NOT NULL,
    download_link TEXT NOT NULL UNIQUE,
    source_table_link TEXT NOT NULL,
    download_date TIMESTAMP DEFAULT NOW(),
    storage_path VARCHAR(500) NOT NULL,
    file_type VARCHAR(20) NOT NULL,
    processed_status BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- Create indexes for common queries
CREATE INDEX IF NOT EXISTS idx_download_entries_date ON download_entries(row_date);
CREATE INDEX IF NOT EXISTS idx_download_entries_processed ON download_entries(processed_status);
CREATE INDEX IF NOT EXISTS idx_download_entries_link ON download_entries(download_link);
CREATE INDEX IF NOT EXISTS idx_download_entries_file_type ON download_entries(file_type);

-- Add comments
COMMENT ON TABLE download_entries IS 'Tracks all downloaded files from DANE SIPSA';
COMMENT ON COLUMN download_entries.row_name IS 'Link text from source table (e.g., "Anexo - 24 dic 2025")';
COMMENT ON COLUMN download_entries.row_date IS 'Parsed date from the row/filename';
COMMENT ON COLUMN download_entries.download_link IS 'Raw download URL (unique constraint)';
COMMENT ON COLUMN download_entries.source_table_link IS 'URL of the webpage where link was found';
COMMENT ON COLUMN download_entries.download_date IS 'Timestamp when file was downloaded';
COMMENT ON COLUMN download_entries.storage_path IS 'Path to file in Supabase storage';
COMMENT ON COLUMN download_entries.file_type IS 'Type: pdf, excel, zip';
COMMENT ON COLUMN download_entries.processed_status IS 'True when all data has been extracted';
