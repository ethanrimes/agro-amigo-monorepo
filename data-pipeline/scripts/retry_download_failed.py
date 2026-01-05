#!/usr/bin/env python3
"""
Retry processing errors with type 'download_failed'.
These are files that exist in storage but failed to download during processing.
"""

import sys
import time
from pathlib import Path
from datetime import datetime, timezone

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.supabase_client import get_db_connection, get_supabase_client, close_connections
from backend.storage import StorageClient
from backend.database import DatabaseClient
from processing.processor import DataProcessor

# Configuration
RETRY_DELAY = 1.0  # seconds between files


def get_download_failed_errors():
    """Get all unresolved processing errors with download_failed type."""
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT pe.*
        FROM processing_errors pe
        LEFT JOIN processed_prices pp ON pe.source_path = pp.source_path
        WHERE pe.resolved = FALSE
          AND pe.error_type = 'download_failed'
          AND pp.id IS NULL
        ORDER BY pe.source_type, pe.created_at
    """)

    return [dict(row) for row in cursor.fetchall()]


def mark_error_resolved(error_id: str):
    """Mark a processing error as resolved."""
    client = get_supabase_client()
    try:
        client.table('processing_errors').update({
            'resolved': True,
            'updated_at': datetime.now(timezone.utc).isoformat()
        }).eq('id', error_id).execute()
        return True
    except Exception as e:
        print(f"  [WARN] Failed to mark error resolved: {e}", flush=True)
        return False


def check_file_exists(storage: StorageClient, storage_path: str) -> bool:
    """Check if file exists in storage."""
    return storage.file_exists(storage_path)


def get_row_date_from_entry(download_entry_id: str):
    """Get row_date from download_entries table."""
    if not download_entry_id:
        return None
    client = get_supabase_client()
    try:
        result = client.table('download_entries').select('row_date').eq('id', download_entry_id).execute()
        if result.data and result.data[0].get('row_date'):
            from datetime import date
            date_str = result.data[0]['row_date']
            return date.fromisoformat(date_str) if isinstance(date_str, str) else date_str
    except Exception as e:
        print(f"  [WARN] Failed to get row_date: {e}", flush=True)
    return None


def retry_processing(error: dict, processor: DataProcessor, storage: StorageClient):
    """
    Retry processing a file that previously failed to download.

    Returns:
        True if successful, False otherwise
    """
    source_path = error['source_path']
    source_type = error.get('source_type', '')
    download_entry_id = error.get('download_entry_id')
    extracted_pdf_id = error.get('extracted_pdf_id')

    print(f"\nRetrying: {source_path}", flush=True)
    print(f"  Type: {source_type}", flush=True)

    # First check if file exists in storage
    if not check_file_exists(storage, source_path):
        print(f"  [SKIP] File does not exist in storage", flush=True)
        return False

    # Get row_date for Excel files
    row_date = get_row_date_from_entry(download_entry_id) if source_type == 'excel' else None

    # Try to process based on type
    try:
        if source_type == 'pdf':
            prices, errors = processor._process_pdf(
                source_path,
                download_entry_id=download_entry_id,
                extracted_pdf_id=extracted_pdf_id
            )
        elif source_type == 'excel':
            prices, errors = processor._process_excel(
                source_path,
                download_entry_id=download_entry_id,
                row_date=row_date
            )
        else:
            print(f"  [SKIP] Unknown source type: {source_type}", flush=True)
            return False

        if prices > 0:
            print(f"  [SUCCESS] Processed {prices} prices", flush=True)
            return True
        elif errors:
            # Check if it's still a download error or a different error
            for err in errors:
                if err.error_type == 'download_failed':
                    print(f"  [FAIL] Still failing to download", flush=True)
                else:
                    print(f"  [PARTIAL] Different error: {err.error_type} - {err.error_message[:50]}", flush=True)
            return False
        else:
            print(f"  [FAIL] No prices extracted", flush=True)
            return False

    except Exception as e:
        print(f"  [ERROR] Exception: {e}", flush=True)
        return False


def main():
    """Main entry point."""
    print("=" * 60, flush=True)
    print("RETRY DOWNLOAD_FAILED PROCESSING ERRORS", flush=True)
    print("=" * 60, flush=True)

    # Get errors to retry
    errors = get_download_failed_errors()
    print(f"\nFound {len(errors)} download_failed errors to retry", flush=True)

    if not errors:
        print("Nothing to retry.", flush=True)
        return

    # Group by type for summary
    by_type = {}
    for e in errors:
        t = e.get('source_type', 'unknown')
        by_type[t] = by_type.get(t, 0) + 1
    print(f"By type: {by_type}", flush=True)

    # Initialize clients
    print("Initializing clients...", flush=True)
    storage = StorageClient()
    processor = DataProcessor()

    # Stats
    success_count = 0
    fail_count = 0
    skip_count = 0

    try:
        for i, error in enumerate(errors):
            print(f"\n[{i + 1}/{len(errors)}]", end="", flush=True)

            success = retry_processing(error, processor, storage)

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
