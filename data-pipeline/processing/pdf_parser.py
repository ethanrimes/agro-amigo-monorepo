"""
PDF parser for SIPSA regional price bulletins.

Uses pdfplumber for extraction and a stack-based approach
for category/subcategory detection.
"""

import re
from datetime import datetime, date
from typing import List, Optional, Tuple
from dataclasses import dataclass

import pdfplumber

import sys
from pathlib import Path

_parent_dir = str(Path(__file__).parent.parent)
if _parent_dir not in sys.path:
    sys.path.insert(0, _parent_dir)

from backend.database import ProcessedPrice, ProcessingError
from processing.parser_base import (
    parse_spanish_date,
    parse_price,
    extract_city_market,
    row_has_price_data,
    is_header_row,
    clean_text
)

# Valid subcategory names from the SIPSA PDF format.
# If the parser produces a subcategory not in this set, it's likely a product name
# that was misidentified as a header (happens with simpler PDF layouts that lack subcategories).
VALID_SUBCATEGORIES = {
    # Frutas
    'Cítricos', 'CÍtricos', 'Citricos', 'CITRICOS',
    'Otras frutas', 'OTRAS FRUTAS',
    # Tubérculos, raíces y plátanos
    'Otros tubérculos', 'Otros tuberculos', 'OTROS TUBERCULOS',
    'Plátano', 'PlÁtano', 'Platano', 'PLATANO',
    'Papa', 'PAPA',
    'Yuca', 'YUCA',
    # Verduras y hortalizas
    'Leguminosas', 'LEGUMINOSAS',
    'Otras hortalizas y verduras', 'OTRAS HORTALIZAS Y VERDURAS',
    'Zanahorias', 'ZANAHORIAS',
    'Cebollas', 'CEBOLLAS',
    'Tomates', 'TOMATES',
    'Hortalizas', 'HORTALIZAS',
    # Carnes
    'Carne de res', 'CARNE DE RES',
    'Carne de cerdo', 'CARNE DE CERDO',
    'Pollo', 'POLLO',
    # Pescados
    'Frescos y congelados', 'FRESCOS Y CONGELADOS',
    # Granos y cereales
    'Granos', 'GRANOS',
    'Cereales', 'CEREALES',
    # Procesados
    'Otros procesados', 'OTROS PROCESADOS',
    'Aceites y grasas', 'ACEITES Y GRASAS',
    'Panela', 'PANELA',
    'Azúcar', 'AzÚcar', 'Azucar', 'AZUCAR',
    # Lácteos y huevos
    'Lácteos', 'LÁcteos', 'Lacteos', 'LACTEOS',
    'Huevos', 'HUEVOS',
}

# Valid category names (top-level headers in the PDF)
VALID_CATEGORIES = {
    'Frutas', 'FRUTAS',
    'Verduras y hortalizas', 'VERDURAS Y HORTALIZAS', 'Verduras y Hortalizas',
    'Tuberculos, raices y platanos', 'TUBERCULOS, RAICES Y PLATANOS',
    'Tubérculos, raíces y plátanos', 'Tubérculos y plátanos',
    'Procesados', 'PROCESADOS',
    'Carnes', 'CARNES',
    'Granos y cereales', 'GRANOS Y CEREALES',
    'Pescados', 'PESCADOS',
    'Lacteos y huevos', 'LACTEOS Y HUEVOS', 'Lácteos y huevos',
}


@dataclass
class PDFParseResult:
    """Result of parsing a PDF file."""
    prices: List[ProcessedPrice]
    errors: List[ProcessingError]
    city: str
    market: str
    date: Optional[date]
    record_count: int


