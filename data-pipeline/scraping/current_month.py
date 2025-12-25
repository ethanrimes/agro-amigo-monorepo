"""
Current month scraper for downloading latest SIPSA data.

Downloads the current month's Anexo and Informes por ciudades files
from DANE's SIPSA website.
"""

from typing import List, Optional
from datetime import datetime

import sys
from pathlib import Path

_parent_dir = str(Path(__file__).parent.parent)
if _parent_dir not in sys.path:
    sys.path.insert(0, _parent_dir)

from config import SIPSA_MAIN_PAGE
from scraping.scraper_base import ScraperBase, FileLink


class CurrentMonthScraper(ScraperBase):
    """Scraper for current month SIPSA data."""

    def __init__(self, dry_run: bool = False):
        """
        Initialize the current month scraper.

        Args:
            dry_run: If True, don't actually download or save anything
        """
        super().__init__(dry_run=dry_run)

    def get_current_month_links(self) -> List[FileLink]:
        """
        Fetch and parse current month links from the main SIPSA page.

        Returns:
            List of FileLink objects for current month files
        """
        print(f"Fetching main page: {SIPSA_MAIN_PAGE}")

        response = self._request_with_retry(SIPSA_MAIN_PAGE)
        if response is None:
            print("Failed to fetch main page")
            return []

        links = self.extract_links_from_page(SIPSA_MAIN_PAGE, response.text)

        # Filter to only links with dates (current month files have dates)
        links_with_dates = [l for l in links if l.file_date is not None]

        return links_with_dates

    def run(self, anexo_only: bool = False, informes_only: bool = False, include_boletin: bool = False) -> dict:
        """
        Run the current month scraper.

        Args:
            anexo_only: Only download Anexo files
            informes_only: Only download Informes por ciudades files
            include_boletin: Include Boletín files (excluded by default)

        Returns:
            Summary dict with counts
        """
        print("=" * 60)
        print("SIPSA Current Month Downloader")
        print("=" * 60)

        if self.dry_run:
            print("Mode: DRY RUN (no files will be downloaded)")

        # Get all links from main page
        links = self.get_current_month_links()

        if not links:
            print("No links found!")
            return {
                'total_found': 0,
                'downloaded': 0,
                'skipped': 0,
                'failed': 0,
                'entry_ids': []
            }

        # Filter out Boletín by default (unless explicitly included)
        if not include_boletin:
            links = [l for l in links if self.get_link_category(l.url, l.link_text) != 'boletin']

        # Filter by type if requested
        if anexo_only:
            links = [l for l in links if 'anexo' in l.link_text.lower() or 'anex-' in l.url.lower()]
            print("Filtering: Anexo only")
        elif informes_only:
            links = [l for l in links if 'informes' in l.link_text.lower() or 'regionales' in l.url.lower()]
            print("Filtering: Informes por ciudades only")

        # Categorize links
        anexo_links = [l for l in links if self.get_link_category(l.url, l.link_text) == 'anexo']
        informes_links = [l for l in links if self.get_link_category(l.url, l.link_text) == 'informes_ciudades']

        print(f"\nFound {len(links)} files:")
        print(f"  - Anexo: {len(anexo_links)}")
        print(f"  - Informes por ciudades: {len(informes_links)}")

        # Download files
        downloaded = 0
        skipped = 0
        failed = 0
        entry_ids = []

        print("\nDownloading Anexo files...")
        for link in anexo_links:
            result = self.download_and_store_file(link)
            if result == "dry-run-id":
                downloaded += 1
            elif result:
                downloaded += 1
                entry_ids.append(result)
            elif self.is_already_downloaded(link.url):
                skipped += 1
            else:
                failed += 1
            self.respect_rate_limit()

        print("\nDownloading Informes por ciudades files...")
        for link in informes_links:
            result = self.download_and_store_file(link)
            if result == "dry-run-id":
                downloaded += 1
            elif result:
                downloaded += 1
                entry_ids.append(result)
            elif self.is_already_downloaded(link.url):
                skipped += 1
            else:
                failed += 1
            self.respect_rate_limit()

        print("\n" + "=" * 60)
        print("Download Summary")
        print("=" * 60)
        print(f"  Downloaded: {downloaded}")
        print(f"  Skipped (already exist): {skipped}")
        print(f"  Failed: {failed}")
        print("=" * 60)

        return {
            'total_found': len(links),
            'downloaded': downloaded,
            'skipped': skipped,
            'failed': failed,
            'entry_ids': entry_ids
        }


def main():
    """CLI entry point for current month scraper."""
    import argparse

    parser = argparse.ArgumentParser(description='Download current month SIPSA data')
    parser.add_argument('--dry-run', action='store_true',
                        help='Show what would be downloaded without downloading')
    parser.add_argument('--anexo-only', action='store_true',
                        help='Download only Anexo files')
    parser.add_argument('--informes-only', action='store_true',
                        help='Download only Informes por ciudades files')
    parser.add_argument('--include-boletin', action='store_true',
                        help='Include Boletín PDF files (excluded by default)')

    args = parser.parse_args()

    scraper = CurrentMonthScraper(dry_run=args.dry_run)
    result = scraper.run(
        anexo_only=args.anexo_only,
        informes_only=args.informes_only,
        include_boletin=args.include_boletin
    )

    return 0 if result['failed'] == 0 else 1


if __name__ == "__main__":
    import sys
    sys.exit(main())
