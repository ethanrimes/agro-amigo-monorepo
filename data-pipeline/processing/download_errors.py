"""
Download files from storage that had processing errors.

Downloads files that have entries in the processing_errors table,
preserving the storage bucket structure in the output directory.
"""

import os
import sys
import argparse
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict

# Add parent directory to path for imports
_parent_dir = str(Path(__file__).parent.parent)
if _parent_dir not in sys.path:
    sys.path.insert(0, _parent_dir)

from backend.supabase_client import get_supabase_client
from backend.storage import StorageClient
from config import STORAGE_BUCKET, EXTRACTED_BUCKET


def get_error_files(
    error_type: Optional[str] = None,
    error_message_contains: Optional[str] = None,
    start_time: Optional[datetime] = None,
    end_time: Optional[datetime] = None,
    resolved: Optional[bool] = None
) -> List[Dict]:
    """
    Query processing errors from database with optional filters.

    Args:
        error_type: Filter by error type (e.g., 'no_prices_extracted', 'corrupted_pdf')
        error_message_contains: Filter by substring in error message
        start_time: Filter errors created after this time
        end_time: Filter errors created before this time
        resolved: Filter by resolved status (True/False/None for all)

    Returns:
        List of error records with source paths and related info
    """
    client = get_supabase_client()

    # Start building query
    query = client.table('processing_errors').select(
        '*',
        count='exact'
    )

    # Apply filters
    if error_type:
        query = query.eq('error_type', error_type)

    if resolved is not None:
        query = query.eq('resolved', resolved)

    if start_time:
        query = query.gte('created_at', start_time.isoformat())

    if end_time:
        query = query.lte('created_at', end_time.isoformat())

    # Execute query
    response = query.execute()
    errors = response.data or []

    # Filter by error message if specified (Supabase doesn't support LIKE easily)
    if error_message_contains:
        errors = [
            e for e in errors
            if error_message_contains.lower() in (e.get('error_message') or '').lower()
        ]

    return errors


def download_error_files(
    output_dir: str,
    error_type: Optional[str] = None,
    error_message_contains: Optional[str] = None,
    start_time: Optional[datetime] = None,
    end_time: Optional[datetime] = None,
    resolved: Optional[bool] = None,
    dry_run: bool = False
) -> Dict:
    """
    Download files that had processing errors.

    Args:
        output_dir: Output directory (required)
        error_type: Filter by error type
        error_message_contains: Filter by substring in error message
        start_time: Filter errors created after this time
        end_time: Filter errors created before this time
        resolved: Filter by resolved status
        dry_run: If True, just list files without downloading

    Returns:
        Summary dict with counts
    """
    print("=" * 60)
    print("Download Error Files")
    print("=" * 60)

    # Get errors from database
    errors = get_error_files(
        error_type=error_type,
        error_message_contains=error_message_contains,
        start_time=start_time,
        end_time=end_time,
        resolved=resolved
    )

    print(f"Found {len(errors)} error records")

    if not errors:
        return {'total': 0, 'downloaded': 0, 'failed': 0, 'skipped': 0}

    # Collect unique source paths
    paths_to_download = {}
    for error in errors:
        source_path = error.get('source_path')
        if source_path and source_path not in paths_to_download:
            # Determine which bucket this file is in
            if source_path.startswith('extracted/'):
                bucket = EXTRACTED_BUCKET
            else:
                bucket = STORAGE_BUCKET

            paths_to_download[source_path] = {
                'bucket': bucket,
                'error_type': error.get('error_type'),
                'error_message': error.get('error_message'),
                'created_at': error.get('created_at')
            }

    print(f"Unique files to download: {len(paths_to_download)}")

    if dry_run:
        print("\n[DRY-RUN] Files that would be downloaded:")
        for path, info in paths_to_download.items():
            print(f"  [{info['bucket']}] {path}")
            print(f"    Error: {info['error_type']}")
        return {
            'total': len(paths_to_download),
            'downloaded': 0,
            'failed': 0,
            'skipped': len(paths_to_download)
        }

    # Create output directory
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    # Initialize storage clients for both buckets
    storage_clients = {
        STORAGE_BUCKET: StorageClient(bucket_name=STORAGE_BUCKET),
        EXTRACTED_BUCKET: StorageClient(bucket_name=EXTRACTED_BUCKET)
    }

    downloaded = 0
    failed = 0

    print(f"\nDownloading to: {output_path.absolute()}")
    print("-" * 60)

    for source_path, info in paths_to_download.items():
        bucket = info['bucket']
        local_path = output_path / source_path

        # Create parent directories preserving bucket structure
        local_path.parent.mkdir(parents=True, exist_ok=True)

        try:
            storage = storage_clients[bucket]
            success = storage.download_to_file(source_path, str(local_path))

            if success:
                downloaded += 1
                print(f"  [OK] {source_path}")
            else:
                failed += 1
                print(f"  [FAIL] {source_path} - download failed")

        except Exception as e:
            failed += 1
            print(f"  [FAIL] {source_path} - {e}")

    # Summary
    print("\n" + "=" * 60)
    print("Download Summary")
    print("=" * 60)
    print(f"  Total files: {len(paths_to_download)}")
    print(f"  Downloaded: {downloaded}")
    print(f"  Failed: {failed}")
    print(f"  Output: {output_path.absolute()}")
    print("=" * 60)

    return {
        'total': len(paths_to_download),
        'downloaded': downloaded,
        'failed': failed,
        'skipped': 0
    }


