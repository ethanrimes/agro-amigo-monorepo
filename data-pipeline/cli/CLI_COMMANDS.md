Implementation Summary

Directory Structure

data-pipeline/
├── backend/           # Supabase client, storage, database operations
├── migrations/        # 6 SQL migrations with RLS policies
├── scraping/          # Current month + historical scrapers
├── processing/        # PDF, Excel, ZIP parsers + orchestrator
├── cleaning/          # Standardizer, tuple exporter, geographic mapper
├── cli/               # Main CLI with all commands
├── exports/           # Output directory for tuple exports
├── config.py          # Central configuration
└── requirements.txt   # Python dependencies

CLI Commands

| Command                    | Description                                   |
|----------------------------|-----------------------------------------------|
| run-current                | Full pipeline: scrape current month + process |
| run-historical --year 2024 | Full pipeline: scrape historical + process    |
| scrape-current             | Only download current month files             |
| scrape-historical          | Only download historical files                |
| process                    | Process all unprocessed entries               |
| retry-errors               | Retry failed file processing                  |
| migrate                    | Run database migrations                       |
| upload-divipola            | Upload municipality reference data            |
| export-tuples              | Export data for manual cleaning review        |
| generate-dimensions        | Create dimension tables from reviewed data    |

Database Tables

- divipola_municipios - Colombian municipalities reference
- download_entries - Tracks downloaded files
- extracted_pdfs - PDFs extracted from ZIPs
- processed_prices - Raw extracted price data
- processing_errors - Error logging for retry
- Dimension tables (after manual review): dim_categories, dim_subcategories, dim_products, dim_presentations, dim_departments, dim_municipalities, dim_markets
- cleaned_prices - Final cleaned fact table

To Use

# Activate virtual environment
source .venv/bin/activate
cd data-pipeline

# Run migrations (once database is accessible)
python -m cli.main migrate

# Upload DIVIPOLA reference data
python -m cli.main upload-divipola

# Run the pipeline
python -m cli.main run-current --dry-run  # Test first
python -m cli.main run-current            # Full run

The database connection error indicates the Supabase project may need to be created or network access enabled. Once that's resolved, the migrations and pipeline will work.