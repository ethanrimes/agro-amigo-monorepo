#!/usr/bin/env python3
"""
Retry downloads that failed with [Errno 35] Resource temporarily unavailable.
These are transient errors that may succeed on retry.
"""

import sys
import time
from pathlib import Path
from datetime import datetime, timezone

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.supabase_client import get_db_connection, get_supabase_client, close_connections
from backend.storage import StorageClient
from backend.database import DatabaseClient, DownloadEntry
from scraping.scraper_base import ScraperBase

# Configuration
RETRY_DELAY = 2.0  # seconds between retries
MAX_BATCH_RETRIES = 3  # retries per file


def get_transient_upload_errors():
    """Get all unresolved transient upload errors (Errno 35, etc.)."""
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT de.*
        FROM download_errors de
        LEFT JOIN download_entries dn ON de.download_url = dn.download_link
        WHERE de.resolved = FALSE
          AND de.error_type = 'upload_transient'
          AND dn.id IS NULL
        ORDER BY de.created_at
    """)

    return [dict(row) for row in cursor.fetchall()]


def mark_error_resolved(error_id: str):
    """Mark a download error as resolved."""
    client = get_supabase_client()
    try:
        client.table('download_errors').update({
            'resolved': True,
            'updated_at': datetime.now(timezone.utc).isoformat()
        }).eq('id', error_id).execute()
        return True
    except Exception as e:
        print(f"  [WARN] Failed to mark error resolved: {e}")
        return False


def extract_date_from_filename(url: str):
    """
    Extract date from URL/filename with additional patterns.
    Handles sipsa-DD-MM-YYYY format that the base scraper doesn't.
    """
    import re
    from datetime import datetime

    url_lower = url.lower()

    # sipsa-DD-MM-YYYY format (e.g., sipsa-24-06-2020.zip)
    pattern = re.search(r'sipsa-(\d{2})-(\d{2})-(\d{4})', url_lower)
    if pattern:
        day, month, year = pattern.groups()
        try:
            return datetime(int(year), int(month), int(day))
        except ValueError:
            pass

    return None


def retry_download(error: dict, scraper: ScraperBase, storage: StorageClient, db: DatabaseClient):
    """
    Retry downloading and uploading a file.

    Returns:
        True if successful, False otherwise
    """
    url = error['download_url']
    source_page = error.get('source_page', '')
    file_type = error.get('file_type', '')
    filename = url.split('/')[-1]

    print(f"\nRetrying: {filename}", flush=True)
    print(f"  URL: {url}", flush=True)

    # Try to download the file
    for attempt in range(MAX_BATCH_RETRIES):
        try:
            response = scraper._request_with_retry(url, stream=True)

            if response is None:
                print(f"  [FAIL] Download failed (attempt {attempt + 1}/{MAX_BATCH_RETRIES})", flush=True)
                time.sleep(RETRY_DELAY)
                continue

            file_data = response.content
            print(f"  Downloaded {len(file_data)} bytes", flush=True)

            # Extract date from URL for storage path - try our custom parser first
            file_date = extract_date_from_filename(url)
            if not file_date:
                file_date = scraper.extract_date_from_url(url)

            # Skip if we can't parse the date (row_date is NOT NULL in DB)
            if not file_date:
                print(f"  [SKIP] Cannot parse date from URL, skipping", flush=True)
                return False

            # Generate storage path
            if file_date:
                category = scraper.get_link_category(url, '') or file_type
                storage_path = storage.generate_storage_path(
                    file_date,
                    category,
                    filename
                )
            else:
                storage_path = f"unknown_date/{file_type}/{filename}"

            # Get content type
            content_types = {
                'pdf': 'application/pdf',
                'excel': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                'zip': 'application/zip'
            }
            content_type = content_types.get(file_type, 'application/octet-stream')

            # Try to upload
            print(f"  Uploading to: {storage_path}", flush=True)
            upload_result = storage.upload_file(file_data, storage_path, content_type)

            if not upload_result.get('success'):
                error_msg = upload_result.get('error', 'Unknown error')
                # Check if it's a duplicate error - that means file already exists
                if '409' in str(error_msg) or 'Duplicate' in str(error_msg):
                    print(f"  [INFO] File already exists in storage, creating DB entry", flush=True)
                else:
                    print(f"  [FAIL] Upload failed: {error_msg}", flush=True)
                    time.sleep(RETRY_DELAY)
                    continue

            # Create download entry
            entry = DownloadEntry(
                row_name=filename,
                row_date=file_date.date() if file_date else None,
                download_link=url,
                source_table_link=source_page,
                storage_path=storage_path,
                file_type=file_type
            )

            entry_id = db.create_download_entry(entry)

            if entry_id:
                print(f"  [SUCCESS] Created entry: {entry_id}", flush=True)
                return True
            else:
                print(f"  [FAIL] Failed to create database entry", flush=True)
                time.sleep(RETRY_DELAY)
                continue

        except Exception as e:
            print(f"  [ERROR] Exception (attempt {attempt + 1}): {e}", flush=True)
            time.sleep(RETRY_DELAY)
            continue

    return False


def main():
    """Main entry point."""
    print("=" * 60, flush=True)
    print("RETRY TRANSIENT UPLOAD ERRORS", flush=True)
    print("=" * 60, flush=True)

    # Get errors to retry
    errors = get_transient_upload_errors()
    print(f"\nFound {len(errors)} transient upload errors to retry", flush=True)

    if not errors:
        print("Nothing to retry.", flush=True)
        return

    # Initialize clients
    print("Initializing clients...", flush=True)
    scraper = ScraperBase(dry_run=False)
    storage = StorageClient()
    db = DatabaseClient()

    # Stats
    success_count = 0
    fail_count = 0

    try:
        for i, error in enumerate(errors):
            print(f"\n[{i + 1}/{len(errors)}]", end="", flush=True)

            success = retry_download(error, scraper, storage, db)

            if success:
                mark_error_resolved(error['id'])
                success_count += 1
            else:
                fail_count += 1

            # Rate limiting
            time.sleep(RETRY_DELAY)

    except KeyboardInterrupt:
        print("\n\nInterrupted by user.", flush=True)

    finally:
        close_connections()

    # Summary
    print("\n" + "=" * 60, flush=True)
    print("SUMMARY", flush=True)
    print("=" * 60, flush=True)
    print(f"Total attempted: {success_count + fail_count}", flush=True)
    print(f"Successful:      {success_count}", flush=True)
    print(f"Failed:          {fail_count}", flush=True)
    print(f"Remaining:       {len(errors) - success_count - fail_count}", flush=True)


if __name__ == "__main__":
    main()
