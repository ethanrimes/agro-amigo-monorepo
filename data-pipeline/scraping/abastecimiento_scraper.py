#!/usr/bin/env python3
"""
Scraper for SIPSA abastecimiento (supply/quantity) data.

Downloads microdato Excel files from DANE's SIPSA website.
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

# Local directory for large abastecimiento files (not uploaded to Supabase storage)
ABAST_LOCAL_DIR = DATA_PIPELINE_ROOT / "exports" / "abastecimiento"

HISTORICAL_URLS = [
    "https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/series-historicas/microdato-abastecimiento-2013.xlsx",
    "https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/series-historicas/microdato-abastecimiento-2014.xlsx",
    "https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/series-historicas/microdato-abastecimiento-2015.xlsx",
    "https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/series-historicas/microdato-abastecimiento-2016.xlsx",
    "https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/series-historicas/microdato-abastecimiento-2017.xlsx",
    "https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/series-historicas/microdato-abastecimiento-2018.xlsx",
    "https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/series-historicas/microdato-abastecimiento-2019.xlsx",
    "https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/series-historicas/microdato-abastecimiento-2020.xlsx",
    "https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/series-historicas/microdato-abastecimiento-2021.xlsx",
    "https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/series-historicas/microdato-abastecimiento-2022.xlsx",
    "https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/series-historicas/microdato-abastecimiento-2023.xlsx",
    "https://www.dane.gov.co/files/operaciones/SIPSA/anex-Microdato-abastecimiento-2024.xlsx",
    "https://www.dane.gov.co/files/operaciones/SIPSA/anex-Microdato-abastecimiento-2025.xlsx",
]

CURRENT_URL = "https://www.dane.gov.co/files/operaciones/SIPSA/anex-Microdato-abastecimiento-2026.xlsx"


class AbastecimientoScraper:
    """Scraper for SIPSA abastecimiento data."""

    def __init__(self, dry_run: bool = False):
        self.dry_run = dry_run
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
        })
        self.database = DatabaseClient()
        ABAST_LOCAL_DIR.mkdir(parents=True, exist_ok=True)

    def _request_with_retry(self, url: str, **kwargs) -> Optional[requests.Response]:
        kwargs.setdefault('timeout', REQUEST_TIMEOUT * 3)  # Larger files need more time
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

    def scrape_historical(self) -> dict:
        """Download all historical abastecimiento files."""
        print("=" * 60)
        print("SIPSA Abastecimiento Historical Downloader")
        print("=" * 60)
        return self._download_urls(HISTORICAL_URLS)

    def scrape_current(self) -> dict:
        """Download the current year's abastecimiento file."""
        print("=" * 60)
        print("SIPSA Abastecimiento Current Year Downloader")
        print("=" * 60)
        return self._download_urls([CURRENT_URL])

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
                    cleanup_stale_entry(freshness.existing_entry, ["supply_observations"])

            if self.dry_run:
                print(f"  [DRY-RUN] Would download: {filename}")
                downloaded += 1
                continue

            # Save locally (files are 50-100MB, too large for Supabase storage)
            local_path = ABAST_LOCAL_DIR / filename

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

            # Parse year from filename
            year_match = re.search(r'(\d{4})', filename)
            file_date = date(int(year_match.group(1)), 1, 1) if year_match else None

            # Store local path as the storage_path (prefixed with 'local:')
            storage_path = f"local:{local_path}"

            entry = DownloadEntry(
                row_name=f"Abastecimiento - {filename}",
                row_date=file_date,
                download_link=url,
                source_table_link='abastecimiento_microdatos',
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
