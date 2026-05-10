#!/usr/bin/env python3
"""
Scraper for SIPSA insumos (agricultural input) price data.

Downloads historical and current Excel files from DANE's SIPSA website.
Files are stored locally due to their size (~50MB each).
"""

import os
import re
import sys
import time
from datetime import date
from pathlib import Path
from typing import List, Optional

import requests

_parent_dir = str(Path(__file__).parent.parent)
if _parent_dir not in sys.path:
    sys.path.insert(0, _parent_dir)

from config import REQUEST_DELAY, REQUEST_TIMEOUT, MAX_RETRIES, DATA_PIPELINE_ROOT
from backend.database import DatabaseClient, DownloadEntry
from scraping.freshness import check_url_freshness, cleanup_stale_entry

INSUMOS_LOCAL_DIR = DATA_PIPELINE_ROOT / "exports" / "insumos"

# Historical municipality-level (2013-2020)
HISTORICAL_MUN_URL = "https://www.dane.gov.co/files/operaciones/SIPSA/anex-series-historicas-insumos-2013-2020.xlsx"

# Current municipality-level (2021-2026)
CURRENT_MUN_URL = "https://www.dane.gov.co/files/operaciones/SIPSA/anex-SIPSAInsumos-SeriesHistoricasMun-2021-2026.xlsx"

# Department-level (2018-2026)
DEPT_URL = "https://www.dane.gov.co/files/operaciones/SIPSA/anex-SIPSAInsumos-SeriesHistoricasDep-2018-2026.xlsx"

ALL_URLS = [HISTORICAL_MUN_URL, CURRENT_MUN_URL, DEPT_URL]


class InsumosScraper:
    """Scraper for SIPSA insumos price data."""

    def __init__(self, dry_run: bool = False):
        self.dry_run = dry_run
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
        })
        self.database = DatabaseClient()
        INSUMOS_LOCAL_DIR.mkdir(parents=True, exist_ok=True)

    def _request_with_retry(self, url: str, **kwargs) -> Optional[requests.Response]:
        kwargs.setdefault('timeout', REQUEST_TIMEOUT * 3)
        for attempt in range(MAX_RETRIES):
            try:
                response = self.session.get(url, **kwargs)
                response.raise_for_status()
                return response
            except requests.RequestException as e:
                print(f"  Request failed (attempt {attempt + 1}/{MAX_RETRIES}): {e}")
                if attempt < MAX_RETRIES - 1:
                    time.sleep(REQUEST_DELAY * (attempt + 1) * 2)
        return None

    def scrape_all(self) -> dict:
        """Download all insumos files."""
        print("=" * 60)
        print("SIPSA Insumos Price Downloader")
        print("=" * 60)
        return self._download_urls(ALL_URLS)

    def scrape_historical(self) -> dict:
        """Download only historical insumos files."""
        print("=" * 60)
        print("SIPSA Insumos Historical Downloader")
        print("=" * 60)
        return self._download_urls([HISTORICAL_MUN_URL])

    def scrape_current(self) -> dict:
        """Download current insumos files (municipality + department)."""
        print("=" * 60)
        print("SIPSA Insumos Current Downloader")
        print("=" * 60)
        return self._download_urls([CURRENT_MUN_URL, DEPT_URL])

    def _download_urls(self, urls: List[str]) -> dict:
        downloaded = 0
        skipped = 0
        failed = 0
        entry_ids = []

        for url in urls:
            filename = url.split('/')[-1]

            freshness = check_url_freshness(self.database, self.session, url)
            if freshness.status == "fresh":
                print(f"  [SKIP] Up to date: {filename}")
                skipped += 1
                continue
            if freshness.status == "stale" and freshness.existing_entry:
                print(f"  [REFRESH] Server copy newer than {freshness.existing_entry.get('download_date')}: {filename}")
                if not self.dry_run:
                    is_dept = 'Dep' in filename
                    dest = "insumo_prices_department" if is_dept else "insumo_prices_municipality"
                    cleanup_stale_entry(freshness.existing_entry, [dest])

            if self.dry_run:
                print(f"  [DRY-RUN] Would download: {filename}")
                downloaded += 1
                continue

            local_path = INSUMOS_LOCAL_DIR / filename

            if local_path.exists():
                size_mb = local_path.stat().st_size / 1024 / 1024
                print(f"  [LOCAL] Already on disk: {filename} ({size_mb:.1f} MB)")
            else:
                print(f"  Downloading: {filename} ...", end='', flush=True)
                response = self._request_with_retry(url)
                if not response:
                    print(f" FAILED")
                    failed += 1
                    continue
                with open(local_path, 'wb') as f:
                    f.write(response.content)
                size_mb = len(response.content) / 1024 / 1024
                print(f" {size_mb:.1f} MB")

            # Determine data type from URL
            if 'Dep' in filename:
                data_type = 'department'
            else:
                data_type = 'municipality'

            storage_path = f"local:{local_path}"

            entry = DownloadEntry(
                row_name=f"Insumos {data_type} - {filename}",
                row_date=date.today(),
                download_link=url,
                source_table_link='insumos_series_historicas',
                storage_path=storage_path,
                file_type='excel'
            )
            entry_id = self.database.create_download_entry(entry)
            if entry_id:
                print(f"  [OK] Registered: {filename}")
                downloaded += 1
                entry_ids.append(entry_id)
            else:
                failed += 1

            time.sleep(REQUEST_DELAY)

        print(f"\n  Downloaded: {downloaded}, Skipped: {skipped}, Failed: {failed}")
        return {'downloaded': downloaded, 'skipped': skipped, 'failed': failed, 'entry_ids': entry_ids}
