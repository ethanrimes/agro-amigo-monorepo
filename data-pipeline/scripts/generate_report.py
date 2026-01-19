#!/usr/bin/env python3
"""
Generate error report from database with downloadable file links.

Usage:
    python scripts/generate_report.py                    # All errors
    python scripts/generate_report.py --recent 24       # Last 24 hours only
    python scripts/generate_report.py --output report.md # Custom output path
"""

import argparse
import os
import sys
from pathlib import Path
from datetime import datetime, timezone, timedelta

sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.supabase_client import get_db_connection, close_connections
from config import STORAGE_BUCKET

# Error types to exclude (transient/retryable errors)
TRANSIENT_ERROR_TYPES = {
    'upload_transient',
    'upload_duplicate',
    'database_error',
    'processing_failed',  # Usually transient network errors
}

# Error messages that indicate transient issues or already processed (case-insensitive check)
TRANSIENT_ERROR_MESSAGES = [
    'errno 35',
    'resource temporarily unavailable',
    'rate limit',
    'too many requests',
    'connection reset',
    'connection refused',
    'timeout',
    'network connection lost',
    'gateway error',
    'already processed',
    'already exists',
    'duplicate',
]


def get_storage_base_url():
    """Get the Supabase storage base URL."""
    supabase_url = os.getenv("SUPABASE_URL", "")
    if supabase_url:
        return f"{supabase_url}/storage/v1/object/public"
    return None


def is_transient_error(error_type: str, error_message: str) -> bool:
    """Check if an error is transient and should be excluded."""
    if error_type in TRANSIENT_ERROR_TYPES:
        return True

    msg_lower = (error_message or '').lower()
    return any(t in msg_lower for t in TRANSIENT_ERROR_MESSAGES)


def get_errors(hours_ago: int = None):
    """Get errors from database, optionally filtered by time."""
    conn = get_db_connection()
    cursor = conn.cursor()

    time_filter = ""
    if hours_ago:
        cutoff = datetime.now(timezone.utc) - timedelta(hours=hours_ago)
        time_filter = f"AND created_at >= '{cutoff.isoformat()}'"

    results = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "hours_filter": hours_ago,
        "storage_base_url": get_storage_base_url(),
        "download_errors": [],
        "processing_errors": [],
    }

    # Download errors - get full URL for downloading
    cursor.execute(f"""
        SELECT de.error_type, de.download_url, de.error_code, de.error_message,
               de.file_type, de.retry_count, de.created_at, de.source_page
        FROM download_errors de
        LEFT JOIN download_entries dn ON de.download_url = dn.download_link
        WHERE de.resolved = FALSE AND dn.id IS NULL
              {time_filter.replace('created_at', 'de.created_at')}
        ORDER BY de.error_type, de.created_at DESC
    """)

    for row in cursor.fetchall():
        row_dict = dict(row)
        # Filter out transient errors
        if not is_transient_error(row_dict.get('error_type', ''), row_dict.get('error_message', '')):
            results["download_errors"].append(row_dict)

    # Processing errors - join with download_entries and extracted_pdfs to get storage paths
    cursor.execute(f"""
        SELECT pe.error_type, pe.source_path, pe.source_type, pe.error_message,
               pe.retry_count, pe.created_at, pe.download_entry_id, pe.extracted_pdf_id,
               de.storage_path as download_storage_path, de.download_link,
               ep.storage_path as extracted_storage_path, ep.pdf_filename
        FROM processing_errors pe
        LEFT JOIN download_entries de ON pe.download_entry_id = de.id
        LEFT JOIN extracted_pdfs ep ON pe.extracted_pdf_id = ep.id
        LEFT JOIN processed_prices pp ON pe.source_path = pp.source_path
        WHERE pe.resolved = FALSE AND pp.id IS NULL
              {time_filter.replace('created_at', 'pe.created_at')}
        ORDER BY pe.error_type, pe.created_at DESC
    """)

    for row in cursor.fetchall():
        row_dict = dict(row)
        # Filter out transient errors
        if not is_transient_error(row_dict.get('error_type', ''), row_dict.get('error_message', '')):
            results["processing_errors"].append(row_dict)

    return results


