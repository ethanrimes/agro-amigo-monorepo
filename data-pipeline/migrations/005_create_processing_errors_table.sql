-- Migration: Create processing_errors table
-- Description: Tracks errors during data processing for retry handling
-- Date: 2024-12-24

CREATE TABLE IF NOT EXISTS processing_errors (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    error_type VARCHAR(100) NOT NULL,
    error_message TEXT NOT NULL,
    source_path VARCHAR(500) NOT NULL,
    source_type VARCHAR(20) NOT NULL,
    download_entry_id UUID REFERENCES download_entries(id),
    extracted_pdf_id UUID REFERENCES extracted_pdfs(id),
    row_data JSONB,
    retry_count INTEGER DEFAULT 0,
    resolved BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- Create indexes for common queries
CREATE INDEX IF NOT EXISTS idx_processing_errors_type ON processing_errors(error_type);
CREATE INDEX IF NOT EXISTS idx_processing_errors_resolved ON processing_errors(resolved);
CREATE INDEX IF NOT EXISTS idx_processing_errors_download ON processing_errors(download_entry_id);
CREATE INDEX IF NOT EXISTS idx_processing_errors_extracted ON processing_errors(extracted_pdf_id);
CREATE INDEX IF NOT EXISTS idx_processing_errors_retry ON processing_errors(retry_count);

-- Add comments
COMMENT ON TABLE processing_errors IS 'Tracks processing errors for debugging and retry';
COMMENT ON COLUMN processing_errors.error_type IS 'Error category: corrupted_pdf, missing_date, missing_location, etc.';
COMMENT ON COLUMN processing_errors.error_message IS 'Detailed error message';
COMMENT ON COLUMN processing_errors.source_path IS 'Path to file that caused error';
COMMENT ON COLUMN processing_errors.source_type IS 'Source type: pdf or excel';
COMMENT ON COLUMN processing_errors.row_data IS 'Raw row data if available (JSONB for flexibility)';
COMMENT ON COLUMN processing_errors.retry_count IS 'Number of retry attempts';
COMMENT ON COLUMN processing_errors.resolved IS 'True when error has been fixed/ignored';
