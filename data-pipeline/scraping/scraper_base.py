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

        # Old anexo format: mayoristas_anexo_sept_28_2012.xls
        pattern5 = re.search(r'mayoristas_anexo_([a-z]{3,4})_(\d{1,2})_(\d{4})', url_lower)
        if pattern5:
            month_abbr, day, year = pattern5.groups()
            month = MONTH_ABBR_MAP.get(month_abbr)
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

        # Boletín detection - check first since some URLs may contain 'bol' prefix
        if 'boletín' in text_lower or 'boletin' in text_lower:
            return 'boletin'
        if 'bol_' in href_lower or 'bol-' in href_lower:
            # Make sure it's not a regional report (bol-reg-)
            if 'bol-reg' not in href_lower:
                return 'boletin'

        if 'informes por ciudades' in text_lower or 'regionales' in href_lower:
            return 'informes_ciudades'
        elif 'anexo' in text_lower or 'anex-' in href_lower:
            return 'anexo'
        elif 'mayoristas' in href_lower:
            return 'anexo'

        return None

    def parse_date_from_text(self, text: str) -> Optional[datetime]:
        """
        Parse a Spanish date string like "30 de septiembre de 2021".

        Args:
            text: Date text in Spanish format

        Returns:
            datetime object or None if parsing failed
        """
        if not text:
            return None

        text = text.strip().lower()

        # Pattern: "30 de septiembre de 2021" or "30 de septiembre 2021"
        pattern = re.search(r'(\d{1,2})\s+de\s+([a-záéíóú]+)(?:\s+de)?\s+(\d{4})', text)
        if pattern:
            day, month_name, year = pattern.groups()
            month = MONTHS_ES_REVERSE.get(month_name)
            if month:
                try:
                    return datetime(int(year), month, int(day))
                except ValueError:
                    pass

        return None

    def extract_links_from_page(
        self,
        page_url: str,
        html_content: str
    ) -> List[FileLink]:
        """
        Extract all file links from a page's HTML content.
        Prioritizes extracting dates from table row context over filename parsing.

        Args:
            page_url: URL of the page (for building absolute URLs)
            html_content: HTML content of the page

        Returns:
            List of FileLink objects
        """
        soup = BeautifulSoup(html_content, 'html.parser')
        links = []

        # First, try to extract links from table rows with date context
        for table in soup.find_all('table'):
            for row in table.find_all('tr'):
                cells = row.find_all(['td', 'th'])
                if not cells:
                    continue

                # Try to find date in the first cell (Día column)
                row_date = None
                first_cell_text = cells[0].get_text(strip=True)
                row_date = self.parse_date_from_text(first_cell_text)

                # Extract all file links from this row
                for a in row.find_all('a', href=True):
                    href = a['href']

                    if not href.startswith('/files/'):
                        continue

                    link_text = a.get_text(strip=True)
                    file_type = self.get_file_type(href, link_text)

                    if not file_type:
                        continue

                    full_url = urljoin(DANE_BASE_URL, href)
                    # Use row date if available, otherwise fall back to URL parsing
                    file_date = row_date if row_date else self.extract_date_from_url(href)
                    filename = href.split('/')[-1]

                    links.append(FileLink(
                        url=full_url,
                        link_text=link_text,
                        file_type=file_type,
                        file_date=file_date,
                        filename=filename,
                        source_page=page_url
                    ))

        # If no links found in tables, fall back to finding all links on page
        if not links:
            for a in soup.find_all('a', href=True):
                href = a['href']

                if not href.startswith('/files/'):
                    continue

                link_text = a.get_text(strip=True)
                file_type = self.get_file_type(href, link_text)

                if not file_type:
                    continue

                full_url = urljoin(DANE_BASE_URL, href)
                file_date = self.extract_date_from_url(href)
                filename = href.split('/')[-1]

                links.append(FileLink(
                    url=full_url,
                    link_text=link_text,
                    file_type=file_type,
                    file_date=file_date,
                    filename=filename,
                    source_page=page_url
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
            print(f"  [ERROR] Failed to upload: {file_link.filename}")
            print(f"    {error_msg}")
            self.log_download_error(
                url=file_link.url,
                source_page=file_link.source_page,
                error_type='upload_error',
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