def generate_report(results: dict) -> str:
    """Generate markdown report from results with file links."""
    lines = []
    storage_base = results.get('storage_base_url')

    time_note = f" (last {results['hours_filter']} hours)" if results['hours_filter'] else ""
    lines.append(f"# Pipeline Error Report{time_note}")
    lines.append(f"\n**Generated:** {results['generated_at']}")
    lines.append("\n> Note: Transient errors (network issues, rate limits) and 'already processed' errors are excluded from this report.")

    # Summary
    lines.append("\n## Summary\n")
    lines.append("| Category | Count |")
    lines.append("|----------|------:|")
    lines.append(f"| Download Errors | {len(results['download_errors'])} |")
    lines.append(f"| Processing Errors | {len(results['processing_errors'])} |")

    # Download Errors
    if results['download_errors']:
        lines.append("\n## Download Errors\n")
        lines.append("These files failed to download from the DANE website.\n")

        by_type = {}
        for err in results['download_errors']:
            etype = err.get('error_type', 'unknown')
            by_type.setdefault(etype, []).append(err)

        for etype, errors in sorted(by_type.items(), key=lambda x: -len(x[1])):
            lines.append(f"\n### {etype} ({len(errors)})\n")
            lines.append("| File | Error | Source Link |")
            lines.append("|------|-------|-------------|")

            for err in errors[:50]:  # Limit to 50 per type
                url = err.get('download_url', '')
                filename = url.split('/')[-1] if url else 'N/A'
                msg = (err.get('error_message', '') or '')[:80].replace('|', '\\|')
                source = err.get('source_page', '')

                # Create clickable link to source file
                if url:
                    file_link = f"[{filename}]({url})"
                else:
                    file_link = filename

                source_link = f"[source]({source})" if source else "-"
                lines.append(f"| {file_link} | {msg} | {source_link} |")

            if len(errors) > 50:
                lines.append(f"\n*... and {len(errors) - 50} more errors of this type*")

    # Processing Errors
    if results['processing_errors']:
        lines.append("\n## Processing Errors\n")
        lines.append("These files were downloaded but failed during processing.\n")

        by_type = {}
        for err in results['processing_errors']:
            etype = err.get('error_type', 'unknown')
            by_type.setdefault(etype, []).append(err)

        for etype, errors in sorted(by_type.items(), key=lambda x: -len(x[1])):
            lines.append(f"\n### {etype} ({len(errors)})\n")

            # Add description for each error type
            descriptions = {
                'missing_category': 'Product name could not be mapped to a category.',
                'no_prices_extracted': 'File was processed but no price data was found.',
                'unused_stack_items': 'PDF parser had leftover text that could not be matched.',
                'missing_location': 'Could not extract city/market name from the file.',
                'excel_parse_error': 'Excel file format could not be parsed.',
                'download_failed': 'File could not be downloaded from storage.',
                'invalid_city_headers': 'PDF table headers could not be parsed.',
            }
            if etype in descriptions:
                lines.append(f"*{descriptions[etype]}*\n")

            lines.append("| File | Storage Path | Error |")
            lines.append("|------|--------------|-------|")

            for err in errors[:50]:
                source_path = err.get('source_path', '')
                filename = source_path.split('/')[-1] if source_path else 'N/A'
                msg = (err.get('error_message', '') or '')[:100].replace('|', '\\|').replace('\n', ' ')

                # Get storage path for download link
                storage_path = err.get('extracted_storage_path') or err.get('download_storage_path') or source_path

                # Create clickable link if we have storage base URL
                if storage_base and storage_path:
                    full_url = f"{storage_base}/{STORAGE_BUCKET}/{storage_path}"
                    file_link = f"[{filename}]({full_url})"
                    path_display = f"`{storage_path[:50]}...`" if len(storage_path) > 50 else f"`{storage_path}`"
                else:
                    file_link = f"`{filename}`"
                    path_display = f"`{source_path[:50]}...`" if source_path and len(source_path) > 50 else f"`{source_path or 'N/A'}`"

                lines.append(f"| {file_link} | {path_display} | {msg[:80]} |")

            if len(errors) > 50:
                lines.append(f"\n*... and {len(errors) - 50} more errors of this type*")

    if not any([results['download_errors'], results['processing_errors']]):
        lines.append("\n**No errors found (excluding transient errors).**")

    # Add instructions
    lines.append("\n---\n")
    lines.append("## How to Investigate\n")
    lines.append("1. Click on file links to download and inspect the problematic files")
    lines.append("2. For **download errors**: The file may not exist on DANE's website")
    lines.append("3. For **processing errors**: Download the file and check its format")
    lines.append("4. Use `python -m cli.main download-errors -o ./error_files` to batch download files with errors")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description='Generate pipeline error report')
    parser.add_argument('--recent', type=int, metavar='HOURS',
                        help='Only include errors from last N hours')
    parser.add_argument('--output', '-o', type=str, default='exports/error_report.md',
                        help='Output file path (default: exports/error_report.md)')
    args = parser.parse_args()

    try:
        print("Querying database for errors (excluding transient errors)...")
        results = get_errors(hours_ago=args.recent)

        print(f"Found:")
        print(f"  - {len(results['download_errors'])} download errors")
        print(f"  - {len(results['processing_errors'])} processing errors")

        report = generate_report(results)

        output_path = Path(__file__).parent.parent / args.output
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(report)

        print(f"\nReport saved to: {output_path}")

    finally:
        close_connections()


if __name__ == "__main__":
    main()
