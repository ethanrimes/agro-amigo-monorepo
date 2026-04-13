#!/usr/bin/env python3
"""
Scraper for SIPSA rice price data (arroz y subproductos en molinos).
"""

import re
import sys
import time
from datetime import date
from pathlib import Path
from typing import Optional

import requests

_parent_dir = str(Path(__file__).parent.parent)
if _parent_dir not in sys.path:
    sys.path.insert(0, _parent_dir)

from config import REQUEST_DELAY, REQUEST_TIMEOUT, MAX_RETRIES
from backend.storage import StorageClient
from backend.database import DatabaseClient, DownloadEntry

HISTORICAL_URLS = [
    "https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/series-historicas/series-historicas-precios-mayoristas-arroz-sub-molinos-2013-2020.xlsx",
    "https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/series-historicas/series-historicas-precios-mayoristas-arroz-sub-molinos-2021.xlsx",
    "https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/series-historicas/series-historicas-precios-mayoristas-arroz-sub-molinos-2022.xlsx",
    "https://www.dane.gov.co/files/operaciones/SIPSA/anex-SIPSArroz-SerieHistoricaPrecio-2023.xlsx",
    "https://www.dane.gov.co/files/operaciones/SIPSA/anex-SIPSArroz-SerieHistoricaPrecio-2024.xlsx",
    "https://www.dane.gov.co/files/operaciones/SIPSA/anex-SIPSArroz-SerieHistoricaPrecio-2025.xlsx",
]

CURRENT_URL = "https://www.dane.gov.co/files/operaciones/SIPSA/anex-SIPSArroz-SerieHistoricaPrecio-2026.xlsx"


class RiceScraper:
    """Scraper for SIPSA rice mill price data."""

    def __init__(self, dry_run: bool = False):
        self.dry_run = dry_run
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
        })
        self.storage = StorageClient()
        self.database = DatabaseClient()

    def _request_with_retry(self, url, **kwargs):
        kwargs.setdefault('timeout', REQUEST_TIMEOUT)
        for attempt in range(MAX_RETRIES):
            try:
                r = self.session.get(url, **kwargs)
                r.raise_for_status()
                return r
            except requests.RequestException as e:
                if attempt < MAX_RETRIES - 1:
                    time.sleep(REQUEST_DELAY * (attempt + 1))
        return None

    def scrape_historical(self) -> dict:
        print("=" * 60)
        print("SIPSA Rice Price Historical Downloader")
        print("=" * 60)
        return self._download_urls(HISTORICAL_URLS)

    def scrape_current(self) -> dict:
        print("=" * 60)
        print("SIPSA Rice Price Current Year Downloader")
        print("=" * 60)
        return self._download_urls([CURRENT_URL])

    def _download_urls(self, urls) -> dict:
        downloaded = skipped = failed = 0
        entry_ids = []

        for url in urls:
            filename = url.split('/')[-1]
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
                failed += 1
                continue

            file_date = None
            m = re.search(r'(\d{4})', filename)
            if m:
                file_date = date(int(m.group(1)), 1, 1)

            storage_path = f"rice/{filename}"
            result = self.storage.upload_file(
                response.content, storage_path,
                'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
            )
            if not result.get('success'):
                print(f"  [ERROR] Upload failed: {result.get('error')}")
                failed += 1
                continue

            entry = DownloadEntry(
                row_name=f"Rice - {filename}",
                row_date=file_date,
                download_link=url,
                source_table_link='rice_molinos',
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
