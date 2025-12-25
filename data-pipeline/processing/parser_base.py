"""
Base parsing utilities for SIPSA data extraction.

Provides common functions for date parsing, price parsing,
and location extraction used by both PDF and Excel parsers.
"""

import re
from datetime import datetime, date
from typing import Optional, Tuple

import sys
from pathlib import Path

_parent_dir = str(Path(__file__).parent.parent)
if _parent_dir not in sys.path:
    sys.path.insert(0, _parent_dir)

from config import MONTHS_ES_REVERSE


def parse_spanish_date(date_str: str) -> Optional[str]:
    """
    Parse Spanish date string to YYYY-MM-DD format.

    Handles formats like:
    - "31 de Diciembre de 2020"
    - "Lunes 28 de abril de 2014"

    Args:
        date_str: Spanish date string

    Returns:
        ISO date string (YYYY-MM-DD) or None if parsing fails
    """
    months = {
        'enero': '01', 'febrero': '02', 'marzo': '03', 'abril': '04',
        'mayo': '05', 'junio': '06', 'julio': '07', 'agosto': '08',
        'septiembre': '09', 'octubre': '10', 'noviembre': '11', 'diciembre': '12'
    }

    # Pattern: "31 de Diciembre de 2020"
    pattern1 = r'(\d{1,2})\s+de\s+(\w+)\s+de\s+(\d{4})'
    match = re.search(pattern1, date_str, re.IGNORECASE)
    if match:
        day = match.group(1).zfill(2)
        month = months.get(match.group(2).lower(), '01')
        year = match.group(3)
        return f"{year}-{month}-{day}"

    # Pattern: "Lunes 28 de abril de 2014"
    pattern2 = r'(?:\w+\s+)?(\d{1,2})\s+de\s+(\w+)\s+de\s+(\d{4})'
    match = re.search(pattern2, date_str, re.IGNORECASE)
    if match:
        day = match.group(1).zfill(2)
        month = months.get(match.group(2).lower(), '01')
        year = match.group(3)
        return f"{year}-{month}-{day}"

    return None


def parse_price(price_str) -> Optional[float]:
    """
    Parse price string to float, handling Colombian number format.

    Colombian format uses:
    - Dots as thousand separators: "1.200" = 1200
    - Commas as decimal separators: "12,5" = 12.5

    Args:
        price_str: Price value (string or number)

    Returns:
        Float value or None if parsing fails
    """
    if price_str is None:
        return None

    # Handle numeric types directly
    if isinstance(price_str, (int, float)):
        return float(price_str) if price_str > 0 else None

    price_str = str(price_str).strip()

    # Check for invalid values
    if price_str == '' or price_str.lower() == 'n.d.' or price_str == '0':
        return None

    try:
        # Colombian format: remove dots (thousands), replace comma with dot (decimal)
        cleaned = price_str.replace('.', '').replace(',', '.')
        value = float(cleaned)
        return value if value > 0 else None
    except (ValueError, TypeError):
        return None


def extract_city_market(location_str: str) -> Tuple[str, str]:
    """
    Extract city and market from location string.

    Handles various formats:
    - "Cali, Cavasa" -> city="Cali", market="Cavasa"
    - "Bogotá, D.C., Corabastos" -> city="Bogotá, D.C.", market="Corabastos"
    - "Santa Marta (Magdalena)" -> city="Santa Marta", market=""
    - "Ipiales (Nariño), Ipiales somos todos" -> city="Ipiales", market="Ipiales somos todos"
    - "Armenia, Mercar" -> city="Armenia", market="Mercar"

    Args:
        location_str: Location string from PDF/Excel

    Returns:
        Tuple of (city, market)
    """
    location_str = location_str.strip()

    # First check if there's a market after region pattern
    # Pattern: "City (Region), Market"
    pattern_with_region_and_market = r'^(.+?)\s*\([^)]+\)\s*,\s*(.+)$'
    match = re.match(pattern_with_region_and_market, location_str)
    if match:
        return match.group(1).strip(), match.group(2).strip()

    # Check for "City (Region)" pattern without market
    pattern_with_region = r'^(.+?)\s*\([^)]+\)$'
    match = re.match(pattern_with_region, location_str)
    if match:
        return match.group(1).strip(), ""

    # Special handling for "Bogotá, D.C., Market" pattern
    if 'D.C.' in location_str:
        parts = location_str.split(',')
        if len(parts) >= 3:
            city = ','.join(parts[:-1]).strip()
            market = parts[-1].strip()
            return city, market

    # Standard "City, Market" pattern
    if ',' in location_str:
        parts = location_str.split(',', 1)
        return parts[0].strip(), parts[1].strip()

    return location_str, ""


def row_has_price_data(row: list, price_col_start: int = 3) -> bool:
    """
    Check if a row has price data (numeric values in price columns).

    Args:
        row: Table row as list
        price_col_start: Column index where prices start

    Returns:
        True if row contains price data
    """
    if not row or len(row) <= price_col_start:
        return False

    for cell in row[price_col_start:]:
        if cell is None:
            continue

        cell_str = str(cell).strip()
        if cell_str == '' or cell_str.lower() == 'n.d.':
            continue

        # Check if it looks like a price (contains digits)
        cleaned = cell_str.replace('.', '').replace(',', '')
        if cleaned.isdigit() and int(cleaned) > 0:
            return True

    return False


def is_header_row(row: list) -> bool:
    """
    Check if row is a table header row.

    Args:
        row: Table row as list

    Returns:
        True if row is a header
    """
    if not row or not row[0]:
        return False

    first_cell = str(row[0]).strip().upper()
    header_keywords = ['PRECIOS', 'PRODUCTO', 'MÍNIMO', 'MÁXIMO', 'PAGINA', 'RONDA', 'PRESENTACIÓN']

    return any(kw in first_cell for kw in header_keywords)


def clean_text(text: str) -> str:
    """
    Clean text by removing extra whitespace and newlines.

    Args:
        text: Input text

    Returns:
        Cleaned text
    """
    if not text:
        return ""

    return ' '.join(str(text).split()).strip()
