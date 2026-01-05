"""
Base scraper with common functionality for SIPSA data download.
"""

import re
import time
from datetime import datetime
from typing import Optional, Dict, List, Tuple
from dataclasses import dataclass
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

import sys
from pathlib import Path

# Add parent directory to path for imports
_parent_dir = str(Path(__file__).parent.parent)
if _parent_dir not in sys.path:
    sys.path.insert(0, _parent_dir)

from config import (
    DANE_BASE_URL,
    SIPSA_MAIN_PAGE,
    REQUEST_DELAY,
    REQUEST_TIMEOUT,
    MAX_RETRIES,
    MONTH_ABBR_MAP,
    MONTHS_ES_REVERSE
)
from backend.storage import StorageClient
from backend.database import DatabaseClient, DownloadEntry, DownloadError


@dataclass
class FileLink:
    """Represents a file link found on the SIPSA website."""
    url: str
    link_text: str
    file_type: str  # 'pdf', 'excel', 'zip'
    file_date: Optional[datetime]
    filename: str
    source_page: str
    category: Optional[str] = None  # 'boletin', 'anexo', 'informes_ciudades'


class ScraperBase:
    """Base class for SIPSA web scrapers."""

    def __init__(self, dry_run: bool = False):
        """
        Initialize the scraper.

        Args:
            dry_run: If True, don't actually download or save anything
        """
        self.dry_run = dry_run
        self.session = self._create_session()
        self.storage = StorageClient()
        self.database = DatabaseClient()

    def _create_session(self) -> requests.Session:
        """Create a requests session with appropriate headers."""
        session = requests.Session()
        session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
        })
        return session

    def _request_with_retry(
        self,
        url: str,
        method: str = 'GET',
        **kwargs
    ) -> Optional[requests.Response]:
        """
        Make a request with retry logic.

        Args:
            url: URL to request
            method: HTTP method
            **kwargs: Additional arguments for requests

        Returns:
            Response object or None if all retries failed
        """
        kwargs.setdefault('timeout', REQUEST_TIMEOUT)

        for attempt in range(MAX_RETRIES):
            try:
                response = self.session.request(method, url, **kwargs)
                response.raise_for_status()
                return response
            except requests.RequestException as e:
                print(f"  Request failed (attempt {attempt + 1}/{MAX_RETRIES}): {e}")
                if attempt < MAX_RETRIES - 1:
                    time.sleep(REQUEST_DELAY * (attempt + 1))

        return None

    def extract_date_from_url(self, url: str) -> Optional[datetime]:
        """
        Extract date from file URL.

        Handles multiple formats:
        - Modern: anex-SIPSADiario-24dic2025.xlsx
        - Historical full month: mayoristas_noviembre_30_2018.xlsx
        - Historical abbreviated: anex_feb_28_2022.xlsx, bol_feb_28_2022.pdf
        - Old anexo format: mayoristas_anexo_sept_28_2012.xls
        - Regional format: bol-reg-28-02-2022.zip
        - SIPSA regional: sipsa-08-01-2021.zip
        """
        url_lower = url.lower()

        # Modern format: 24dic2025 (day + 3-letter-month + year concatenated)
        pattern1 = re.search(r'(\d{1,2})([a-z]{3,4})(\d{4})', url_lower)
        if pattern1:
            day, month_abbr, year = pattern1.groups()
            month = MONTH_ABBR_MAP.get(month_abbr)
            if month:
                try:
                    return datetime(int(year), month, int(day))
                except ValueError:
                    pass

        # Historical format with full month: mayoristas_noviembre_30_2018
        pattern2 = re.search(r'mayoristas_([a-z]+)_(\d{1,2})_(\d{4})', url_lower)
        if pattern2:
            month_name, day, year = pattern2.groups()
            month = MONTHS_ES_REVERSE.get(month_name)
            if month:
                try:
                    return datetime(int(year), month, int(day))
                except ValueError:
                    pass

        # Historical format with abbreviated month: anex_feb_28_2022, bol_feb_28_2022
        pattern3 = re.search(r'(?:anex|bol)_([a-z]{3,4})_(\d{1,2})_(\d{4})', url_lower)
        if pattern3:
            month_abbr, day, year = pattern3.groups()
            month = MONTH_ABBR_MAP.get(month_abbr)
            if month:
                try:
                    return datetime(int(year), month, int(day))
                except ValueError:
                    pass

        # Old anexo format with abbreviated month: mayoristas_anexo_sept_28_2012.xls
        pattern5 = re.search(r'mayoristas_anexo_([a-z]{3,4})_(\d{1,2})_(\d{4})', url_lower)
        if pattern5:
            month_abbr, day, year = pattern5.groups()
            month = MONTH_ABBR_MAP.get(month_abbr)
            if month:
                try:
                    return datetime(int(year), month, int(day))
                except ValueError:
                    pass

        # Old anexo format with full month name: mayoristas_anexo_agosto_31_2012.xls
        pattern6 = re.search(r'mayoristas_anexo_([a-z]+)_(\d{1,2})_(\d{4})', url_lower)
        if pattern6:
            month_name, day, year = pattern6.groups()
            month = MONTHS_ES_REVERSE.get(month_name)
            if month:
                try:
                    return datetime(int(year), month, int(day))
                except ValueError:
                    pass

        # Old format: mayoristas_julio_31_2012.xls (for Jun-Jul 2012)
        pattern7 = re.search(r'mayoristas_([a-z]+)_(\d{1,2})_(\d{4})\.xls', url_lower)
        if pattern7:
            month_name, day, year = pattern7.groups()
            month = MONTHS_ES_REVERSE.get(month_name)
            if month:
                try:
                    return datetime(int(year), month, int(day))
                except ValueError:
                    pass

        # Regional format: bol-reg-28-02-2022.zip (dd-mm-yyyy with hyphens)
        pattern4 = re.search(r'bol-reg-(\d{1,2})-(\d{2})-(\d{4})', url_lower)
        if pattern4:
            day, month, year = pattern4.groups()
            try:
                return datetime(int(year), int(month), int(day))
            except ValueError:
                pass

        # SIPSA regional reports: sipsa-08-01-2021.zip (dd-mm-yyyy with hyphens)
        pattern_sipsa = re.search(r'sipsa-(\d{1,2})-(\d{2})-(\d{4})', url_lower)
        if pattern_sipsa:
            day, month, year = pattern_sipsa.groups()
            try:
                return datetime(int(year), int(month), int(day))
            except ValueError:
                pass

        return None

    def get_file_type(self, href: str, link_text: str) -> Optional[str]:
        """
        Determine file type based on URL and link text.

        Returns:
            'pdf', 'excel', 'zip', or None if not a data file
        """
        href_lower = href.lower()
        text_lower = link_text.lower()

        # Check file extension first
        if href_lower.endswith('.zip'):
            return 'zip'
        elif href_lower.endswith('.pdf'):
            return 'pdf'
        elif href_lower.endswith('.xlsx') or href_lower.endswith('.xls'):
            return 'excel'

        # Check link text for clues
        if 'informes por ciudades' in text_lower or 'regionales' in href_lower:
            return 'zip'  # Usually ZIP for city reports
        elif 'anexo' in text_lower or 'anex-' in href_lower:
            return 'excel'  # Anexo files are Excel

        return None

    def get_link_category(self, href: str, link_text: str) -> Optional[str]:
        """
        Determine the category of a link (boletin, anexo, informes_ciudades, etc.)
        """
        text_lower = link_text.lower()
        href_lower = href.lower()

        # Check for regional/city reports FIRST (before boletín check)
        # These URLs may contain 'bol-' prefix but are not boletines
        # Formats: bol-reg-DD-MM-YYYY.zip, bol-SIPSADiario-regionales-DDmmmYYYY.zip
        if 'informes por ciudades' in text_lower or 'regionales' in href_lower:
            return 'informes_ciudades'

        # Boletín detection
        if 'boletín' in text_lower or 'boletin' in text_lower:
            return 'boletin'
        if 'bol_' in href_lower or 'bol-' in href_lower:
            return 'boletin'

        if 'anexo' in text_lower or 'anex-' in href_lower:
            return 'anexo'
        elif 'mayoristas' in href_lower:
            return 'anexo'

        return None

    def parse_date_from_text(self, text: str, default_year: Optional[int] = None) -> Optional[datetime]:
        """
        Parse a Spanish date string like "30 de septiembre de 2021" or "30 de septiembre".

        Args:
            text: Date text in Spanish format
            default_year: Year to use if not present in text (for current month pages)

        Returns:
            datetime object or None if parsing failed
        """
        if not text:
            return None

        text = text.strip().lower()

        # Pattern with year: "30 de septiembre de 2021" or "30 de septiembre 2021"
        pattern_with_year = re.search(r'(\d{1,2})\s+de\s+([a-záéíóú]+)(?:\s+de)?\s+(\d{4})', text)
        if pattern_with_year:
            day, month_name, year = pattern_with_year.groups()
            month = MONTHS_ES_REVERSE.get(month_name)
            if month:
                try:
                    return datetime(int(year), month, int(day))
                except ValueError:
                    pass

        # Pattern without year: "30 de septiembre" (needs default_year)
        if default_year:
            pattern_no_year = re.search(r'(\d{1,2})\s+de\s+([a-záéíóú]+)', text)
            if pattern_no_year:
                day, month_name = pattern_no_year.groups()
                month = MONTHS_ES_REVERSE.get(month_name)
                if month:
                    try:
                        return datetime(default_year, month, int(day))
                    except ValueError:
                        pass

        return None

    def _get_page_format(self, target_date: Optional[datetime]) -> str:
        """
        Determine page format based on target date.

        Returns one of:
        - 'four_column': March 2020+ (Día, Boletín, Anexos, Informes por ciudades)
        - 'three_column': Dec 2015 - Feb 2020 (Día, Documentos, Anexos)
        - 'bullet_list': Aug 2012 - Nov 2015 (Boletín/Anexo bullet pairs)
        - 'simple_links': Jun-Jul 2012 (just date links)
        - 'current': No target date (use current page format)
        """
        if target_date is None:
            return 'current'

        # March 2020 onwards: 4-column format
        if target_date >= datetime(2020, 3, 1):
            return 'four_column'
        # December 2015 - February 2020: 3-column format
        elif target_date >= datetime(2015, 12, 1):
            return 'three_column'
        # August 2012 - November 2015: bullet list format
        elif target_date >= datetime(2012, 8, 1):
            return 'bullet_list'
        # June-July 2012: simple date links
        else:
            return 'simple_links'

    def _get_year_from_url(self, url: str) -> Optional[int]:
        """Extract year from page URL."""
        match = re.search(r'(\d{4})', url)
        return int(match.group(1)) if match else None

    def _extract_four_column_table(
        self,
        soup: BeautifulSoup,
        page_url: str,
        target_date: Optional[datetime] = None
    ) -> List[FileLink]:
        """
        Extract links from 4-column table format (March 2020+).
        Columns: Día, Boletín (skip), Anexos, Precios mínimos y máximos
        """
        links = []
        column_categories = {
            # Column 1 (Boletines) intentionally omitted - returns None to skip
            2: 'anexo',
            3: 'informes_ciudades',
        }

        # Get default year for dates without year (e.g., "28 de enero")
        default_year = target_date.year if target_date else self._get_year_from_url(page_url)

        for table in soup.find_all('table'):
            for row in table.find_all('tr'):
                cells = row.find_all(['td', 'th'])
                if not cells:
                    continue

                # Try to find date in the first cell (Día column)
                first_cell_text = cells[0].get_text(strip=True)
                row_date = self.parse_date_from_text(first_cell_text, default_year)

                # Extract links from each cell, using column index for category
                for col_index, cell in enumerate(cells):
                    category = column_categories.get(col_index)
                    if category is None:
                        continue  # Skip column 0 (date) and column 1 (boletín)

                    for a in cell.find_all('a', href=True):
                        href = a['href']
                        if '/files/' not in href:
                            continue

                        link_text = a.get_text(strip=True)
                        file_type = self.get_file_type(href, link_text)
                        if not file_type:
                            continue

                        full_url = urljoin(DANE_BASE_URL, href)
                        file_date = row_date if row_date else self.extract_date_from_url(href)
                        filename = href.split('/')[-1]

                        links.append(FileLink(
                            url=full_url,
                            link_text=link_text,
                            file_type=file_type,
                            file_date=file_date,
                            filename=filename,
                            source_page=page_url,
                            category=category
                        ))
        return links

    def _extract_three_column_table(
        self,
        soup: BeautifulSoup,
        page_url: str,
        target_date: Optional[datetime] = None
    ) -> List[FileLink]:
        """
        Extract links from 3-column table format (Dec 2015 - Feb 2020).
        Columns: Día, Documentos (skip), Anexos
        We only want the last column (Anexos).
        """
        links = []
        default_year = target_date.year if target_date else self._get_year_from_url(page_url)

        for table in soup.find_all('table'):
            for row in table.find_all('tr'):
                cells = row.find_all(['td', 'th'])
                if len(cells) < 3:
                    continue

                # Try to find date in the first cell (Día column)
                first_cell_text = cells[0].get_text(strip=True)
                row_date = self.parse_date_from_text(first_cell_text, default_year)

                # Only extract from the last column (Anexos = column 2)
                last_cell = cells[-1]  # Use last cell to be safe
                for a in last_cell.find_all('a', href=True):
                    href = a['href']
                    if '/files/' not in href:
                        continue

                    link_text = a.get_text(strip=True)
                    file_type = self.get_file_type(href, link_text)
                    if not file_type:
                        continue

                    full_url = urljoin(DANE_BASE_URL, href)
                    file_date = row_date if row_date else self.extract_date_from_url(href)
                    filename = href.split('/')[-1]

                    links.append(FileLink(
                        url=full_url,
                        link_text=link_text,
                        file_type=file_type,
                        file_date=file_date,
                        filename=filename,
                        source_page=page_url,
                        category='anexo'
                    ))
        return links

    def _parse_date_from_bullet_text(self, text: str, page_url: str) -> Optional[datetime]:
        """
        Parse date from bullet list link text like "Anexo - 31 de agosto".
        Extracts year from the page URL since it's not in the text.
        """
        # Extract year from page URL (e.g., "agosto-de-2012-1" -> 2012)
        year_match = re.search(r'(\d{4})', page_url)
        if not year_match:
            return None
        year = int(year_match.group(1))

        # Pattern: "Anexo - DD de month" or "DD de month"
        pattern = re.search(r'(\d{1,2})\s+de\s+([a-záéíóú]+)', text.lower())
        if pattern:
            day, month_name = pattern.groups()
            month = MONTHS_ES_REVERSE.get(month_name)
            if month:
                try:
                    return datetime(year, month, int(day))
                except ValueError:
                    pass
        return None

    def _extract_bullet_list(
        self,
        soup: BeautifulSoup,
        page_url: str
    ) -> List[FileLink]:
        """
        Extract links from bullet list format (Aug 2012 - Nov 2015).
        Format: "Boletín - DD de month" and "Anexo - DD de month"
        We only want the "Anexo" links.
        """
        links = []

        for a in soup.find_all('a', href=True):
            href = a['href']
            if '/files/' not in href:
                continue

            link_text = a.get_text(strip=True)

            # Only get Anexo links, skip Boletín
            if not link_text.lower().startswith('anexo'):
                continue

            file_type = self.get_file_type(href, link_text)
            if not file_type:
                # Default to excel for anexo links
                file_type = 'excel'

            full_url = urljoin(DANE_BASE_URL, href)

            # Parse date from link text "Anexo - DD de month" + year from URL
            file_date = self._parse_date_from_bullet_text(link_text, page_url)
            if not file_date:
                file_date = self.extract_date_from_url(href)
            filename = href.split('/')[-1]

            links.append(FileLink(
                url=full_url,
                link_text=link_text,
                file_type=file_type,
                file_date=file_date,
                filename=filename,
                source_page=page_url,
                category='anexo'
            ))
        return links

    def _extract_simple_links(
        self,
        soup: BeautifulSoup,
        page_url: str
    ) -> List[FileLink]:
        """
        Extract links from simple date link format (Jun-Jul 2012).
        Format: Just date text like "31 de julio de 2012" as link text
        All links are anexos. Only extract SIPSA/mayoristas files.
        """
        links = []

        for a in soup.find_all('a', href=True):
            href = a['href']
            if '/files/' not in href:
                continue

            # Only get SIPSA/mayoristas files, skip unrelated files
            href_lower = href.lower()
            if 'mayoristas' not in href_lower and 'sipsa' not in href_lower:
                continue

            link_text = a.get_text(strip=True)
            file_type = self.get_file_type(href, link_text)
            if not file_type:
                # Default to excel for these old links
                file_type = 'excel'

            full_url = urljoin(DANE_BASE_URL, href)

            # Date is in the link text itself: "31 de julio de 2012"
            file_date = self.parse_date_from_text(link_text)
            if not file_date:
                file_date = self.extract_date_from_url(href)
            filename = href.split('/')[-1]

            links.append(FileLink(
                url=full_url,
                link_text=link_text,
                file_type=file_type,
                file_date=file_date,
                filename=filename,
                source_page=page_url,
                category='anexo'
            ))
        return links

    def extract_links_from_page(
        self,
        page_url: str,
        html_content: str,
        target_date: Optional[datetime] = None
    ) -> List[FileLink]:
        """
        Extract all file links from a page's HTML content.
        Uses different parsing strategies based on the page's date format.

        Args:
            page_url: URL of the page (for building absolute URLs)
            html_content: HTML content of the page
            target_date: Optional date to determine page format (for historical pages)

        Returns:
            List of FileLink objects
        """
        soup = BeautifulSoup(html_content, 'html.parser')
        page_format = self._get_page_format(target_date)

        if page_format == 'four_column' or page_format == 'current':
            links = self._extract_four_column_table(soup, page_url, target_date)
        elif page_format == 'three_column':
            links = self._extract_three_column_table(soup, page_url, target_date)
        elif page_format == 'bullet_list':
            links = self._extract_bullet_list(soup, page_url)
        elif page_format == 'simple_links':
            links = self._extract_simple_links(soup, page_url)
        else:
            links = []

        # If no links found with structured approach, fall back to generic extraction
        if not links:
            for a in soup.find_all('a', href=True):
                href = a['href']
                if '/files/' not in href:
                    continue

                link_text = a.get_text(strip=True)
                file_type = self.get_file_type(href, link_text)
                if not file_type:
                    continue

                full_url = urljoin(DANE_BASE_URL, href)
                file_date = self.extract_date_from_url(href)
                filename = href.split('/')[-1]

                # Use keyword matching for category as fallback
                category = self.get_link_category(href, link_text)

                links.append(FileLink(
                    url=full_url,
                    link_text=link_text,
                    file_type=file_type,
                    file_date=file_date,
                    filename=filename,
                    source_page=page_url,
                    category=category
                ))

        return links

    def is_already_downloaded(self, download_link: str) -> bool:
        """Check if a file has already been downloaded."""
        existing = self.database.get_download_entry_by_link(download_link)
        return existing is not None

    def log_download_error(
        self,
        url: str,
        source_page: str,
        error_type: str,
        error_message: str,
        file_type: str = "",
        error_code: int = None
    ) -> None:
        """Log a download error to the database."""
        try:
            error = DownloadError(
                download_url=url,
                source_page=source_page,
                error_type=error_type,
                error_code=error_code,
                error_message=str(error_message)[:1000],  # Truncate long messages
                file_type=file_type
            )
            self.database.create_download_error(error)
        except Exception as e:
            # Don't let error logging failures break the main flow
            print(f"  [WARN] Failed to log error: {e}")

    def download_and_store_file(
        self,
        file_link: FileLink
    ) -> Optional[str]:
        """
        Download a file and store it in Supabase storage.

        Args:
            file_link: FileLink object with URL and metadata

        Returns:
            Download entry ID if successful, None otherwise
        """
        if self.dry_run:
            print(f"  [DRY-RUN] Would download: {file_link.filename}")
            return "dry-run-id"

        # Check if already downloaded
        if self.is_already_downloaded(file_link.url):
            print(f"  [SKIP] Already downloaded: {file_link.filename}")
            return None

        # Log if date could not be parsed
        if file_link.file_date is None:
            self.log_download_error(
                url=file_link.url,
                source_page=file_link.source_page,
                error_type='date_parse_error',
                error_message=f"Could not parse date from filename: {file_link.filename}",
                file_type=file_link.file_type
            )

        # Download the file
        print(f"  Downloading: {file_link.filename}")
        response = self._request_with_retry(file_link.url, stream=True)

        if response is None:
            print(f"  [ERROR] Failed to download: {file_link.filename}")
            self.log_download_error(
                url=file_link.url,
                source_page=file_link.source_page,
                error_type='http_error',
                error_message=f"Failed to download after {MAX_RETRIES} retries",
                file_type=file_link.file_type
            )
            return None

        file_data = response.content

        # Generate storage path
        if file_link.file_date:
            category = self.get_link_category(file_link.url, file_link.link_text) or file_link.file_type
            storage_path = self.storage.generate_storage_path(
                file_link.file_date,
                category,
                file_link.filename
            )
        else:
            # Fallback for files without dates
            storage_path = f"unknown_date/{file_link.file_type}/{file_link.filename}"

        # Upload to storage
        upload_result = self.storage.upload_file(
            file_data,
            storage_path,
            self._get_content_type(file_link.file_type)
        )

        if not upload_result.get('success'):
            error_msg = upload_result.get('error', 'Unknown error')
            error_str = str(error_msg).lower()

            # Categorize upload errors
            if '409' in error_str or 'duplicate' in error_str or 'already exists' in error_str:
                error_type = 'upload_duplicate'
            elif 'errno 35' in error_str or 'resource temporarily unavailable' in error_str:
                error_type = 'upload_transient'
            else:
                error_type = 'upload_error'

            print(f"  [ERROR] Failed to upload: {file_link.filename}")
            print(f"    {error_msg}")
            self.log_download_error(
                url=file_link.url,
                source_page=file_link.source_page,
                error_type=error_type,
                error_message=f"Upload failed: {error_msg}",
                file_type=file_link.file_type
            )
            return None

        # Create download entry
        entry = DownloadEntry(
            row_name=file_link.link_text,
            row_date=file_link.file_date.date() if file_link.file_date else None,
            download_link=file_link.url,
            source_table_link=file_link.source_page,
            storage_path=storage_path,
            file_type=file_link.file_type
        )

        entry_id = self.database.create_download_entry(entry)

        if entry_id:
            print(f"  [OK] Stored: {file_link.filename}")
        else:
            print(f"  [ERROR] Failed to create database entry: {file_link.filename}")
            self.log_download_error(
                url=file_link.url,
                source_page=file_link.source_page,
                error_type='database_error',
                error_message="Failed to create database entry",
                file_type=file_link.file_type
            )

        return entry_id

    def _get_content_type(self, file_type: str) -> str:
        """Get MIME type for file type."""
        content_types = {
            'pdf': 'application/pdf',
            'excel': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            'zip': 'application/zip'
        }
        return content_types.get(file_type, 'application/octet-stream')

    def respect_rate_limit(self):
        """Sleep to respect rate limiting."""
        time.sleep(REQUEST_DELAY)
