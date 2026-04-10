#!/usr/bin/env python3
"""
Scraper for SIPSA milk price data.

Downloads monthly milk price Excel files from DANE's SIPSA website.
Handles both historical series and current monthly updates.
"""

import re
import sys
import time
from datetime import datetime, date
from pathlib import Path
from typing import List, Optional
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

_parent_dir = str(Path(__file__).parent.parent)
if _parent_dir not in sys.path:
    sys.path.insert(0, _parent_dir)

from config import DANE_BASE_URL, REQUEST_DELAY, REQUEST_TIMEOUT, MAX_RETRIES, MONTHS_ES_REVERSE
from backend.storage import StorageClient
from backend.database import DatabaseClient, DownloadEntry

# Monthly milk bulletin page
MILK_PAGE_URL = (
    f"{DANE_BASE_URL}/index.php/estadisticas-por-tema/agropecuario/"
    "sistema-de-informacion-de-precios-sipsa/boletin-mensual-precios-de-leche-cruda-en-finca"
)

# Historical milk series URLs (newest first)
HISTORICAL_MILK_URLS = [
    "https://www.dane.gov.co/files/operaciones/SIPSA/anex-SIPSALeche-SerieHistoricaPrecios-2025.xlsx",
    "https://www.dane.gov.co/files/operaciones/SIPSA/anex-SIPSALeche-SerieHistoricaPrecios-2024.xlsx",
    "https://www.dane.gov.co/files/operaciones/SIPSA/anex-SIPSALeche-SerieHistoricaPrecios-2023.xlsx",
    "https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/series-historicas/series-historicas-precios-mayoristas-leche-2022.xlsx",
    "https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/series-historicas/series-historicas-precios-mayoristas-leche-2021.xlsx",
    "https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/series-historicas/series-historicas-precios-mayoristas-leche-2020.xlsx",
    "https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/series-historicas/series-historicas-precios-mayoristas-leche-2013-2019.xlsx",
]


