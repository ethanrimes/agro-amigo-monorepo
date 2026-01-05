"""
Excel parser for SIPSA price data files.

Handles both .xls (legacy) and .xlsx (modern) formats.
"""

import re
from datetime import datetime, date
from typing import List, Optional, Dict, Tuple
from dataclasses import dataclass

import xlrd
import openpyxl

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
    clean_text
)


@dataclass
class ExcelParseResult:
    """Result of parsing an Excel file."""
    prices: List[ProcessedPrice]
    errors: List[ProcessingError]
    date: Optional[date]
    cities: List[str]
    record_count: int


class ExcelParser:
    """Parser for SIPSA Excel files."""

    def __init__(
        self,
        download_entry_id: Optional[str] = None,
        row_date: Optional[date] = None
    ):
        """
        Initialize the Excel parser.

        Args:
            download_entry_id: ID of the download entry (for tracking)
            row_date: Date from the scraper (preferred over Excel parsing)
        """
        self.download_entry_id = download_entry_id
        self.row_date = row_date

    def parse(self, filepath: str, storage_path: str = "") -> ExcelParseResult:
        """
        Parse a SIPSA Excel file and extract price records.

        Args:
            filepath: Path to the Excel file
            storage_path: Storage path for reference

        Returns:
            ExcelParseResult with prices and errors
        """
        # Try to determine file type - but handle mismatched extensions
        is_xlsx_extension = filepath.lower().endswith('.xlsx')

        if is_xlsx_extension:
            return self._parse_xlsx(filepath, storage_path)
        else:
            # Try .xls first, if it fails try as .xlsx
            try:
                return self._parse_xls(filepath, storage_path)
            except xlrd.biffh.XLRDError as e:
                # File might be xlsx saved with .xls extension
                if 'xlsx' in str(e).lower() or 'not supported' in str(e).lower():
                    return self._parse_xlsx(filepath, storage_path)
                raise
            except Exception as e:
                # Try xlsx as fallback for any other error
                error_str = str(e).lower()
                if 'excel' in error_str or 'workbook' in error_str or 'zip' in error_str:
                    try:
                        return self._parse_xlsx(filepath, storage_path)
                    except:
                        pass
                raise

    def _parse_xls(self, filepath: str, storage_path: str) -> ExcelParseResult:
        """Parse legacy .xls format using xlrd."""
        prices = []
        errors = []
        parsed_date = self.row_date  # Use scraper date as primary
        cities_found = []

        # Open workbook outside the main try/except so format errors
        # can propagate up and trigger xlsx fallback in parse()
        workbook = xlrd.open_workbook(filepath)
        sheet = workbook.sheet_by_index(0)

        try:

            # Find the date row to determine where data starts
            date_row_idx = self._find_date_row_xls(sheet, 10)

            # Find city headers row and build city/market mappings
            city_row_idx, cities_info = self._find_city_headers_xls(sheet, date_row_idx)

            if not cities_info:
                errors.append(ProcessingError(
                    error_type='invalid_city_headers',
                    error_message="Could not find or parse city headers",
                    source_path=storage_path or filepath,
                    source_type='excel',
                    download_entry_id=self.download_entry_id
                ))
                return ExcelParseResult(
                    prices=[],
                    errors=errors,
                    date=parsed_date,
                    cities=[],
                    record_count=0
                )

            cities_found = list(set(city for city, _ in cities_info.values()))

            # Find data start row (after headers - look for "Precio" row + 1)
            data_start_row = city_row_idx + 2 if city_row_idx >= 0 else 4

            # Track current category
            current_category = ""

            # Parse data rows
            for row_idx in range(data_start_row, sheet.nrows):
                first_cell = str(sheet.cell_value(row_idx, 0)).strip()

                # Skip empty rows and footnotes
                if not first_cell or first_cell.startswith('*') or first_cell.startswith('n.d.') or 'Var%' in first_cell:
                    continue

                # Check if it's a category row
                if self._is_category_row_xls(sheet, row_idx):
                    current_category = first_cell
                    continue

                # This is a product row
                product = first_cell

                if not current_category:
                    errors.append(ProcessingError(
                        error_type='missing_category',
                        error_message=f"Product '{product}' has no category",
                        source_path=storage_path or filepath,
                        source_type='excel',
                        download_entry_id=self.download_entry_id,
                        row_data={'product': product}
                    ))
                    continue

                # Extract prices for each city
                for col_idx, (city, market) in cities_info.items():
                    try:
                        price_val = sheet.cell_value(row_idx, col_idx)

                        # Skip n.d. and empty values
                        if price_val == 'n.d.' or price_val == '':
                            continue

                        price = parse_price(price_val)

                        if price is not None and price > 0:
                            prices.append(ProcessedPrice(
                                category=current_category,
                                subcategory="",  # Excel doesn't have subcategory
                                product=product,
                                presentation="Kilogramo",
                                units="1 Kilogramo",
                                price_date=parsed_date,
                                round=1,
                                min_price=price,
                                max_price=price,
                                source_type='excel',
                                source_path=storage_path or filepath,
                                download_entry_id=self.download_entry_id,
                                city=city,
                                market=market
                            ))
                    except Exception as e:
                        errors.append(ProcessingError(
                            error_type='non_numeric_price',
                            error_message=f"Invalid price value: {e}",
                            source_path=storage_path or filepath,
                            source_type='excel',
                            download_entry_id=self.download_entry_id,
                            row_data={'product': product, 'city': city}
                        ))

        except Exception as e:
            errors.append(ProcessingError(
                error_type='excel_parse_error',
                error_message=f"Failed to parse Excel file: {str(e)}",
                source_path=storage_path or filepath,
                source_type='excel',
                download_entry_id=self.download_entry_id
            ))

        if not parsed_date and prices:
            errors.append(ProcessingError(
                error_type='missing_date',
                error_message="No date available for Excel (row_date not provided)",
                source_path=storage_path or filepath,
                source_type='excel',
                download_entry_id=self.download_entry_id
            ))

        return ExcelParseResult(
            prices=prices,
            errors=errors,
            date=parsed_date,
            cities=cities_found,
            record_count=len(prices)
        )

    def _parse_xlsx(self, filepath: str, storage_path: str) -> ExcelParseResult:
        """Parse modern .xlsx format using openpyxl."""
        prices = []
        errors = []
        parsed_date = self.row_date  # Use scraper date as primary
        cities_found = []

        try:
            workbook = openpyxl.load_workbook(filepath, read_only=True, data_only=True)
            sheet = workbook.active

            # Convert to list for easier indexing
            rows = list(sheet.iter_rows(values_only=True))

            # Find the date row to determine where data starts
            date_row_idx = self._find_date_row_xlsx(rows, 10)

            # Find city headers row
            city_row_idx, cities_info = self._find_city_headers_xlsx(rows, date_row_idx)

            if not cities_info:
                errors.append(ProcessingError(
                    error_type='invalid_city_headers',
                    error_message="Could not find or parse city headers",
                    source_path=storage_path or filepath,
                    source_type='excel',
                    download_entry_id=self.download_entry_id
                ))
                return ExcelParseResult(
                    prices=[],
                    errors=errors,
                    date=parsed_date,
                    cities=[],
                    record_count=0
                )

            cities_found = list(set(city for city, _ in cities_info.values()))

            # Find data start row
            data_start_row = city_row_idx + 2 if city_row_idx >= 0 else 4

            # Track current category
            current_category = ""

            # Parse data rows
            for row_idx in range(data_start_row, len(rows)):
                row = rows[row_idx]
                if not row or not row[0]:
                    continue

                first_cell = str(row[0]).strip()

                # Skip empty rows and footnotes
                if not first_cell or first_cell.startswith('*') or first_cell.startswith('n.d.'):
                    continue

                # Check if it's a category row
                if self._is_category_row_xlsx(row):
                    current_category = first_cell
                    continue

                # This is a product row
                product = first_cell

                if not current_category:
                    errors.append(ProcessingError(
                        error_type='missing_category',
                        error_message=f"Product '{product}' has no category",
                        source_path=storage_path or filepath,
                        source_type='excel',
                        download_entry_id=self.download_entry_id,
                        row_data={'product': product}
                    ))
                    continue

                # Extract prices for each city
                for col_idx, (city, market) in cities_info.items():
                    try:
                        if col_idx >= len(row):
                            continue

                        price_val = row[col_idx]

                        # Skip n.d. and empty values
                        if price_val is None or price_val == 'n.d.' or price_val == '':
                            continue

                        price = parse_price(price_val)

                        if price is not None and price > 0:
                            prices.append(ProcessedPrice(
                                category=current_category,
                                subcategory="",
                                product=product,
                                presentation="Kilogramo",
                                units="1 Kilogramo",
                                price_date=parsed_date,
                                round=1,
                                min_price=price,
                                max_price=price,
                                source_type='excel',
                                source_path=storage_path or filepath,
                                download_entry_id=self.download_entry_id,
                                city=city,
                                market=market
                            ))
                    except Exception as e:
                        errors.append(ProcessingError(
                            error_type='non_numeric_price',
                            error_message=f"Invalid price value: {e}",
                            source_path=storage_path or filepath,
                            source_type='excel',
                            download_entry_id=self.download_entry_id,
                            row_data={'product': product, 'city': city}
                        ))

            workbook.close()

        except Exception as e:
            errors.append(ProcessingError(
                error_type='excel_parse_error',
                error_message=f"Failed to parse Excel file: {str(e)}",
                source_path=storage_path or filepath,
                source_type='excel',
                download_entry_id=self.download_entry_id
            ))

        return ExcelParseResult(
            prices=prices,
            errors=errors,
            date=parsed_date,
            cities=cities_found,
            record_count=len(prices)
        )

    def _find_date_row_xls(self, sheet, max_rows: int) -> int:
        """
        Find the row containing the date in XLS sheet.
        Searches all columns, handles various date formats and misspellings.
        Returns the row index where date was found, or -1 if not found.
        """
        for row_idx in range(min(max_rows, sheet.nrows)):
            # Search all columns in this row (images might push date to later columns)
            for col_idx in range(sheet.ncols):
                cell_val = sheet.cell_value(row_idx, col_idx)
                if not cell_val:
                    continue

                cell_str = str(cell_val).strip()

                # Check if this cell contains a date pattern
                if self._contains_date_pattern(cell_str):
                    return row_idx

        return -1

    def _find_date_row_xlsx(self, rows: list, max_rows: int) -> int:
        """
        Find the row containing the date in XLSX.
        Searches all columns, handles various date formats.
        Returns the row index where date was found, or -1 if not found.
        """
        for row_idx, row in enumerate(rows[:max_rows]):
            if not row:
                continue

            # Search all columns in this row
            for cell_val in row:
                if not cell_val:
                    continue

                cell_str = str(cell_val).strip()

                # Check if this cell contains a date pattern
                if self._contains_date_pattern(cell_str):
                    return row_idx

        return -1

    def _contains_date_pattern(self, text: str) -> bool:
        """
        Check if text contains a Spanish date pattern.
        Handles various formats, misspellings, and edge cases.
        """
        if not text:
            return False

        text_lower = text.lower()

        # Skip formulas
        if text.startswith('=') or 'TODAY()' in text.upper():
            return False

        # Spanish date patterns - flexible for misspellings
        # Pattern 1: "Viernes 21 de septiembre de 2012" or "21 de septiembre de 2012"
        # Pattern 2: "Thursday, December 25, 2025" (English)
        # Pattern 3: "Lunes 21 de abril de 2014"

        # Flexible Spanish pattern - allows day name, handles 05 or 5
        spanish_patterns = [
            # With optional day name: "Viernes 21 de septiembre de 2012"
            r'(?:\w+\s+)?(\d{1,2})\s+de\s+(\w+)\s+de\s+(\d{4})',
            # Just date: "21 de septiembre de 2012"
            r'(\d{1,2})\s+de\s+(\w+)\s+de\s+(\d{4})',
            # Handle "XX de XXX de 2017" placeholder
            r'(\d{1,2}|XX)\s+de\s+(\w+|XXX)\s+de\s+(\d{4})',
        ]

        for pattern in spanish_patterns:
            if re.search(pattern, text, re.IGNORECASE):
                return True

        # English date pattern: "Thursday, December 25, 2025"
        english_pattern = r'(?:\w+,?\s+)?(\w+)\s+(\d{1,2}),?\s+(\d{4})'
        if re.search(english_pattern, text):
            return True

        return False

    def _find_city_headers_xls(self, sheet, date_row_idx: int) -> Tuple[int, Dict[int, Tuple[str, str]]]:
        """
        Find city headers row and extract city/market mappings.
        Start searching after the date row.
        """
        city_row_idx = -1
        cities_info = {}

        # Start searching from after the date row
        start_row = max(0, date_row_idx)

        for row_idx in range(start_row, min(start_row + 10, sheet.nrows)):
            row_vals = [sheet.cell_value(row_idx, col_idx) for col_idx in range(sheet.ncols)]
            row_text = ' '.join(str(v) for v in row_vals if v)

            # Look for row with city names or "Precio"
            if 'Precio' in row_text or 'Bogot' in row_text or 'Medell' in row_text:
                city_row_idx = row_idx

                # Parse city headers - look for the row with city names
                # Sometimes there's a row with cities, then a row with "Precio Var %"
                # Check if this row has city names or just "Precio"
                has_cities = any(
                    'Bogot' in str(v) or 'Medell' in str(v) or 'Cali' in str(v) or
                    'Barranquilla' in str(v) or 'Armenia' in str(v)
                    for v in row_vals if v
                )

                if not has_cities and row_idx > 0:
                    # Check previous row for city names
                    prev_row_vals = [sheet.cell_value(row_idx - 1, col_idx) for col_idx in range(sheet.ncols)]
                    if any('Bogot' in str(v) or 'Medell' in str(v) for v in prev_row_vals if v):
                        row_vals = prev_row_vals
                        city_row_idx = row_idx - 1

                # Extract cities from the row
                col_idx = 1  # Skip first column (product names)
                while col_idx < sheet.ncols:
                    cell_val = str(sheet.cell_value(city_row_idx, col_idx)).strip()
                    if cell_val and cell_val not in ['', 'Precio', 'Var %', 'Var%', 'None']:
                        cell_val = cell_val.replace('\n', ' ').strip()
                        # Skip percentage columns
                        if '%' not in cell_val and cell_val not in ['Var', 'Var %']:
                            city, market = extract_city_market(cell_val)
                            if city:  # Only add if we got a valid city
                                cities_info[col_idx] = (city, market)
                    col_idx += 1
                break

        return city_row_idx, cities_info

    def _find_city_headers_xlsx(self, rows: list, date_row_idx: int) -> Tuple[int, Dict[int, Tuple[str, str]]]:
        """Find city headers row in XLSX."""
        city_row_idx = -1
        cities_info = {}

        # Start searching from after the date row
        start_row = max(0, date_row_idx)

        for row_idx, row in enumerate(rows[start_row:start_row + 10], start=start_row):
            if not row:
                continue
            row_text = ' '.join(str(v) for v in row if v)

            if 'Precio' in row_text or 'Bogot' in row_text or 'Medell' in row_text:
                city_row_idx = row_idx

                # Check if this row has city names or just "Precio"
                has_cities = any(
                    'Bogot' in str(v) or 'Medell' in str(v) or 'Cali' in str(v) or
                    'Barranquilla' in str(v) or 'Armenia' in str(v)
                    for v in row if v
                )

                target_row = row
                if not has_cities and row_idx > 0:
                    # Check previous row for city names
                    prev_row = rows[row_idx - 1] if row_idx > 0 else None
                    if prev_row and any('Bogot' in str(v) or 'Medell' in str(v) for v in prev_row if v):
                        target_row = prev_row
                        city_row_idx = row_idx - 1

                for col_idx in range(1, len(target_row)):
                    cell_val = target_row[col_idx]
                    if cell_val:
                        cell_val = str(cell_val).replace('\n', ' ').strip()
                        if cell_val not in ['', 'Precio', 'Var %', 'Var%', 'None']:
                            # Skip percentage columns
                            if '%' not in cell_val and cell_val not in ['Var', 'Var %']:
                                city, market = extract_city_market(cell_val)
                                if city:  # Only add if we got a valid city
                                    cities_info[col_idx] = (city, market)
                break

        return city_row_idx, cities_info

    def _is_category_row_xls(self, sheet, row_idx: int) -> bool:
        """Check if a row is a category row in XLS."""
        # Check if all cells after the first are empty
        for col_idx in range(1, min(5, sheet.ncols)):
            if sheet.cell_value(row_idx, col_idx) != '':
                return False
        return True

    def _is_category_row_xlsx(self, row: tuple) -> bool:
        """Check if a row is a category row in XLSX."""
        if not row or len(row) < 2:
            return False

        # Check if all cells after the first are empty
        for cell in row[1:5]:
            if cell is not None and cell != '':
                return False
        return True
