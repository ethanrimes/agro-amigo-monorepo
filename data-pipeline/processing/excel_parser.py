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

    def __init__(self, download_entry_id: Optional[str] = None):
        """
        Initialize the Excel parser.

        Args:
            download_entry_id: ID of the download entry (for tracking)
        """
        self.download_entry_id = download_entry_id

    def parse(self, filepath: str, storage_path: str = "") -> ExcelParseResult:
        """
        Parse a SIPSA Excel file and extract price records.

        Args:
            filepath: Path to the Excel file
            storage_path: Storage path for reference

        Returns:
            ExcelParseResult with prices and errors
        """
        # Determine file type and use appropriate parser
        if filepath.lower().endswith('.xlsx'):
            return self._parse_xlsx(filepath, storage_path)
        else:
            return self._parse_xls(filepath, storage_path)

    def _parse_xls(self, filepath: str, storage_path: str) -> ExcelParseResult:
        """Parse legacy .xls format using xlrd."""
        prices = []
        errors = []
        date_str = ""
        parsed_date = None
        cities_found = []

        try:
            workbook = xlrd.open_workbook(filepath)
            sheet = workbook.sheet_by_index(0)

            # Extract date from header rows
            date_str = self._find_date_in_rows_xls(sheet, 5)
            if date_str:
                try:
                    parsed_date = datetime.strptime(date_str, '%Y-%m-%d').date()
                except ValueError:
                    pass

            # Find city headers row and build city/market mappings
            city_row_idx, cities_info = self._find_city_headers_xls(sheet)

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

            # Find data start row (after headers)
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

        if not date_str and prices:
            errors.append(ProcessingError(
                error_type='missing_date',
                error_message="Could not extract date from Excel",
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
        date_str = ""
        parsed_date = None
        cities_found = []

        try:
            workbook = openpyxl.load_workbook(filepath, read_only=True, data_only=True)
            sheet = workbook.active

            # Convert to list for easier indexing
            rows = list(sheet.iter_rows(values_only=True))

            # Extract date from header rows
            date_str = self._find_date_in_rows_xlsx(rows, 5)
            if date_str:
                try:
                    parsed_date = datetime.strptime(date_str, '%Y-%m-%d').date()
                except ValueError:
                    pass

            # Find city headers row
            city_row_idx, cities_info = self._find_city_headers_xlsx(rows)

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

    def _find_date_in_rows_xls(self, sheet, max_rows: int) -> str:
        """Find date in first few rows of XLS sheet."""
        for row_idx in range(min(max_rows, sheet.nrows)):
            row_text = ' '.join(
                str(sheet.cell_value(row_idx, col_idx))
                for col_idx in range(min(5, sheet.ncols))
            )
            date_match = re.search(
                r'(?:\w+\s+)?(\d{1,2})\s+de\s+(\w+)\s+de\s+(\d{4})',
                row_text,
                re.IGNORECASE
            )
            if date_match:
                return parse_spanish_date(date_match.group()) or ""
        return ""

    def _find_date_in_rows_xlsx(self, rows: list, max_rows: int) -> str:
        """Find date in first few rows of XLSX."""
        for row in rows[:max_rows]:
            if not row:
                continue
            row_text = ' '.join(str(c) for c in row[:5] if c)
            date_match = re.search(
                r'(?:\w+\s+)?(\d{1,2})\s+de\s+(\w+)\s+de\s+(\d{4})',
                row_text,
                re.IGNORECASE
            )
            if date_match:
                return parse_spanish_date(date_match.group()) or ""
        return ""

    def _find_city_headers_xls(self, sheet) -> Tuple[int, Dict[int, Tuple[str, str]]]:
        """Find city headers row and extract city/market mappings."""
        city_row_idx = -1
        cities_info = {}

        for row_idx in range(min(10, sheet.nrows)):
            row_vals = [sheet.cell_value(row_idx, col_idx) for col_idx in range(sheet.ncols)]
            row_text = ' '.join(str(v) for v in row_vals if v)

            # Look for row with city names
            if 'Precio' in row_text or 'Bogot' in row_text or 'Medell' in row_text:
                city_row_idx = row_idx

                # Parse city headers
                col_idx = 1  # Skip first column (product names)
                while col_idx < sheet.ncols:
                    cell_val = str(sheet.cell_value(row_idx, col_idx)).strip()
                    if cell_val and cell_val not in ['', 'Precio', 'Var %', 'Var%']:
                        cell_val = cell_val.replace('\n', ' ').strip()
                        city, market = extract_city_market(cell_val)
                        cities_info[col_idx] = (city, market)
                    col_idx += 1
                break

        return city_row_idx, cities_info

    def _find_city_headers_xlsx(self, rows: list) -> Tuple[int, Dict[int, Tuple[str, str]]]:
        """Find city headers row in XLSX."""
        city_row_idx = -1
        cities_info = {}

        for row_idx, row in enumerate(rows[:10]):
            if not row:
                continue
            row_text = ' '.join(str(v) for v in row if v)

            if 'Precio' in row_text or 'Bogot' in row_text or 'Medell' in row_text:
                city_row_idx = row_idx

                for col_idx in range(1, len(row)):
                    cell_val = row[col_idx]
                    if cell_val:
                        cell_val = str(cell_val).replace('\n', ' ').strip()
                        if cell_val not in ['', 'Precio', 'Var %', 'Var%']:
                            city, market = extract_city_market(cell_val)
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
