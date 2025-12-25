-- Migration: Create download_errors table
-- Description: Tracks errors during file download for debugging and retry
-- Date: 2024-12-24

CREATE TABLE IF NOT EXISTS download_errors (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    download_url VARCHAR(1000) NOT NULL,
    source_page VARCHAR(1000),
    error_type VARCHAR(100) NOT NULL,
    error_code INTEGER,
    error_message TEXT NOT NULL,
    file_type VARCHAR(20),
    retry_count INTEGER DEFAULT 0,
    resolved BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- Create indexes for common queries
CREATE INDEX IF NOT EXISTS idx_download_errors_url ON download_errors(download_url);
CREATE INDEX IF NOT EXISTS idx_download_errors_type ON download_errors(error_type);
CREATE INDEX IF NOT EXISTS idx_download_errors_resolved ON download_errors(resolved);
CREATE INDEX IF NOT EXISTS idx_download_errors_code ON download_errors(error_code);
CREATE INDEX IF NOT EXISTS idx_download_errors_retry ON download_errors(retry_count);

-- Add comments
COMMENT ON TABLE download_errors IS 'Tracks download errors for debugging and retry';
COMMENT ON COLUMN download_errors.download_url IS 'URL that failed to download';
COMMENT ON COLUMN download_errors.source_page IS 'Page URL where the download link was found';
COMMENT ON COLUMN download_errors.error_type IS 'Error category: http_error, connection_error, upload_error, date_parse_error, etc.';
COMMENT ON COLUMN download_errors.error_code IS 'HTTP status code if applicable (e.g., 404, 500)';
COMMENT ON COLUMN download_errors.error_message IS 'Detailed error message';
COMMENT ON COLUMN download_errors.file_type IS 'File type: pdf, excel, zip';
COMMENT ON COLUMN download_errors.retry_count IS 'Number of retry attempts';
COMMENT ON COLUMN download_errors.resolved IS 'True when error has been fixed/ignored';
