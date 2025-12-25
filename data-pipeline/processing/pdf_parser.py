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
                        city, market, date_str = self._extract_header_info(text)

                        if date_str:
                            try:
                                parsed_date = datetime.strptime(date_str, '%Y-%m-%d').date()
                            except ValueError:
                                pass

                    # Extract tables
                    tables = page.extract_tables()
                    for table in tables:
                        if table:
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
                            current_subcategory = header_stack.pop()
                            current_category = header_stack.pop()
                            # Clear any remaining items
                            if header_stack:
                                # Log warning about unused stack items
                                errors.append(ProcessingError(
                                    error_type='unused_stack_items',
                                    error_message=f"Unused items in stack: {header_stack}",
                                    source_path=storage_path or filepath,
                                    source_type='pdf',
                                    download_entry_id=self.download_entry_id,
                                    extracted_pdf_id=self.extracted_pdf_id
                                ))
                            header_stack.clear()
                        elif len(header_stack) == 1:
                            current_subcategory = header_stack.pop()
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

        for i, line in enumerate(lines[:15]):  # Check first 15 lines
            # Look for "PRECIOS DE VENTA MAYORISTA" header
            if 'PRECIOS DE VENTA MAYORISTA' in line.upper():
                # Location is usually on the next line
                if i + 1 < len(lines):
                    location = lines[i + 1].strip()
                    city, market = extract_city_market(location)
                continue

            # Look for date
            if 'de 20' in line.lower() or 'de diciembre' in line.lower() or 'de enero' in line.lower():
                date_match = re.search(r'\d{1,2}\s+de\s+\w+\s+de\s+\d{4}', line, re.IGNORECASE)
                if date_match:
                    date_str = parse_spanish_date(date_match.group()) or ""

        return city, market, date_str

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
