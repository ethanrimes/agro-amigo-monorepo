#!/usr/bin/env python3
"""
Test script to run the Excel parser on downloaded error files.
"""

import os
import sys
from pathlib import Path
from datetime import datetime, date

# Add current directory to import excel_parser directly
sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent.parent))

# Import directly from file to avoid __init__.py importing pdf_parser
import importlib.util
spec = importlib.util.spec_from_file_location("excel_parser", Path(__file__).parent / "excel_parser.py")
excel_parser_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(excel_parser_module)
ExcelParser = excel_parser_module.ExcelParser


def extract_date_from_path(filepath: str) -> date:
    """Extract date from the directory path structure (YYYY/MM/DD)."""
    parts = Path(filepath).parts
    for i, part in enumerate(parts):
        if part.isdigit() and len(part) == 4 and int(part) > 2000:
            # Found year
            year = int(part)
            if i + 2 < len(parts):
                month = int(parts[i + 1])
                day = int(parts[i + 2])
                return date(year, month, day)
    return None


def test_file(filepath: str) -> dict:
    """Test parsing a single Excel file."""
    row_date = extract_date_from_path(filepath)

    parser = ExcelParser(download_entry_id=None, row_date=row_date)

    try:
        result = parser.parse(filepath, filepath)
        return {
            'file': filepath,
            'success': len(result.prices) > 0,
            'prices_count': len(result.prices),
            'errors_count': len(result.errors),
            'cities': result.cities,
            'date_used': result.date,
            'row_date_from_path': row_date,
            'errors': [e.error_type + ': ' + e.error_message[:100] for e in result.errors]
        }
    except Exception as e:
        return {
            'file': filepath,
            'success': False,
            'prices_count': 0,
            'errors_count': 1,
            'cities': [],
            'date_used': None,
            'row_date_from_path': row_date,
            'errors': [f'Exception: {str(e)[:200]}']
        }


def test_directory(base_dir: str) -> list:
    """Test all Excel files in a directory tree."""
    results = []

    for root, dirs, files in os.walk(base_dir):
        # Skip temp files
        dirs[:] = [d for d in dirs if not d.startswith('.')]

        for filename in files:
            if filename.endswith(('.xls', '.xlsx')) and not filename.startswith('~$'):
                filepath = os.path.join(root, filename)
                result = test_file(filepath)
                results.append(result)

    return results


def print_results(results: list, title: str):
    """Print test results in a formatted way."""
    print("\n" + "=" * 70)
    print(title)
    print("=" * 70)

    success = [r for r in results if r['success']]
    failed = [r for r in results if not r['success']]

    print(f"\nTotal files: {len(results)}")
    print(f"Success: {len(success)}")
    print(f"Failed: {len(failed)}")

    print("\n" + "-" * 70)
    print("SUCCESSFUL FILES:")
    print("-" * 70)
    for r in success:
        rel_path = r['file'].split('anexo/')[-1] if 'anexo/' in r['file'] else r['file']
        print(f"  [OK] {rel_path}")
        print(f"       Prices: {r['prices_count']}, Cities: {len(r['cities'])}, Date: {r['date_used']}")
        if r['cities']:
            print(f"       Cities found: {', '.join(r['cities'][:5])}{'...' if len(r['cities']) > 5 else ''}")

    print("\n" + "-" * 70)
    print("FAILED FILES:")
    print("-" * 70)
    for r in failed:
        rel_path = r['file'].split('anexo/')[-1] if 'anexo/' in r['file'] else r['file']
        print(f"  [FAIL] {rel_path}")
        print(f"         Row date from path: {r['row_date_from_path']}")
        for err in r['errors'][:3]:
            print(f"         Error: {err}")

    return success, failed


def main():
    # Base directory where error files are downloaded
    base_dirs = [
        "/Users/ethan/Documents/AgroAmigo/processing_errors/excel_parse_error",
        "/Users/ethan/Documents/AgroAmigo/processing_errors/missing_date",
    ]

    all_success = []
    all_failed = []

    for base_dir in base_dirs:
        if os.path.exists(base_dir):
            error_type = os.path.basename(base_dir)
            results = test_directory(base_dir)
            success, failed = print_results(results, f"Testing {error_type} files")
            all_success.extend(success)
            all_failed.extend(failed)
        else:
            print(f"Directory not found: {base_dir}")

    # Summary
    print("\n" + "=" * 70)
    print("OVERALL SUMMARY")
    print("=" * 70)
    print(f"Total files tested: {len(all_success) + len(all_failed)}")
    print(f"Total successful: {len(all_success)}")
    print(f"Total failed: {len(all_failed)}")

    if all_success:
        total_prices = sum(r['prices_count'] for r in all_success)
        print(f"Total prices extracted: {total_prices}")


if __name__ == '__main__':
    main()
