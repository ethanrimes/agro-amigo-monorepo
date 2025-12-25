"""
Historical data scraper for downloading SIPSA data within date range.

Downloads historical Anexo and Informes por ciudades files
from DANE's SIPSA website archives.
"""

import re
from datetime import datetime, date
from typing import List, Optional, Dict, Tuple
from concurrent.futures import ThreadPoolExecutor, as_completed

import sys
from pathlib import Path

_parent_dir = str(Path(__file__).parent.parent)
if _parent_dir not in sys.path:
    sys.path.insert(0, _parent_dir)

from config import (
    DANE_BASE_URL,
    SIPSA_MAIN_PAGE,
    MONTHS_ES,
    MONTHS_ES_REVERSE,
    MAX_THREADS
)
from scraping.scraper_base import ScraperBase, FileLink


class HistoricalScraper(ScraperBase):
    """Scraper for historical SIPSA data."""

    def __init__(self, dry_run: bool = False, max_threads: int = MAX_THREADS):
        """
        Initialize the historical scraper.

        Args:
            dry_run: If True, don't actually download or save anything
            max_threads: Maximum number of threads for parallel downloads
        """
        super().__init__(dry_run=dry_run)
        self.max_threads = max_threads

    def extract_year_month_from_page_url(self, url: str) -> Optional[Tuple[int, int]]:
        """
        Extract year and month from a historical page URL.

        IMPORTANT: Cannot use simple substring matching because 'mayo'
        appears in 'mayoristas'. Must use regex to match month names
        that are preceded by a hyphen.
        """
        url_lower = url.lower()

        for month_name, month_num in MONTHS_ES_REVERSE.items():
            # Pattern: month name preceded by hyphen (to avoid matching "mayo" in "mayoristas")
            pattern = rf'-{month_name}[-\s]|{month_name}-de-'
            if re.search(pattern, url_lower):
                year_match = re.search(r'(\d{4})', url)
                if year_match:
                    return (int(year_match.group(1)), month_num)

        return None

    def get_historical_month_urls(self) -> Dict[Tuple[int, int], List[str]]:
        """
        Get all historical month page URLs from the main page.

        Returns:
            Dict mapping (year, month) tuples to list of page URLs
            (some months have multiple URLs, e.g., with -1 suffix)
        """
        print("Fetching main page to find historical months...")

        response = self._request_with_retry(SIPSA_MAIN_PAGE)
        if response is None:
            print("Failed to fetch main page")
            return {}

        # Find all historical month URLs
        pattern = r'href="(/index\.php/estadisticas-por-tema/agropecuario/sistema-de-informacion-de-precios-sipsa/componente[^"]+)"'
        urls = {}

        for match in re.finditer(pattern, response.text, re.I):
            href = match.group(1)

            # Skip the main page itself
            if href.endswith('componente-precios-mayoristas'):
                continue

            result = self.extract_year_month_from_page_url(href)
            if result:
                year, month = result
                key = (year, month)
                full_url = f"{DANE_BASE_URL}{href}"
                if key not in urls:
                    urls[key] = []
                if full_url not in urls[key]:
                    urls[key].append(full_url)

        return urls

    def get_links_from_month_page(
        self,
        page_url: str,
        _year: int,
        _month: int
    ) -> List[FileLink]:
        """
        Extract file links from a historical month page.

        Args:
            page_url: URL of the month page
            _year: Year of the data (unused, for interface compatibility)
            _month: Month of the data (unused, for interface compatibility)

        Returns:
            List of FileLink objects
        """
        response = self._request_with_retry(page_url)
        if response is None:
            print(f"  Failed to fetch page: {page_url}")
            return []

        links = self.extract_links_from_page(page_url, response.text)
        return links

    def filter_links_by_date_range(
        self,
        links: List[FileLink],
        start_date: date,
        end_date: date
    ) -> List[FileLink]:
        """Filter links to only those within the specified date range."""
        filtered = []
        for link in links:
            if link.file_date:
                link_date = link.file_date.date()
                if start_date <= link_date <= end_date:
                    filtered.append(link)
        return filtered

    def download_link_threadsafe(self, link: FileLink) -> Tuple[str, Optional[str]]:
        """
        Thread-safe wrapper for downloading a single link.

        Returns:
            Tuple of (status, entry_id)
            Status is one of: 'downloaded', 'skipped', 'failed', 'dry-run'
        """
        if self.dry_run:
            print(f"  [DRY-RUN] Would download: {link.filename}")
            return ('dry-run', None)

        if self.is_already_downloaded(link.url):
            return ('skipped', None)

        result = self.download_and_store_file(link)
        if result:
            return ('downloaded', result)
        else:
            return ('failed', None)

    def run(
        self,
        start_date: date,
        end_date: date,
        anexo_only: bool = False,
        informes_only: bool = False,
        parallel: bool = True
    ) -> dict:
        """
        Run the historical scraper for a date range.

        Args:
            start_date: Start date for download range
            end_date: End date for download range
            anexo_only: Only download Anexo files
            informes_only: Only download Informes por ciudades files
            parallel: Use multithreading for downloads

        Returns:
            Summary dict with counts
        """
        print("=" * 60)
        print("SIPSA Historical Data Downloader")
        print("=" * 60)
        print(f"Date range: {start_date} to {end_date}")

        if anexo_only:
            print("Downloading: Anexo only")
        elif informes_only:
            print("Downloading: Informes por ciudades only")
            if start_date < date(2020, 3, 1):
                print("WARNING: Informes por ciudades are only available from March 2020")
        else:
            print("Downloading: Anexo and Informes por ciudades")

        if self.dry_run:
            print("Mode: DRY RUN")

        if parallel:
            print(f"Threads: {self.max_threads}")

        # Get all historical month URLs
        month_urls = self.get_historical_month_urls()
        print(f"\nFound {len(month_urls)} historical months on main page")

        # Filter months within date range
        months_to_process = []
        for (year, month), url_list in sorted(month_urls.items()):
            month_start = date(year, month, 1)
            if month == 12:
                month_end = date(year, 12, 31)
            else:
                month_end = date(year, month + 1, 1)

            # Check if this month overlaps with our date range
            if month_start <= end_date and month_end >= start_date:
                months_to_process.append((year, month, url_list))

        print(f"Months in date range: {len(months_to_process)}")

        # Collect all links from all month pages
        all_links = []

        for i, (year, month, url_list) in enumerate(months_to_process):
            month_name = MONTHS_ES[month].capitalize()
            print(f"\n[{i+1}/{len(months_to_process)}] Fetching {month_name} {year}...")

            links = []
            # Try each URL for this month until we find one that works
            urls_to_try = list(url_list)

            # Add fallback URLs with -1, -2 suffixes for older data that may not be on main page
            for url in list(url_list):
                for suffix in ['-1', '-2']:
                    alt_url = url + suffix
                    if alt_url not in urls_to_try:
                        urls_to_try.append(alt_url)

            for url in urls_to_try:
                try:
                    links = self.get_links_from_month_page(url, year, month)
                    if links:
                        break  # Found links, no need to try other URLs
                except Exception as e:
                    # Silently continue for fallback URLs
                    continue

            # Filter by file type
            if anexo_only:
                links = [l for l in links if self.get_link_category(l.url, l.link_text) == 'anexo']
            elif informes_only:
                links = [l for l in links if self.get_link_category(l.url, l.link_text) == 'informes_ciudades']

            # Filter by exact date range
            links = self.filter_links_by_date_range(links, start_date, end_date)

            if links:
                anexo_count = sum(1 for l in links if self.get_link_category(l.url, l.link_text) == 'anexo')
                informes_count = sum(1 for l in links if self.get_link_category(l.url, l.link_text) == 'informes_ciudades')
                print(f"  Found {len(links)} files (Anexo: {anexo_count}, Informes: {informes_count})")
                all_links.extend(links)
            else:
                print(f"  No files found in date range")

            self.respect_rate_limit()

        print(f"\nTotal files to download: {len(all_links)}")

        # Download files
        downloaded = 0
        skipped = 0
        failed = 0
        entry_ids = []

        if parallel and not self.dry_run and len(all_links) > 1:
            # Parallel downloads
            print("\nDownloading files in parallel...")
            with ThreadPoolExecutor(max_workers=self.max_threads) as executor:
                future_to_link = {
                    executor.submit(self.download_link_threadsafe, link): link
                    for link in all_links
                }

                for future in as_completed(future_to_link):
                    link = future_to_link[future]
                    try:
                        status, entry_id = future.result()
                        if status == 'downloaded':
                            downloaded += 1
                            if entry_id:
                                entry_ids.append(entry_id)
                        elif status == 'skipped':
                            skipped += 1
                        elif status == 'failed':
                            failed += 1
                        elif status == 'dry-run':
                            downloaded += 1
                    except Exception as e:
                        print(f"  ERROR processing {link.filename}: {e}")
                        failed += 1
        else:
            # Sequential downloads
            print("\nDownloading files sequentially...")
            for link in all_links:
                status, entry_id = self.download_link_threadsafe(link)
                if status == 'downloaded':
                    downloaded += 1
                    if entry_id:
                        entry_ids.append(entry_id)
                elif status == 'skipped':
                    skipped += 1
                elif status == 'failed':
                    failed += 1
                elif status == 'dry-run':
                    downloaded += 1

                self.respect_rate_limit()

        print("\n" + "=" * 60)
        print("Download Summary")
        print("=" * 60)
        print(f"  Downloaded: {downloaded}")
        print(f"  Skipped (already exist): {skipped}")
        print(f"  Failed: {failed}")
        print("=" * 60)

        return {
            'total_found': len(all_links),
            'downloaded': downloaded,
            'skipped': skipped,
            'failed': failed,
            'entry_ids': entry_ids
        }