class MilkScraper:
    """Scraper for SIPSA milk price data."""

    def __init__(self, dry_run: bool = False):
        self.dry_run = dry_run
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
        })
        self.storage = StorageClient()
        self.database = DatabaseClient()

    def _request_with_retry(self, url: str, **kwargs) -> Optional[requests.Response]:
        kwargs.setdefault('timeout', REQUEST_TIMEOUT)
        for attempt in range(MAX_RETRIES):
            try:
                response = self.session.get(url, **kwargs)
                response.raise_for_status()
                return response
            except requests.RequestException as e:
                print(f"  Request failed (attempt {attempt + 1}/{MAX_RETRIES}): {e}")
                if attempt < MAX_RETRIES - 1:
                    time.sleep(REQUEST_DELAY * (attempt + 1))
        return None

    def scrape_historical(self) -> dict:
        """Download all historical milk price series files."""
        print("=" * 60)
        print("SIPSA Milk Price Historical Downloader")
        print("=" * 60)

        downloaded = 0
        skipped = 0
        failed = 0
        entry_ids = []

        for url in HISTORICAL_MILK_URLS:
            filename = url.split('/')[-1]

            # Check if already downloaded
            existing = self.database.get_download_entry_by_link(url)
            if existing:
                print(f"  [SKIP] Already downloaded: {filename}")
                skipped += 1
                continue

            if self.dry_run:
                print(f"  [DRY-RUN] Would download: {filename}")
                downloaded += 1
                continue

            print(f"  Downloading: {filename}")
            response = self._request_with_retry(url, stream=True)
            if not response:
                print(f"  [ERROR] Failed to download: {filename}")
                failed += 1
                continue

            # Determine date range from filename
            file_date = self._parse_historical_date(filename)

            # Upload to storage
            storage_path = f"milk/historical/{filename}"
            result = self.storage.upload_file(
                response.content, storage_path,
                'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
            )

            if not result.get('success'):
                print(f"  [ERROR] Upload failed: {result.get('error')}")
                failed += 1
                continue

            # Create download entry
            entry = DownloadEntry(
                row_name=f"Milk historical - {filename}",
                row_date=file_date,
                download_link=url,
                source_table_link='historical_milk_series',
                storage_path=storage_path,
                file_type='excel'
            )
            entry_id = self.database.create_download_entry(entry)
            if entry_id:
                print(f"  [OK] Stored: {filename}")
                downloaded += 1
                entry_ids.append(entry_id)
            else:
                failed += 1

            time.sleep(REQUEST_DELAY)

        print(f"\n  Downloaded: {downloaded}, Skipped: {skipped}, Failed: {failed}")
        return {'downloaded': downloaded, 'skipped': skipped, 'failed': failed, 'entry_ids': entry_ids}

    def scrape_current(self) -> dict:
        """Scrape the current month's milk price Anexo from the SIPSA milk page."""
        print("=" * 60)
        print("SIPSA Milk Price Current Month Downloader")
        print("=" * 60)

        print(f"Fetching milk page: {MILK_PAGE_URL}")
        response = self._request_with_retry(MILK_PAGE_URL)
        if not response:
            print("Failed to fetch milk page")
            return {'downloaded': 0, 'skipped': 0, 'failed': 1, 'entry_ids': []}

        soup = BeautifulSoup(response.text, 'html.parser')

        # Find the Anexo link — look for links containing 'anex-SIPSALeche' or 'Anexo' text
        anexo_url = None
        for a in soup.find_all('a', href=True):
            href = a['href']
            text = a.get_text(strip=True).lower()
            if 'anexo' in text and ('sipsa' in href.lower() or 'leche' in href.lower()):
                anexo_url = urljoin(DANE_BASE_URL, href)
                break
            if 'anex-sipsaleche' in href.lower():
                anexo_url = urljoin(DANE_BASE_URL, href)
                break

        if not anexo_url:
            print("  [ERROR] Could not find Anexo link on milk page")
            return {'downloaded': 0, 'skipped': 0, 'failed': 1, 'entry_ids': []}

        filename = anexo_url.split('/')[-1]
        print(f"  Found: {filename}")

        # Check if already downloaded
        existing = self.database.get_download_entry_by_link(anexo_url)
        if existing:
            print(f"  [SKIP] Already downloaded: {filename}")
            return {'downloaded': 0, 'skipped': 1, 'failed': 0, 'entry_ids': []}

        if self.dry_run:
            print(f"  [DRY-RUN] Would download: {filename}")
            return {'downloaded': 1, 'skipped': 0, 'failed': 0, 'entry_ids': []}

        # Download
        print(f"  Downloading: {filename}")
        dl_response = self._request_with_retry(anexo_url, stream=True)
        if not dl_response:
            return {'downloaded': 0, 'skipped': 0, 'failed': 1, 'entry_ids': []}

        # Parse date from filename
        file_date = self._parse_monthly_date(filename)

        # Upload to storage
        storage_path = f"milk/monthly/{filename}"
        result = self.storage.upload_file(
            dl_response.content, storage_path,
            'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )

        if not result.get('success'):
            print(f"  [ERROR] Upload failed: {result.get('error')}")
            return {'downloaded': 0, 'skipped': 0, 'failed': 1, 'entry_ids': []}

        entry = DownloadEntry(
            row_name=f"Milk monthly - {filename}",
            row_date=file_date,
            download_link=anexo_url,
            source_table_link=MILK_PAGE_URL,
            storage_path=storage_path,
            file_type='excel'
        )
        entry_id = self.database.create_download_entry(entry)
        if entry_id:
            print(f"  [OK] Stored: {filename}")
            return {'downloaded': 1, 'skipped': 0, 'failed': 0, 'entry_ids': [entry_id]}

        return {'downloaded': 0, 'skipped': 0, 'failed': 1, 'entry_ids': []}

    def _parse_historical_date(self, filename: str) -> Optional[date]:
        """Parse date from historical filename like '...-2025.xlsx' or '...-2013-2019.xlsx'."""
        match = re.search(r'(\d{4})\.xlsx$', filename)
        if match:
            return date(int(match.group(1)), 1, 1)
        return None

    def _parse_monthly_date(self, filename: str) -> Optional[date]:
        """Parse date from monthly filename like 'anex-SIPSALeche-ene2026.xlsx'."""
        from config import MONTH_ABBR_MAP
        match = re.search(r'([a-z]{3,4})(\d{4})\.xlsx$', filename.lower())
        if match:
            month_abbr, year = match.groups()
            month = MONTH_ABBR_MAP.get(month_abbr)
            if month:
                return date(int(year), month, 1)
        return None


def main():
    import argparse
    parser = argparse.ArgumentParser(description='Download SIPSA milk price data')
    parser.add_argument('--dry-run', action='store_true')
    parser.add_argument('--historical', action='store_true', help='Download historical series')
    parser.add_argument('--current', action='store_true', help='Download current month')
    args = parser.parse_args()

    scraper = MilkScraper(dry_run=args.dry_run)

    if args.historical:
        scraper.scrape_historical()
    elif args.current:
        scraper.scrape_current()
    else:
        # Default: both
        scraper.scrape_historical()
        scraper.scrape_current()


if __name__ == '__main__':
    main()
