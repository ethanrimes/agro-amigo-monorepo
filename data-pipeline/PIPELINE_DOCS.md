# AgroAmigo Data Pipeline Documentation

## Overview

The data pipeline scrapes, processes, and stores Colombian agricultural price and supply data from DANE's SIPSA system. It handles 6 data sources producing ~25M+ records in Supabase (PostgreSQL).

All commands run from the `data-pipeline/` directory:
```bash
cd data-pipeline
source .venv/Scripts/activate  # Windows
python -m cli.main <command> [options]
```

---

## 1. CLI Commands

### Daily Wholesale Prices (PDFs from SIPSA website)

| Command | Description |
|---------|-------------|
| `scrape-current` | Download current month's Anexo + Informes ZIP files |
| `scrape-historical --year 2024` | Download historical data for a year |
| `scrape-historical --year 2024 --month 6` | Download a specific month |
| `process` | Process all unprocessed download entries |
| `process --entry-id <uuid>` | Process a specific entry |
| `run-current` | Scrape current month + process (combined) |
| `run-historical --year 2024` | Scrape + process a year |

**Common flags**: `--dry-run`, `--sequential`, `--threads N`, `--anexo-only`, `--informes-only`

### Milk Prices

| Command | Description |
|---------|-------------|
| `scrape-milk` | Download all milk price files (historical + current) |
| `scrape-milk --historical` | Historical only (2013-2025) |
| `scrape-milk --current` | Current month only |
| `process-milk` | Process unprocessed milk files |

### Rice Mill Prices

| Command | Description |
|---------|-------------|
| `scrape-rice` | Download all rice mill price files (2013-2026) |
| `scrape-rice --historical` | Historical only |
| `scrape-rice --current` | Current year only |
| `process-rice` | Process unprocessed rice files |

### Abastecimiento (Supply Quantities)

| Command | Description |
|---------|-------------|
| `scrape-abastecimiento` | Download all supply microdato files (2013-2026, ~1GB total) |
| `scrape-abastecimiento --historical` | Historical only |
| `scrape-abastecimiento --current` | Current year only |
| `process-abastecimiento` | Process unprocessed supply files |

Note: Supply files are 50-100MB each and stored locally (not in Supabase storage).

### Insumos (Agricultural Input Prices)

| Command | Description |
|---------|-------------|
| `scrape-insumos` | Download all insumo price files (3 files, ~150MB total) |
| `scrape-insumos --historical` | Historical municipality data only |
| `scrape-insumos --current` | Current municipality + department data |
| `process-insumos` | Process unprocessed insumo files |

### Dimension Tables & Utilities

| Command | Description |
|---------|-------------|
| `populate-dimensions` | Populate dimension tables from processed_prices |
| `populate-dimensions --skip-observations` | Dimensions only, skip price_observations |
| `migrate` | Run pending database migrations |
| `migrate --list` | Show migration status |
| `upload-divipola` | Upload DIVIPOLA municipality reference data |
| `retry-errors` | Retry failed processing |
| `download-errors --output ./errors` | Download files that had errors |

---

## 2. Data Flow

```
DANE SIPSA Website
    │
    ├── Daily PDFs (via ZIP) ──► scrape-current/historical
    │                               │
    │                               ▼
    │                         download_entries (Supabase)
    │                               │
    │                               ▼
    │                         extracted_pdfs (from ZIPs)
    │                               │
    │                               ▼
    │                         PDF Parser (pdfplumber + OCR fallback)
    │                               │
    │                               ▼
    │                         processed_prices ──► price_observations (UUID refs)
    │
    ├── Monthly Milk Excel ──► scrape-milk ──► process-milk ──► processed_prices
    ├── Monthly Rice Excel ──► scrape-rice ──► process-rice ──► processed_prices
    ├── Supply Microdatos ──► scrape-abastecimiento ──► process-abastecimiento ──► supply_observations
    └── Insumo Excel ──► scrape-insumos ──► process-insumos ──► insumo_prices_municipality / insumo_prices_department
```

### Idempotency
Every scraper checks `download_entries.download_link` before downloading — files already in the DB are skipped. Every processor checks `processed_status` flags — already-processed entries are skipped. Safe to re-run any command.

---

## 3. Backend Tables (Supabase/PostgreSQL)

### Observation Tables (raw data)

| Table | Records | Description |
|-------|--------:|-------------|
| `processed_prices` | ~3M | Wholesale prices from PDFs + Excel (min/max/avg price per product per market per day) |
| `price_observations` | ~3M | Same data normalized with UUID foreign keys to dimension tables |
| `supply_observations` | ~19.5M | Abastecimiento: kg of food arriving at wholesale markets, with provenance |
| `insumo_prices_municipality` | ~2.2M | Agricultural input prices at municipality level |
| `insumo_prices_department` | ~743K | Agricultural input prices at department level with brand detail |

### Dimension Tables (canonical entities)

| Table | Count | Description |
|-------|------:|-------------|
| `dim_category` | 8 | Top-level product categories (Frutas, Verduras, Tubérculos, Carnes, Pescados, Granos, Procesados, Lácteos) |
| `dim_subcategory` | 33 | Subcategories (Cítricos, Papa, Plátano, Cebollas, etc.) + General fallbacks + Arroz en molino + Leche cruda |
| `dim_product` | ~700 | Individual products (Aguacate Hass, Papa criolla limpia, etc.) with `sipsa_id` and `cpc_code` |
| `dim_presentation` | 72 | Packaging types (Kilogramo, Bulto, Canastilla, Caja de cartón, etc.) |
| `dim_units` | ~630 | Unit specifications (1 Kilogramo, 50 Kilogramo, etc.) |
| `dim_department` | 26 | Colombian departments with DIVIPOLA codes |
| `dim_city` | ~530 | Cities/municipalities with DIVIPOLA codes and department FK |
| `dim_market` | 43 | Wholesale markets with SIPSA IDs and city FK |
| `dim_insumo` | ~2,250 | Agricultural input products with grupo/subgrupo/CPC code |
| `dim_insumo_grupo` | 3 | Insumo top-level groups (Insumos agrícolas, Insumos pecuarios, Factores de producción) |
| `dim_insumo_subgrupo` | 19 | Insumo subgroups (Fertilizantes, Herbicidas, Medicamentos, etc.) |
| `dim_casa_comercial` | 435 | Commercial brands for agricultural inputs |