def parse_date(date_str: str) -> date:
    """Parse date string in YYYY-MM-DD format."""
    try:
        return datetime.strptime(date_str, '%Y-%m-%d').date()
    except ValueError:
        raise ValueError(f"Invalid date format: {date_str}. Use YYYY-MM-DD")


def main():
    """CLI entry point for historical scraper."""
    import argparse

    parser = argparse.ArgumentParser(
        description='Download historical SIPSA data',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python historical.py --year 2024
  python historical.py --year 2024 --month 6
  python historical.py --start-date 2023-01-01 --end-date 2023-12-31
  python historical.py --start-date 2020-03-01 --dry-run

Note: Informes por ciudades are only available from March 2020 onwards.
        """
    )
    parser.add_argument('--start-date', type=str,
                        help='Start date (YYYY-MM-DD format)')
    parser.add_argument('--end-date', type=str,
                        help='End date (YYYY-MM-DD format), defaults to today')
    parser.add_argument('--year', type=int,
                        help='Download entire year')
    parser.add_argument('--month', type=int, choices=range(1, 13),
                        help='Month number (1-12), use with --year')
    parser.add_argument('--dry-run', action='store_true',
                        help='Show what would be downloaded without downloading')
    parser.add_argument('--anexo-only', action='store_true',
                        help='Download only Anexo files')
    parser.add_argument('--informes-only', action='store_true',
                        help='Download only Informes por ciudades files')
    parser.add_argument('--sequential', action='store_true',
                        help='Disable parallel downloads')
    parser.add_argument('--threads', type=int, default=MAX_THREADS,
                        help=f'Number of download threads (default: {MAX_THREADS})')

    args = parser.parse_args()

    # Determine date range
    if args.year:
        if args.month:
            start = date(args.year, args.month, 1)
            if args.month == 12:
                end = date(args.year, 12, 31)
            else:
                end = date(args.year, args.month + 1, 1)
        else:
            start = date(args.year, 1, 1)
            end = date(args.year, 12, 31)
    elif args.start_date:
        start = parse_date(args.start_date)
        end = parse_date(args.end_date) if args.end_date else date.today()
    else:
        parser.error("Please specify either --year or --start-date")

    scraper = HistoricalScraper(
        dry_run=args.dry_run,
        max_threads=args.threads
    )

    result = scraper.run(
        start_date=start,
        end_date=end,
        anexo_only=args.anexo_only,
        informes_only=args.informes_only,
        parallel=not args.sequential
    )

    return 0 if result['failed'] == 0 else 1


if __name__ == "__main__":
    import sys
    sys.exit(main())
