"""
AgroAmigo Data Pipeline Configuration

Central configuration for all pipeline settings.
"""

import os
from pathlib import Path

# Base paths
PROJECT_ROOT = Path(__file__).parent.parent
DATA_PIPELINE_ROOT = Path(__file__).parent
EXPORTS_DIR = DATA_PIPELINE_ROOT / "exports"

# Threading configuration
# Keep concurrent downloads reasonable to avoid Errno 35 (resource temporarily unavailable)
MAX_THREADS = 4
BATCH_SIZE = 100

# Web scraping configuration
REQUEST_DELAY = 0.3  # seconds between requests
MAX_RETRIES = 3
REQUEST_TIMEOUT = 60  # seconds

# Supabase storage
STORAGE_BUCKET = "sipsa-raw-files"
EXTRACTED_BUCKET = "sipsa-extracted"

# DANE SIPSA URLs
DANE_BASE_URL = "https://www.dane.gov.co"
SIPSA_MAIN_PAGE = f"{DANE_BASE_URL}/index.php/estadisticas-por-tema/agropecuario/sistema-de-informacion-de-precios-sipsa/componente-precios-mayoristas"

# Month names in Spanish
MONTHS_ES = {
    1: 'enero', 2: 'febrero', 3: 'marzo', 4: 'abril',
    5: 'mayo', 6: 'junio', 7: 'julio', 8: 'agosto',
    9: 'septiembre', 10: 'octubre', 11: 'noviembre', 12: 'diciembre'
}

MONTHS_ES_REVERSE = {v: k for k, v in MONTHS_ES.items()}

# Month abbreviations (for file parsing)
# Includes both 3 and 4 letter variants (sept is used in older files)
MONTH_ABBR_MAP = {
    'ene': 1, 'feb': 2, 'mar': 3, 'abr': 4, 'may': 5, 'jun': 6,
    'jul': 7, 'ago': 8, 'sep': 9, 'sept': 9, 'oct': 10, 'nov': 11, 'dic': 12
}

# File type mappings
FILE_TYPES = {
    'pdf': 'pdf',
    'excel': 'excel',
    'zip': 'zip'
}

# Reference data paths
DIVIPOLA_PATH = PROJECT_ROOT / "data" / "divipola_municipios.tsv"

# Ensure exports directory exists
EXPORTS_DIR.mkdir(parents=True, exist_ok=True)