### Alias Tables (string-to-UUID mappings)

Each dimension table has a corresponding `alias_*` table that maps every raw string variant seen in the source data to its canonical `dim_*` UUID. This handles spelling differences, casing, accent variations, and encoding issues.

| Table | Description |
|-------|-------------|
| `alias_product` | Raw product names → `dim_product.id` |
| `alias_city` | Raw city names → `dim_city.id` |
| `alias_market` | Raw market names → `dim_market.id` |
| `alias_category` | Raw category names → `dim_category.id` |
| `alias_subcategory` | Raw subcategory names → `dim_subcategory.id` |
| `alias_presentation` | Raw presentation names → `dim_presentation.id` |
| `alias_units` | Raw unit strings → `dim_units.id` |
| `alias_insumo` | Raw insumo names → `dim_insumo.id` |
| `alias_insumo_grupo` | Raw grupo names → `dim_insumo_grupo.id` |
| `alias_insumo_subgrupo` | Raw subgrupo names → `dim_insumo_subgrupo.id` |
| `alias_casa_comercial` | Raw brand names → `dim_casa_comercial.id` |

### Tracking Tables

| Table | Description |
|-------|-------------|
| `download_entries` | Tracks every downloaded file (URL, storage path, processed status) |
| `extracted_pdfs` | Tracks individual PDFs extracted from ZIP files |
| `download_errors` | Logs download failures |
| `processing_errors` | Logs processing failures |
| `schema_migrations` | Tracks applied database migrations |
| `divipola_municipios` | DIVIPOLA reference data (1,122 municipalities) |

### Hierarchy Relationships

**Product taxonomy**: `dim_product` → `dim_subcategory` → `dim_category`
- Each product belongs to exactly one subcategory
- Each subcategory belongs to exactly one category

**Geography**: `dim_market` → `dim_city` → `dim_department`
- Each market belongs to exactly one city
- Each city belongs to exactly one department

**Insumos**: `dim_insumo` → `dim_insumo_subgrupo` → `dim_insumo_grupo`

---

## 4. Configuration

### Environment Variables (`.env`)
```
SUPABASE_URL=https://xxx.supabase.co
SUPABASE_SECRET_KEY=sb_secret_xxx
SUPABASE_DB_URL=postgresql://postgres.xxx:password@aws-1-us-east-1.pooler.supabase.com:6543/postgres
GEMINI_API_KEY=AIzaSyxxx  (for OCR fallback on scanned PDFs)
```

Note: Port 6543 = session pooler (read-write). Port 5432 = transaction pooler (read-only by default).

### Key Files
```
data-pipeline/
├── cli/main.py              # All CLI commands
├── config.py                # Central configuration
├── backend/
│   ├── supabase_client.py   # DB connection management
│   ├── database.py          # CRUD operations (Supabase REST API)
│   ├── storage.py           # Supabase storage operations
│   └── dimension_resolver.py # Runtime string→UUID resolution
├── scraping/
│   ├── scraper_base.py      # Base scraper with link extraction
│   ├── current_month.py     # Daily price scraper
│   ├── historical.py        # Historical price scraper
│   ├── milk_scraper.py      # Milk price scraper
│   ├── rice_scraper.py      # Rice mill price scraper
│   ├── abastecimiento_scraper.py  # Supply data scraper
│   └── insumos_scraper.py   # Agricultural input scraper
├── processing/
│   ├── pdf_parser.py        # PDF price extraction (with subcategory validation)
│   ├── excel_parser.py      # Excel price extraction
│   ├── ocr_fallback.py      # Gemini OCR for scanned PDFs
│   ├── zip_handler.py       # ZIP extraction and storage
│   ├── milk_parser.py       # Milk Excel parser
│   ├── rice_parser.py       # Rice Excel parser
│   ├── abastecimiento_parser.py  # Supply Excel parser
│   └── insumos_parser.py    # Insumo Excel parser
├── cleaning/
│   └── populate_dimensions.py  # Initial dimension table population
├── migrations/               # SQL migration files (001-015)
└── scripts/
    └── pipeline.sh           # Shell wrapper with logging
```

---

## 5. Typical Workflows

### Daily Update
```bash
python -m cli.main run-current     # Scrape + process today's data
```

### Monthly Update (milk, rice, insumos)
```bash
python -m cli.main scrape-milk --current && python -m cli.main process-milk
python -m cli.main scrape-rice --current && python -m cli.main process-rice
# Insumos: re-download the current files (they're cumulative)
python -m cli.main scrape-insumos --current && python -m cli.main process-insumos
```

### Full Historical Backfill
```bash
python -m cli.main scrape-all       # All daily price data since 2012
python -m cli.main process          # Process everything
python -m cli.main scrape-milk && python -m cli.main process-milk
python -m cli.main scrape-rice && python -m cli.main process-rice
python -m cli.main scrape-abastecimiento && python -m cli.main process-abastecimiento
python -m cli.main scrape-insumos && python -m cli.main process-insumos
python -m cli.main populate-dimensions  # Build normalized dimension tables
```

### After Schema Changes
```bash
python -m cli.main migrate          # Apply new migrations
```