class PDFParser:
    """Parser for SIPSA PDF bulletins."""

    def __init__(
        self,
        download_entry_id: Optional[str] = None,
        extracted_pdf_id: Optional[str] = None
    ):
        """
        Initialize the PDF parser.

        Args:
            download_entry_id: ID of the download entry (for tracking)
            extracted_pdf_id: ID of the extracted PDF (for tracking)
        """
        self.download_entry_id = download_entry_id
        self.extracted_pdf_id = extracted_pdf_id

    def parse(self, filepath: str, storage_path: str = "") -> PDFParseResult:
        """
        Parse a SIPSA PDF file and extract price records.

        Uses a stack-based approach for category/subcategory detection:
        - When encountering a row without price data, push onto stack
        - When encountering a product row (has price data):
          - If stack has 2+ items: pop first = subcategory, pop second = category
          - If stack has 1 item: pop = subcategory, category = previous category
          - If stack is empty: use previous category and subcategory

        Args:
            filepath: Path to the PDF file
            storage_path: Storage path for reference

        Returns:
            PDFParseResult with prices and errors
        """
        prices = []
        errors = []
        city = ""
        market = ""
        date_str = ""
        parsed_date = None

        try:
            with pdfplumber.open(filepath) as pdf:
                # Collect all rows from all pages
                all_rows = []

                for page_num, page in enumerate(pdf.pages):
                    # Extract header info from first page
                    if page_num == 0:
                        text = page.extract_text() or ""

                        # Skip bulletin PDFs — they contain narrative prose, not price tables
                        if self._is_bulletin_pdf(text):
                            return PDFParseResult(
                                prices=[], errors=[], city="", market="",
                                date=None, record_count=0
                            )

                        city, market, date_str = self._extract_header_info(text)

                        if date_str:
                            try:
                                parsed_date = datetime.strptime(date_str, '%Y-%m-%d').date()
                            except ValueError:
                                pass

                    # Extract tables
                    tables = page.extract_tables()
                    for table in tables:
                        if table and not self._is_supply_table(table):
                            all_rows.extend(table)

                # Determine number of rounds from header rows
                num_rounds = self._detect_rounds(all_rows[:10])

                # Stack-based category/subcategory tracking
                header_stack = []
                current_category = ""
                current_subcategory = ""

                # Process rows
                for row in all_rows:
                    if not row or not row[0]:
                        continue

                    first_cell = str(row[0]).strip()

                    # Skip header rows
                    if is_header_row(row) or first_cell == '':
                        continue

                    # Check if this row has price data
                    if row_has_price_data(row):
                        # This is a product row - resolve the stack first
                        if len(header_stack) >= 2:
                            candidate_sub = header_stack.pop()
                            candidate_cat = header_stack.pop()

                            if candidate_cat in VALID_CATEGORIES:
                                current_category = candidate_cat
                                if candidate_sub in VALID_SUBCATEGORIES:
                                    current_subcategory = candidate_sub
                                else:
                                    # Subcategory is invalid — it's probably a product
                                    # from a PDF that only has category-level headers.
                                    # Use category-only mode.
                                    current_subcategory = ""
                            elif candidate_sub in VALID_CATEGORIES:
                                # Items were in wrong order or extra item on stack
                                current_category = candidate_sub
                                current_subcategory = ""
                            else:
                                # Neither is a valid category — keep previous
                                pass

                            header_stack.clear()
                        elif len(header_stack) == 1:
                            item = header_stack.pop()
                            if item in VALID_CATEGORIES:
                                current_category = item
                                current_subcategory = ""
                            elif item in VALID_SUBCATEGORIES and current_category:
                                current_subcategory = item
                            elif current_category:
                                # Not a valid subcategory — probably a product name
                                # that the table parser didn't find prices for.
                                # Keep current category, don't update subcategory.
                                pass
                            else:
                                # No category yet and item isn't recognized — skip
                                pass
                        # If stack is empty, keep previous category and subcategory

                        # Check for missing category
                        if not current_category:
                            errors.append(ProcessingError(
                                error_type='missing_category',
                                error_message=f"Product '{first_cell}' has no category",
                                source_path=storage_path or filepath,
                                source_type='pdf',
                                download_entry_id=self.download_entry_id,
                                extracted_pdf_id=self.extracted_pdf_id,
                                row_data={'product': first_cell}
                            ))
                            continue

                        # Extract product data
                        try:
                            price_records = self._extract_prices_from_row(
                                row,
                                current_category,
                                current_subcategory,
                                date_str,
                                parsed_date,
                                city,
                                market,
                                storage_path or filepath,
                                num_rounds
                            )
                            prices.extend(price_records)
                        except Exception as e:
                            errors.append(ProcessingError(
                                error_type='row_parse_error',
                                error_message=str(e),
                                source_path=storage_path or filepath,
                                source_type='pdf',
                                download_entry_id=self.download_entry_id,
                                extracted_pdf_id=self.extracted_pdf_id,
                                row_data={'row': [str(c) for c in row]}
                            ))
                    else:
                        # No price data - this is a category or subcategory header
                        header_text = clean_text(first_cell)
                        if header_text:
                            header_stack.append(header_text)

                # Check for unused stack items at the end
                if header_stack:
                    errors.append(ProcessingError(
                        error_type='unused_stack_items',
                        error_message=f"Unused items in stack at end: {header_stack}",
                        source_path=storage_path or filepath,
                        source_type='pdf',
                        download_entry_id=self.download_entry_id,
                        extracted_pdf_id=self.extracted_pdf_id
                    ))

        except Exception as e:
            errors.append(ProcessingError(
                error_type='corrupted_pdf',
                error_message=f"Failed to open PDF: {str(e)}",
                source_path=storage_path or filepath,
                source_type='pdf',
                download_entry_id=self.download_entry_id,
                extracted_pdf_id=self.extracted_pdf_id
            ))

        # Check for missing required fields
        if not city and prices:
            errors.append(ProcessingError(
                error_type='missing_location',
                error_message="Could not extract city from PDF",
                source_path=storage_path or filepath,
                source_type='pdf',
                download_entry_id=self.download_entry_id,
                extracted_pdf_id=self.extracted_pdf_id
            ))

        if not date_str and prices:
            errors.append(ProcessingError(
                error_type='missing_date',
                error_message="Could not extract date from PDF",
                source_path=storage_path or filepath,
                source_type='pdf',
                download_entry_id=self.download_entry_id,
                extracted_pdf_id=self.extracted_pdf_id
            ))

        return PDFParseResult(
            prices=prices,
            errors=errors,
            city=city,
            market=market,
            date=parsed_date,
            record_count=len(prices)
        )

    def _extract_header_info(self, text: str) -> Tuple[str, str, str]:
        """
        Extract city, market, and date from PDF header text.

        Returns:
            Tuple of (city, market, date_str)
        """
        city = ""
        market = ""
        date_str = ""

        lines = text.split('\n')

        # Lines to skip when looking for city after the header
        skip_keywords = ['PRODUCTO', 'PRIMERA CALIDAD', 'BOLETIN', 'BOLETÍN',
                         'SISTEMA DE INFORMACI', 'SIPSA']

        for i, line in enumerate(lines[:15]):  # Check first 15 lines
            # Look for "PRECIOS DE VENTA MAYORISTA" header
            if 'PRECIOS DE VENTA MAYORISTA' in line.upper():
                # Location is on the next non-subtitle line
                for j in range(i + 1, min(i + 5, len(lines))):
                    candidate = lines[j].strip()
                    if not candidate:
                        continue
                    candidate_upper = candidate.upper()
                    # Skip subtitle/metadata lines
                    if any(kw in candidate_upper for kw in skip_keywords):
                        continue
                    # Skip date lines
                    if re.search(r'\d{1,2}\s+de\s+\w+\s+de\s+\d{4}', candidate, re.IGNORECASE):
                        continue
                    # Skip round/header lines
                    if 'RONDA' in candidate_upper or 'MÍNIMO' in candidate_upper or 'MÁXIMO' in candidate_upper:
                        continue
                    # This should be the city/market line
                    city, market = extract_city_market(candidate)
                    break
                continue

            # Look for date
            if 'de 20' in line.lower() or 'de diciembre' in line.lower() or 'de enero' in line.lower():
                date_match = re.search(r'\d{1,2}\s+de\s+\w+\s+de\s+\d{4}', line, re.IGNORECASE)
                if date_match:
                    date_str = parse_spanish_date(date_match.group()) or ""

        return city, market, date_str

    def _is_supply_table(self, table: List[list]) -> bool:
        """
        Detect supply/abastecimiento tables that should be skipped.

        These tables have headers like 'Mercado mayorista' with day-of-week
        columns (Lunes, Martes, etc.) or date columns, and contain tonnage
        data rather than price data.
        """
        supply_keywords = ['mercado mayorista', 'mercados mayoristas',
                           'abastecimiento', 'toneladas']
        day_keywords = ['lunes', 'martes', 'miércoles', 'miercoles',
                        'jueves', 'viernes', 'sábado', 'sabado',
                        'domingo', 'variación', 'variacion']

        for row in table[:5]:  # Check first 5 rows
            if not row:
                continue
            row_text = ' '.join(str(c).lower() for c in row if c)
            if any(kw in row_text for kw in supply_keywords):
                return True
            # Check if multiple day-of-week names appear in the row
            day_count = sum(1 for kw in day_keywords if kw in row_text)
            if day_count >= 2:
                return True
            # Check for date pattern columns (DD/MM/YYYY)
            date_cols = sum(1 for c in row if c and re.match(r'\d{2}/\d{2}/\d{4}', str(c).strip()))
            if date_cols >= 2:
                return True
            # Check for abbreviated date columns (DD-mmm.)
            abbrev_date_cols = sum(1 for c in row if c and re.match(r'\d{1,2}-\w{3}\.?$', str(c).strip()))
            if abbrev_date_cols >= 2:
                return True

        return False

    def _is_bulletin_pdf(self, text: str) -> bool:
        """
        Detect if a PDF is a news bulletin rather than a price table.

        Bulletins contain narrative prose about market trends but no
        structured price tables. They should be skipped entirely.
        """
        upper = text.upper()
        # Price table PDFs always have this header
        if 'PRECIOS DE VENTA MAYORISTA' in upper:
            return False
        # Bulletin indicators
        bulletin_keywords = ['BOLETÍN DIARIO', 'BOLETIN DIARIO',
                             'PRECIOS MAYORISTAS', 'SIPSA']
        return any(kw in upper for kw in bulletin_keywords)

    def _detect_rounds(self, rows: List[list]) -> int:
        """Detect number of trading rounds from header rows."""
        for row in rows:
            if row:
                row_text = ' '.join(str(c) for c in row if c)
                if 'Ronda 3' in row_text:
                    return 3
                elif 'Ronda 2' in row_text:
                    return 2
        return 1

    def _extract_prices_from_row(
        self,
        row: list,
        category: str,
        subcategory: str,
        date_str: str,
        parsed_date: Optional[date],
        city: str,
        market: str,
        source_path: str,
        num_rounds: int
    ) -> List[ProcessedPrice]:
        """Extract price records from a product row."""
        prices = []

        product = clean_text(row[0])
        presentation = clean_text(row[1]) if len(row) > 1 and row[1] else ""
        units = clean_text(row[2]) if len(row) > 2 and row[2] else ""

        # Round 1 prices (columns 3-4)
        if len(row) >= 5:
            min1 = parse_price(row[3]) if len(row) > 3 else None
            max1 = parse_price(row[4]) if len(row) > 4 else None

            if min1 is not None or max1 is not None:
                prices.append(ProcessedPrice(
                    category=category,
                    subcategory=subcategory,
                    product=product,
                    presentation=presentation,
                    units=units,
                    price_date=parsed_date,
                    round=1,
                    min_price=min1,
                    max_price=max1,
                    source_type='pdf',
                    source_path=source_path,
                    download_entry_id=self.download_entry_id,
                    extracted_pdf_id=self.extracted_pdf_id,
                    city=city,
                    market=market
                ))

        # Round 2 prices (columns 5-6) if available
        if len(row) >= 7 and num_rounds >= 2:
            min2 = parse_price(row[5])
            max2 = parse_price(row[6])

            # Only add Round 2 if it has valid non-zero prices
            if min2 is not None and max2 is not None and (min2 > 0 or max2 > 0):
                prices.append(ProcessedPrice(
                    category=category,
                    subcategory=subcategory,
                    product=product,
                    presentation=presentation,
                    units=units,
                    price_date=parsed_date,
                    round=2,
                    min_price=min2,
                    max_price=max2,
                    source_type='pdf',
                    source_path=source_path,
                    download_entry_id=self.download_entry_id,
                    extracted_pdf_id=self.extracted_pdf_id,
                    city=city,
                    market=market
                ))

        return prices