def list_error_types() -> List[str]:
    """Get list of all error types in the database."""
    client = get_supabase_client()

    response = client.table('processing_errors').select('error_type').execute()

    types = set()
    for record in response.data or []:
        if record.get('error_type'):
            types.add(record['error_type'])

    return sorted(types)


def main():
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description='Download files from storage that had processing errors',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Download all error files to ./error_files
  python download_errors.py --output ./error_files

  # Download only files with 'no_prices_extracted' errors
  python download_errors.py --output ./error_files --error-type no_prices_extracted

  # Download errors from a specific time range
  python download_errors.py --output ./error_files --start-time "2025-01-01 00:00:00"

  # Download errors containing specific message
  python download_errors.py --output ./error_files --error-message "corrupted"

  # Dry run to see what would be downloaded
  python download_errors.py --output ./error_files --dry-run

  # List available error types
  python download_errors.py --list-error-types
        """
    )

    parser.add_argument(
        '--output', '-o',
        type=str,
        help='Output directory (required unless using --list-error-types)'
    )
    parser.add_argument(
        '--error-type', '-t',
        type=str,
        help='Filter by error type (e.g., no_prices_extracted, corrupted_pdf)'
    )
    parser.add_argument(
        '--error-message', '-m',
        type=str,
        help='Filter by substring in error message'
    )
    parser.add_argument(
        '--start-time',
        type=str,
        help='Filter errors created after this time (YYYY-MM-DD HH:MM:SS)'
    )
    parser.add_argument(
        '--end-time',
        type=str,
        help='Filter errors created before this time (YYYY-MM-DD HH:MM:SS)'
    )
    parser.add_argument(
        '--resolved',
        choices=['true', 'false'],
        help='Filter by resolved status'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='List files without downloading'
    )
    parser.add_argument(
        '--list-error-types',
        action='store_true',
        help='List all error types in the database'
    )

    args = parser.parse_args()

    # Handle list-error-types
    if args.list_error_types:
        types = list_error_types()
        print("Available error types:")
        for t in types:
            print(f"  - {t}")
        return 0

    # Validate output is provided
    if not args.output:
        parser.error("--output is required unless using --list-error-types")

    # Parse time arguments
    start_time = None
    end_time = None

    if args.start_time:
        try:
            start_time = datetime.strptime(args.start_time, '%Y-%m-%d %H:%M:%S')
        except ValueError:
            try:
                start_time = datetime.strptime(args.start_time, '%Y-%m-%d')
            except ValueError:
                parser.error("Invalid start-time format. Use 'YYYY-MM-DD' or 'YYYY-MM-DD HH:MM:SS'")

    if args.end_time:
        try:
            end_time = datetime.strptime(args.end_time, '%Y-%m-%d %H:%M:%S')
        except ValueError:
            try:
                end_time = datetime.strptime(args.end_time, '%Y-%m-%d')
            except ValueError:
                parser.error("Invalid end-time format. Use 'YYYY-MM-DD' or 'YYYY-MM-DD HH:MM:SS'")

    # Parse resolved
    resolved = None
    if args.resolved:
        resolved = args.resolved.lower() == 'true'

    # Run download
    result = download_error_files(
        output_dir=args.output,
        error_type=args.error_type,
        error_message_contains=args.error_message,
        start_time=start_time,
        end_time=end_time,
        resolved=resolved,
        dry_run=args.dry_run
    )

    return 0 if result['failed'] == 0 else 1


if __name__ == '__main__':
    sys.exit(main())
