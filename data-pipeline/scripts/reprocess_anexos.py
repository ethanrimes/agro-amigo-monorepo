#!/usr/bin/env python3
"""
Script to reprocess specific anexo files after processing corrections.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from backend.supabase_client import get_supabase_client
from processing.processor import DataProcessor

# Dates extracted from the tree structure of anexo files to reprocess
DATES_TO_REPROCESS = [
    "2012-09-05",
    "2012-09-21",
    "2012-10-05",
    "2012-10-10",
    "2012-10-11",
    "2012-10-12",
    "2012-10-30",
    "2013-09-18",
    "2013-10-10",
    "2013-10-11",
    "2013-11-13",
    "2014-01-15",
    "2014-04-21",
    "2014-05-27",
    "2014-07-03",
    "2014-11-10",
    "2014-11-11",
    "2015-03-17",
    "2015-03-31",
    "2016-11-23",
    "2017-05-26",
    "2017-10-05",
]


def reprocess_anexos(dry_run: bool = False):
    """Reprocess anexo files for the specified dates."""
    client = get_supabase_client()

    print("=" * 60)
    print("Reprocessing Anexo Files")
    print("=" * 60)
    print(f"Dates to reprocess: {len(DATES_TO_REPROCESS)}")
    if dry_run:
        print("[DRY-RUN MODE]")
    print()

    total_entries = 0
    total_prices_deleted = 0
    entry_ids = []

    for date_str in DATES_TO_REPROCESS:
        print(f"\n[{date_str}]")

        # Find download entries for this date with file_type='excel'
        response = client.table('download_entries').select('id, row_name, storage_path').eq(
            'row_date', date_str
        ).eq('file_type', 'excel').execute()

        entries = response.data or []

        if not entries:
            print(f"  No anexo entries found")
            continue

        for entry in entries:
            entry_id = entry['id']
            print(f"  Found: {entry['row_name']}")
            print(f"    ID: {entry_id}")
            print(f"    Path: {entry['storage_path']}")

            # Count existing prices for this entry
            price_count_resp = client.table('processed_prices').select(
                'id', count='exact'
            ).eq('download_entry_id', entry_id).limit(1).execute()

            price_count = price_count_resp.count or 0
            print(f"    Existing prices: {price_count}")

            if not dry_run:
                # Delete existing processed_prices for this entry
                if price_count > 0:
                    client.table('processed_prices').delete().eq(
                        'download_entry_id', entry_id
                    ).execute()
                    print(f"    Deleted {price_count} prices")
                    total_prices_deleted += price_count

                # Reset processed_status to false
                client.table('download_entries').update({
                    'processed_status': False
                }).eq('id', entry_id).execute()
                print(f"    Reset processed_status to false")

                # Mark any related processing errors as resolved
                client.table('processing_errors').update({
                    'resolved': True
                }).eq('download_entry_id', entry_id).execute()

            entry_ids.append(entry_id)
            total_entries += 1

    print("\n" + "=" * 60)
    print(f"Summary: Found {total_entries} anexo entries to reprocess")
    print(f"Total prices deleted: {total_prices_deleted}")
    print("=" * 60)

    if dry_run:
        print("\n[DRY-RUN] No changes made. Run without --dry-run to apply changes.")
        return

    if not entry_ids:
        print("\nNo entries to reprocess.")
        return

    # Now reprocess the entries
    print("\n" + "=" * 60)
    print("Running Processor")
    print("=" * 60)

    processor = DataProcessor(max_threads=4)
    result = processor.process_all_pending(parallel=True)

    print("\n" + "=" * 60)
    print("Final Results")
    print("=" * 60)
    print(f"  Entries processed: {result['total']}")
    print(f"  Successful: {result['success']}")
    print(f"  Failed: {result['failed']}")
    print(f"  Prices extracted: {result['prices_extracted']}")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description='Reprocess specific anexo files')
    parser.add_argument('--dry-run', action='store_true', help='Preview without changes')
    args = parser.parse_args()

    reprocess_anexos(dry_run=args.dry_run)
