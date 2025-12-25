Pipeline Runner Scripts (all stream logs to runs/<timestamp>/):

| Script               | Purpose                            |
|----------------------|------------------------------------|
| run_full_pipeline.sh | Run historical scrape + process    |
| run_current.sh       | Run current month scrape + process |
| run_process.sh       | Process pending entries only       |
| run_scrape.sh        | Scrape only (no processing)        |
| run_migrate.sh       | Run database migrations            |
| retry_errors.sh      | Retry failed processing            |

Schema Dump Scripts:

| Script          | Purpose                           |
|-----------------|-----------------------------------|
| dump_schema.sql | SQL to dump schema to CSV         |
| dump_schema.sh  | Wrapper script for easy execution |

Features:
- Each run creates a timestamped directory in runs/ (e.g., runs/full_pipeline_20251225_143022/)
- Logs are streamed to both console and log file
- Errors are extracted to separate errors.log
- Metadata JSON tracks run status, timestamps, and exit codes

Usage examples:
cd data-pipeline

# Run full historical pipeline for 2024
./scripts/run_full_pipeline.sh --year 2024

# Run current month
./scripts/run_current.sh

# Dump schema (set SUPABASE_DB_URL first)
./scripts/dump_schema.sh