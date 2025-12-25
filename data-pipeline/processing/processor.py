"""
Main data processor for orchestrating SIPSA file processing.

Handles the complete processing workflow:
1. Get unprocessed download entries
2. For each entry:
   - If ZIP: extract PDFs, process each
   - If PDF: process directly
   - If Excel: process directly
3. Store results and update status
"""

import os
import tempfile
from datetime import datetime
from typing import Optional, List, Dict, Tuple
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass

import sys
from pathlib import Path

_parent_dir = str(Path(__file__).parent.parent)
if _parent_dir not in sys.path:
    sys.path.insert(0, _parent_dir)

from config import MAX_THREADS
from backend.storage import StorageClient
from backend.database import DatabaseClient, ProcessedPrice, ProcessingError
from processing.pdf_parser import PDFParser
from processing.excel_parser import ExcelParser
from processing.zip_handler import ZIPHandler


@dataclass
class ProcessingResult:
    """Result of processing a download entry."""
    entry_id: str
    prices_extracted: int
    errors_count: int
    success: bool


class DataProcessor:
    """Orchestrates the processing of SIPSA data files."""

    def __init__(self, max_threads: int = MAX_THREADS):
        """
        Initialize the data processor.

        Args:
            max_threads: Maximum threads for parallel processing
        """
        self.max_threads = max_threads
        self.storage = StorageClient()
        self.database = DatabaseClient()

    def process_all_pending(self, parallel: bool = True) -> Dict:
        """
        Process all pending download entries.

        Args:
            parallel: Use multithreading

        Returns:
            Summary dict with counts
        """
        print("=" * 60)
        print("SIPSA Data Processor")
        print("=" * 60)

        # Get unprocessed entries
        entries = self.database.get_unprocessed_download_entries()
        print(f"Found {len(entries)} unprocessed entries")

        if not entries:
            return {
                'total': 0,
                'success': 0,
                'failed': 0,
                'prices_extracted': 0,
                'errors_logged': 0
            }

        results = []

        if parallel and len(entries) > 1:
            print(f"Processing in parallel ({self.max_threads} threads)...")
            with ThreadPoolExecutor(max_workers=self.max_threads) as executor:
                futures = {
                    executor.submit(self._process_entry, entry): entry
                    for entry in entries
                }

                for future in as_completed(futures):
                    try:
                        result = future.result()
                        results.append(result)
                    except Exception as e:
                        entry = futures[future]
                        print(f"  [ERROR] Failed to process {entry['id']}: {e}")
                        results.append(ProcessingResult(
                            entry_id=entry['id'],
                            prices_extracted=0,
                            errors_count=1,
                            success=False
                        ))
        else:
            print("Processing sequentially...")
            for entry in entries:
                try:
                    result = self._process_entry(entry)
                    results.append(result)
                except Exception as e:
                    print(f"  [ERROR] Failed to process {entry['id']}: {e}")
                    results.append(ProcessingResult(
                        entry_id=entry['id'],
                        prices_extracted=0,
                        errors_count=1,
                        success=False
                    ))

        # Summarize results
        success_count = sum(1 for r in results if r.success)
        failed_count = sum(1 for r in results if not r.success)
        total_prices = sum(r.prices_extracted for r in results)
        total_errors = sum(r.errors_count for r in results)

        print("\n" + "=" * 60)
        print("Processing Summary")
        print("=" * 60)
        print(f"  Entries processed: {len(results)}")
        print(f"  Successful: {success_count}")
        print(f"  Failed: {failed_count}")
        print(f"  Total prices extracted: {total_prices}")
        print(f"  Errors logged: {total_errors}")
        print("=" * 60)

        return {
            'total': len(results),
            'success': success_count,
            'failed': failed_count,
            'prices_extracted': total_prices,
            'errors_logged': total_errors
        }

    def process_entry(self, entry_id: str) -> ProcessingResult:
        """
        Process a specific download entry by ID.

        Args:
            entry_id: ID of the download entry

        Returns:
            ProcessingResult
        """
        # Get entry from database
        entries = self.database.get_unprocessed_download_entries()
        entry = next((e for e in entries if e['id'] == entry_id), None)

        if not entry:
            # Try to get it even if processed
            from backend.supabase_client import get_supabase_client
            client = get_supabase_client()
            response = client.table('download_entries').select('*').eq('id', entry_id).execute()
            if response.data:
                entry = response.data[0]
            else:
                raise ValueError(f"Download entry not found: {entry_id}")

        return self._process_entry(entry)

    def process_by_date(self, target_date: str) -> Dict:
        """
        Process all entries for a specific date.

        Args:
            target_date: Date in YYYY-MM-DD format

        Returns:
            Summary dict
        """
        from backend.supabase_client import get_supabase_client
        client = get_supabase_client()

        response = client.table('download_entries').select('*').eq(
            'row_date', target_date
        ).execute()

        entries = response.data or []

        if not entries:
            print(f"No entries found for date: {target_date}")
            return {'total': 0}

        results = []
        for entry in entries:
            try:
                result = self._process_entry(entry)
                results.append(result)
            except Exception as e:
                print(f"  [ERROR] {e}")
                results.append(ProcessingResult(
                    entry_id=entry['id'],
                    prices_extracted=0,
                    errors_count=1,
                    success=False
                ))

        return {
            'total': len(results),
            'success': sum(1 for r in results if r.success),
            'failed': sum(1 for r in results if not r.success),
            'prices_extracted': sum(r.prices_extracted for r in results)
        }

    def _process_entry(self, entry: dict) -> ProcessingResult:
        """
        Process a single download entry.

        Args:
            entry: Download entry dict

        Returns:
            ProcessingResult
        """
        entry_id = entry['id']
        file_type = entry['file_type']
        storage_path = entry['storage_path']

        print(f"\n[Processing] {entry['row_name']} ({file_type})")

        total_prices = 0
        total_errors = 0
        all_errors = []
        success = True

        try:
            if file_type == 'zip':
                # Extract and process PDFs from ZIP
                prices, errors = self._process_zip(entry_id, storage_path)
                total_prices = prices
                total_errors = len(errors)
                all_errors.extend(errors)

            elif file_type == 'pdf':
                # Process single PDF directly
                prices, errors = self._process_pdf(
                    storage_path,
                    download_entry_id=entry_id
                )
                total_prices = prices
                total_errors = len(errors)
                all_errors.extend(errors)

            elif file_type == 'excel':
                # Process Excel file
                prices, errors = self._process_excel(
                    storage_path,
                    download_entry_id=entry_id
                )
                total_prices = prices
                total_errors = len(errors)
                all_errors.extend(errors)

            # Log errors to database
            for error in all_errors:
                self.database.create_processing_error(error)

            # Log error if no prices were extracted (all files should have price data)
            if total_prices == 0:
                no_prices_error = ProcessingError(
                    error_type='no_prices_extracted',
                    error_message=f"File processed but no prices were extracted. All files should contain price data.",
                    source_path=storage_path,
                    source_type=file_type,
                    download_entry_id=entry_id
                )
                self.database.create_processing_error(no_prices_error)
                total_errors += 1

            # Update entry status (mark as processed even if there were some errors)
            self.database.update_download_entry_status(entry_id, True)

            print(f"  Extracted {total_prices} prices, {total_errors} errors")

        except Exception as e:
            print(f"  [ERROR] Processing failed: {e}")
            success = False

            # Log the error
            self.database.create_processing_error(ProcessingError(
                error_type='processing_failed',
                error_message=str(e),
                source_path=storage_path,
                source_type=file_type,
                download_entry_id=entry_id
            ))

        return ProcessingResult(
            entry_id=entry_id,
            prices_extracted=total_prices,
            errors_count=total_errors,
            success=success and total_prices > 0
        )

    def _process_zip(
        self,
        download_entry_id: str,
        storage_path: str
    ) -> Tuple[int, List[ProcessingError]]:
        """Process a ZIP file containing PDFs."""
        total_prices = 0
        all_errors = []

        # Extract PDFs from ZIP
        zip_handler = ZIPHandler(download_entry_id)
        extracted_ids = zip_handler.extract_and_store(storage_path)

        print(f"  Extracted {len(extracted_ids)} PDFs from ZIP")

        # Get all extracted PDFs
        extracted_pdfs = zip_handler.get_unprocessed_pdfs()

        # Process each PDF
        for pdf_entry in extracted_pdfs:
            prices, errors = self._process_pdf(
                pdf_entry['storage_path'],
                download_entry_id=download_entry_id,
                extracted_pdf_id=pdf_entry['id']
            )
            total_prices += prices
            all_errors.extend(errors)

            # Log error if no prices were extracted from this PDF
            if prices == 0 and not errors:
                no_prices_error = ProcessingError(
                    error_type='no_prices_extracted',
                    error_message=f"PDF processed but no prices were extracted.",
                    source_path=pdf_entry['storage_path'],
                    source_type='pdf',
                    download_entry_id=download_entry_id,
                    extracted_pdf_id=pdf_entry['id']
                )
                all_errors.append(no_prices_error)

            # Update extracted PDF status
            if prices > 0 or not errors:
                self.database.update_extracted_pdf_status(pdf_entry['id'], True)

        return total_prices, all_errors

    def _process_pdf(
        self,
        storage_path: str,
        download_entry_id: Optional[str] = None,
        extracted_pdf_id: Optional[str] = None
    ) -> Tuple[int, List[ProcessingError]]:
        """Process a single PDF file."""
        # Download PDF to temp file
        temp_pdf = self.storage.download_to_temp(storage_path, suffix='.pdf')
        if not temp_pdf:
            return 0, [ProcessingError(
                error_type='download_failed',
                error_message=f"Failed to download PDF: {storage_path}",
                source_path=storage_path,
                source_type='pdf',
                download_entry_id=download_entry_id,
                extracted_pdf_id=extracted_pdf_id
            )]

        try:
            # Parse PDF
            parser = PDFParser(
                download_entry_id=download_entry_id,
                extracted_pdf_id=extracted_pdf_id
            )
            result = parser.parse(temp_pdf, storage_path)

            # Insert prices
            if result.prices:
                success, errors = self.database.bulk_insert_prices(result.prices)
                print(f"    PDF: {result.record_count} records from {result.city}")
                return success, result.errors
            else:
                return 0, result.errors

        finally:
            # Clean up temp file
            if os.path.exists(temp_pdf):
                os.remove(temp_pdf)

    def _process_excel(
        self,
        storage_path: str,
        download_entry_id: Optional[str] = None
    ) -> Tuple[int, List[ProcessingError]]:
        """Process an Excel file."""
        # Determine file extension
        suffix = '.xlsx' if storage_path.lower().endswith('.xlsx') else '.xls'

        # Download Excel to temp file
        temp_excel = self.storage.download_to_temp(storage_path, suffix=suffix)
        if not temp_excel:
            return 0, [ProcessingError(
                error_type='download_failed',
                error_message=f"Failed to download Excel: {storage_path}",
                source_path=storage_path,
                source_type='excel',
                download_entry_id=download_entry_id
            )]

        try:
            # Parse Excel
            parser = ExcelParser(download_entry_id=download_entry_id)
            result = parser.parse(temp_excel, storage_path)

            # Insert prices
            if result.prices:
                success, errors = self.database.bulk_insert_prices(result.prices)
                print(f"    Excel: {result.record_count} records from {len(result.cities)} cities")
                return success, result.errors
            else:
                return 0, result.errors

        finally:
            # Clean up temp file
            if os.path.exists(temp_excel):
                os.remove(temp_excel)

    def retry_errors(self, error_type: Optional[str] = None) -> Dict:
        """
        Retry processing for files with errors.

        Args:
            error_type: Optional filter by error type

        Returns:
            Summary dict
        """
        print("=" * 60)
        print("Retrying Failed Processing")
        print("=" * 60)

        errors = self.database.get_unresolved_errors(error_type)
        print(f"Found {len(errors)} unresolved errors")

        if not errors:
            return {'total': 0, 'resolved': 0}

        resolved = 0

        for error in errors:
            entry_id = error.get('download_entry_id')
            pdf_id = error.get('extracted_pdf_id')

            if not entry_id:
                continue

            # Increment retry count
            self.database.increment_error_retry(error['id'])

            # Try processing again
            try:
                if pdf_id:
                    # Retry specific PDF
                    # Get PDF entry
                    from backend.supabase_client import get_supabase_client
                    client = get_supabase_client()
                    response = client.table('extracted_pdfs').select('*').eq(
                        'id', pdf_id
                    ).execute()

                    if response.data:
                        pdf_entry = response.data[0]
                        prices, new_errors = self._process_pdf(
                            pdf_entry['storage_path'],
                            download_entry_id=entry_id,
                            extracted_pdf_id=pdf_id
                        )
                        if prices > 0:
                            self.database.mark_error_resolved(error['id'])
                            resolved += 1
                else:
                    # Retry full entry
                    result = self.process_entry(entry_id)
                    if result.success:
                        self.database.mark_error_resolved(error['id'])
                        resolved += 1

            except Exception as e:
                print(f"  [ERROR] Retry failed: {e}")

        print(f"\nResolved: {resolved} / {len(errors)}")

        return {
            'total': len(errors),
            'resolved': resolved
        }


def main():
    """CLI entry point for data processor."""
    import argparse

    parser = argparse.ArgumentParser(description='Process SIPSA data files')
    parser.add_argument('--entry-id', type=str,
                        help='Process specific entry by ID')
    parser.add_argument('--date', type=str,
                        help='Process entries for specific date (YYYY-MM-DD)')
    parser.add_argument('--retry-errors', action='store_true',
                        help='Retry processing for failed files')
    parser.add_argument('--error-type', type=str,
                        help='Filter errors by type when retrying')
    parser.add_argument('--sequential', action='store_true',
                        help='Disable parallel processing')
    parser.add_argument('--threads', type=int, default=MAX_THREADS,
                        help=f'Number of threads (default: {MAX_THREADS})')

    args = parser.parse_args()

    processor = DataProcessor(max_threads=args.threads)

    if args.entry_id:
        result = processor.process_entry(args.entry_id)
        print(f"Result: {result}")
    elif args.date:
        result = processor.process_by_date(args.date)
        print(f"Result: {result}")
    elif args.retry_errors:
        result = processor.retry_errors(args.error_type)
        print(f"Result: {result}")
    else:
        result = processor.process_all_pending(parallel=not args.sequential)
        return 0 if result['failed'] == 0 else 1

    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
