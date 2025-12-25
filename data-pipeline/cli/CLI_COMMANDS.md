# Data Pipeline CLI Commands

```bash
cd data-pipeline
source .venv/bin/activate
python -m cli.main <command> [options]
```

## Pipeline Commands

### run-current
Scrape current month + process files.
```bash
python -m cli.main run-current
python -m cli.main run-current --anexo-only
python -m cli.main run-current --informes-only
python -m cli.main run-current --include-boletin
python -m cli.main run-current --dry-run
python -m cli.main run-current --sequential --threads 4
```

### run-historical
Scrape historical data + process files.
```bash
python -m cli.main run-historical --year 2024
python -m cli.main run-historical --year 2024 --month 6
python -m cli.main run-historical --start-date 2024-01-01 --end-date 2024-06-30
python -m cli.main run-historical --year 2023 --anexo-only
python -m cli.main run-historical --year 2024 --dry-run
```

### scrape-current / scrape-historical
Download files only (no processing).
```bash
python -m cli.main scrape-current
python -m cli.main scrape-historical --year 2024
```

### process
Process unprocessed download entries.
```bash
python -m cli.main process
python -m cli.main process --entry-id <uuid>
python -m cli.main process --date 2024-12-01
python -m cli.main process --sequential
```

### retry-errors
Retry failed processing.
```bash
python -m cli.main retry-errors
python -m cli.main retry-errors --error-type corrupted_pdf
```

### download-errors
Download files that had processing errors from storage.
```bash
# Required: --output directory
python -m cli.main download-errors --output ./error_files

# Filter by error type
python -m cli.main download-errors -o ./errors -t no_prices_extracted

# Filter by time range
python -m cli.main download-errors -o ./errors --start-time "2025-01-01" --end-time "2025-01-15"

# Filter by error message
python -m cli.main download-errors -o ./errors --error-message "corrupted"

# Filter by resolved status
python -m cli.main download-errors -o ./errors --resolved false

# Dry run
python -m cli.main download-errors -o ./errors --dry-run

# List error types
python -m cli.main download-errors --list-error-types
```

## Setup Commands

### migrate
Run database migrations.
```bash
python -m cli.main migrate
python -m cli.main migrate --list
```

### upload-divipola
Upload DIVIPOLA municipality reference data.
```bash
python -m cli.main upload-divipola
python -m cli.main upload-divipola --replace
```

## Cleaning Commands

### export-tuples
Export unique tuples for manual review.
```bash
python -m cli.main export-tuples
python -m cli.main export-tuples --output ./my_exports
```

### generate-dimensions
Generate dimension tables from reviewed TSVs.
```bash
python -m cli.main generate-dimensions
python -m cli.main generate-dimensions --input ./my_exports
```

## Common Flags

| Flag | Commands | Description |
|------|----------|-------------|
| `--dry-run` | run-*, scrape-* | Preview without changes |
| `--sequential` | run-*, process | Disable parallel processing |
| `--threads N` | run-*, process, retry | Thread count (default: 8) |
| `--anexo-only` | run-*, scrape-* | Only Anexo (Excel) files |
| `--informes-only` | run-*, scrape-* | Only Informes (ZIP) files |
| `--include-boletin` | run-*, scrape-* | Include Boletín PDFs |

## Error Types

| Type | Description |
|------|-------------|
| `no_prices_extracted` | File processed but 0 prices found |
| `corrupted_pdf` | Failed to parse PDF |
| `missing_date` | Could not extract date |
| `missing_location` | Could not extract city/market |
| `excel_parse_error` | Excel parsing failed |
| `download_failed` | Storage download failed |
| `processing_failed` | General processing failure |

## Database Tables

| Table | Purpose |
|-------|---------|
| `download_entries` | Tracks downloaded files |
| `extracted_pdfs` | PDFs extracted from ZIPs |
| `processed_prices` | Raw extracted price data |
| `processing_errors` | Error logging for retry |
| `download_errors` | Download failure logging |
| `divipola_municipios` | Municipality reference |
