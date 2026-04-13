#!/usr/bin/env python3
"""
Async data processor for SIPSA files.

Uses aiohttp for parallel storage downloads/uploads, psycopg2 for DB writes,
and a thread pool for CPU-bound PDF/Excel parsing. This replaces the sync
DataProcessor as the default processing path.

Typical throughput: 10-20 PDFs/sec (vs ~1/sec sequential).
"""

import asyncio
import os
import re
import sys
import tempfile
import zipfile
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime, date
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from urllib.parse import quote

import aiohttp

_parent_dir = str(Path(__file__).parent.parent)
if _parent_dir not in sys.path:
    sys.path.insert(0, _parent_dir)

# Fix Windows encoding
if sys.platform == 'win32':
    os.environ.setdefault('PYTHONIOENCODING', 'utf-8')
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    if hasattr(sys.stderr, 'reconfigure'):
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')

from dotenv import load_dotenv
load_dotenv(Path(_parent_dir) / '.env')

from backend.supabase_client import get_db_connection
from backend.database import DatabaseClient, ProcessedPrice, ProcessingError
from backend.storage import sanitize_path
from processing.pdf_parser import PDFParser
from processing.excel_parser import ExcelParser
from processing.ocr_fallback import is_scanned_pdf, ocr_extract_prices

SUPABASE_URL = os.getenv('SUPABASE_URL')
SUPABASE_KEY = os.getenv('SUPABASE_SECRET_KEY')
BUCKET = 'sipsa-raw-files'
MAX_PRICE = 9999999999.99  # DECIMAL(12,2) limit

# Concurrency settings
DEFAULT_DOWNLOAD_CONCURRENCY = 20
DEFAULT_PARSE_WORKERS = 4
DEFAULT_COMMIT_EVERY = 100


@dataclass
class ProcessingResult:
    """Result of processing a download entry."""
    entry_id: str
    prices_extracted: int
    errors_count: int
    success: bool


class AsyncDataProcessor:
    """Async processor for SIPSA data files."""

    def __init__(
        self,
        download_concurrency: int = DEFAULT_DOWNLOAD_CONCURRENCY,
        parse_workers: int = DEFAULT_PARSE_WORKERS,
        commit_every: int = DEFAULT_COMMIT_EVERY,
    ):
        self.download_concurrency = download_concurrency
        self.parse_workers = parse_workers
        self.commit_every = commit_every

    # ==================== PUBLIC API ====================

    async def process_all_pending(self) -> Dict:
        """Process all pending download entries."""
        print("=" * 60)
        print("SIPSA Async Data Processor")
        print("=" * 60)
        print(f"Concurrency: {self.download_concurrency} downloads, {self.parse_workers} parse workers")

        db = DatabaseClient()
        entries = db.get_unprocessed_download_entries()
        print(f"Found {len(entries)} unprocessed entries")

        if not entries:
            return {'total': 0, 'success': 0, 'failed': 0, 'prices_extracted': 0}

        # Classify entries
        zip_entries = [e for e in entries if e['file_type'] == 'zip']
        pdf_entries = [e for e in entries if e['file_type'] == 'pdf']
        excel_entries = [e for e in entries if e['file_type'] == 'excel']

        print(f"  ZIP: {len(zip_entries)}, PDF: {len(pdf_entries)}, Excel: {len(excel_entries)}")

        results = []

        # Process ZIPs first (they generate extracted PDFs)
        if zip_entries:
            zip_results = await self._process_zip_entries(zip_entries)
            results.extend(zip_results)

        # Process standalone PDFs and Excels
        file_entries = pdf_entries + excel_entries
        if file_entries:
            file_results = await self._process_file_entries(file_entries)
            results.extend(file_results)

        # Summary
        success = sum(1 for r in results if r.success)
        failed = sum(1 for r in results if not r.success)
        total_prices = sum(r.prices_extracted for r in results)

        print("\n" + "=" * 60)
        print("Processing Summary")
        print("=" * 60)
        print(f"  Entries processed: {len(results)}")
        print(f"  Successful: {success}")
        print(f"  Failed: {failed}")
        print(f"  Total prices extracted: {total_prices:,}")

        return {
            'total': len(results),
            'success': success,
            'failed': failed,
            'prices_extracted': total_prices,
        }

    async def process_entry(self, entry_id: str) -> ProcessingResult:
        """Process a single download entry by ID."""
        from backend.supabase_client import get_supabase_client
        client = get_supabase_client()
        response = client.table('download_entries').select('*').eq('id', entry_id).execute()
        if not response.data:
            raise ValueError(f"Download entry not found: {entry_id}")
        entry = response.data[0]

        if entry['file_type'] == 'zip':
            results = await self._process_zip_entries([entry])
        else:
            results = await self._process_file_entries([entry])

        return results[0] if results else ProcessingResult(entry_id, 0, 1, False)

    # ==================== ASYNC HTTP HELPERS ====================

    def _make_session(self) -> aiohttp.ClientSession:
        """Create an aiohttp session with connection pooling."""
        connector = aiohttp.TCPConnector(
            limit=self.download_concurrency,
            limit_per_host=self.download_concurrency,
        )
        headers = {
            'apikey': SUPABASE_KEY,
            'Authorization': f'Bearer {SUPABASE_KEY}',
        }
        return aiohttp.ClientSession(connector=connector, headers=headers)

    async def _download_file(self, session: aiohttp.ClientSession, storage_path: str) -> Optional[bytes]:
        """Download a file from Supabase storage via async HTTP."""
        parts = storage_path.split('/')
        encoded = '/'.join(quote(p, safe='') for p in parts)
        url = f"{SUPABASE_URL}/storage/v1/object/{BUCKET}/{encoded}"

        for attempt in range(3):
            try:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=60)) as resp:
                    if resp.status == 200:
                        return await resp.read()
                    elif resp.status == 404:
                        return None
            except Exception:
                if attempt < 2:
                    await asyncio.sleep(1 * (attempt + 1))
        return None

    async def _upload_file(self, session: aiohttp.ClientSession, storage_path: str,
                           file_data: bytes, content_type: str) -> Dict:
        """Upload a file to Supabase storage via async HTTP."""
        clean_path = sanitize_path(storage_path)
        parts = clean_path.split('/')
        encoded = '/'.join(quote(p, safe='') for p in parts)
        url = f"{SUPABASE_URL}/storage/v1/object/{BUCKET}/{encoded}"

        try:
            async with session.post(url, data=file_data,
                                    headers={'Content-Type': content_type},
                                    timeout=aiohttp.ClientTimeout(total=120)) as resp:
                if resp.status in (200, 201):
                    return {'success': True, 'path': clean_path}
                elif resp.status == 409:
                    return {'success': True, 'path': clean_path, 'already_exists': True}
                else:
                    return {'success': False, 'error': f'HTTP {resp.status}'}
        except Exception as e:
            return {'success': False, 'error': str(e)}

    # ==================== ZIP PROCESSING ====================

    async def _process_zip_entries(self, entries: List[Dict]) -> List[ProcessingResult]:
        """Process ZIP entries: download, extract PDFs, upload, parse."""
        results = []
        wconn = get_db_connection(new_connection=True)
        wc = wconn.cursor()
        executor = ThreadPoolExecutor(max_workers=self.parse_workers)
        loop = asyncio.get_event_loop()

        async with self._make_session() as session:
            semaphore = asyncio.Semaphore(self.download_concurrency)

            for entry in entries:
                entry_id = entry['id']
                storage_path = entry['storage_path']
                print(f"\n[Processing ZIP] {entry['row_name']}")

                try:
                    result = await self._process_single_zip(
                        session, semaphore, executor, loop, wc, wconn,
                        entry_id, storage_path
                    )
                    results.append(result)

                    # Mark entry as processed if all PDFs succeeded
                    if result.success:
                        wc.execute(
                            "UPDATE download_entries SET processed_status = true, updated_at = NOW() WHERE id = %s",
                            (entry_id,)
                        )
                        wconn.commit()

                except Exception as e:
                    print(f"  [ERROR] {e}")
                    results.append(ProcessingResult(entry_id, 0, 1, False))

        executor.shutdown(wait=False)
        wc.close()
        wconn.close()
        return results

    async def _process_single_zip(self, session, semaphore, executor, loop,
                                   wc, wconn, entry_id, storage_path) -> ProcessingResult:
        """Process a single ZIP file."""
        # Step 1: Download ZIP
        zip_data = await self._download_file(session, storage_path)
        if not zip_data:
            print(f"  [ERROR] Failed to download ZIP")
            return ProcessingResult(entry_id, 0, 1, False)

        # Step 2: Extract PDFs locally
        fd, zip_tmp = tempfile.mkstemp(suffix='.zip')
        os.write(fd, zip_data)
        os.close(fd)
        del zip_data  # Free memory

        try:
            pdf_files = await loop.run_in_executor(executor, self._extract_zip_sync, zip_tmp)
        finally:
            os.unlink(zip_tmp)

        if not pdf_files:
            return ProcessingResult(entry_id, 0, 0, True)

        print(f"  Found {len(pdf_files)} PDFs in ZIP")

        # Step 3: Check which PDFs need processing (via psycopg2)
        to_process = []
        newly_uploaded = 0

        for pdf_filename, pdf_data, pdf_storage_path in pdf_files:
            clean_path = sanitize_path(pdf_storage_path)

            # Check if already in DB
            wc.execute("SELECT id, processed_status FROM extracted_pdfs WHERE storage_path = %s", (clean_path,))
            existing = wc.fetchone()

            if existing:
                if existing['processed_status']:
                    continue  # Already processed, skip
                else:
                    to_process.append((existing['id'], clean_path))
                    continue

            # Upload PDF to storage
            upload_result = await self._upload_file(session, pdf_storage_path, pdf_data, 'application/pdf')
            if not upload_result.get('success'):
                continue

            # Parse city/market/date from filename
            city, market, pdf_date = self._parse_pdf_filename(pdf_filename)

            # Create extracted_pdf record via psycopg2
            wc.execute("""
                INSERT INTO extracted_pdfs (download_entry_id, original_zip_path, pdf_filename,
                    storage_path, city, market, pdf_date, processed_status)
                VALUES (%s, %s, %s, %s, %s, %s, %s, false) RETURNING id
            """, (entry_id, storage_path, pdf_filename, clean_path, city, market,
                  pdf_date.isoformat() if pdf_date else None))
            row = wc.fetchone()
            if row:
                to_process.append((row['id'], clean_path))
                newly_uploaded += 1

        wconn.commit()
        print(f"  Uploaded {newly_uploaded} new, {len(to_process)} to process")

        # Step 4: Download + parse each PDF concurrently
        total_prices = 0
        total_errors = 0

        async def download_parse_one(pdf_id, pdf_path):
            async with semaphore:
                data = await self._download_file(session, pdf_path)
                if not data:
                    return (pdf_id, None, 1)
                return await loop.run_in_executor(
                    executor, self._parse_pdf_sync, data, pdf_id, entry_id, pdf_path
                )

        # Process in batches for DB commits
        for i in range(0, len(to_process), self.commit_every):
            batch = to_process[i:i + self.commit_every]
            tasks = [download_parse_one(pid, ppath) for pid, ppath in batch]
            results_batch = await asyncio.gather(*tasks, return_exceptions=True)

            for r in results_batch:
                if isinstance(r, Exception):
                    total_errors += 1
                    continue
                pdf_id, prices, err_count = r
                if prices:
                    count = self._write_prices(wc, prices)
                    total_prices += count
                if prices or not err_count:
                    wc.execute("UPDATE extracted_pdfs SET processed_status = true, updated_at = NOW() WHERE id = %s", (pdf_id,))
                if err_count:
                    total_errors += err_count

            wconn.commit()

        print(f"  Extracted {total_prices:,} prices, {total_errors} errors")
        return ProcessingResult(entry_id, total_prices, total_errors, total_errors == 0)

    # ==================== FILE (PDF/EXCEL) PROCESSING ====================

    async def _process_file_entries(self, entries: List[Dict]) -> List[ProcessingResult]:
        """Process standalone PDF and Excel entries concurrently."""
        if not entries:
            return []

        results = []
        wconn = get_db_connection(new_connection=True)
        wc = wconn.cursor()
        executor = ThreadPoolExecutor(max_workers=self.parse_workers)
        loop = asyncio.get_event_loop()

        async with self._make_session() as session:
            semaphore = asyncio.Semaphore(self.download_concurrency)

            async def process_one(entry):
                entry_id = entry['id']
                storage_path = entry['storage_path']
                file_type = entry['file_type']

                async with semaphore:
                    data = await self._download_file(session, storage_path)
                    if not data:
                        return ProcessingResult(entry_id, 0, 1, False)

                    if file_type == 'pdf':
                        # Skip boletín PDFs
                        if '/pdf/' in storage_path:
                            return ProcessingResult(entry_id, 0, 0, True)
                        result = await loop.run_in_executor(
                            executor, self._parse_pdf_sync, data, None, entry_id, storage_path
                        )
                        _, prices, errors = result
                    elif file_type == 'excel':
                        row_date = None
                        if entry.get('row_date'):
                            try:
                                rd = entry['row_date']
                                if isinstance(rd, str):
                                    row_date = datetime.strptime(rd, '%Y-%m-%d').date()
                                else:
                                    row_date = rd
                            except Exception:
                                pass
                        result = await loop.run_in_executor(
                            executor, self._parse_excel_sync, data, entry_id, storage_path, row_date
                        )
                        _, prices, errors = result
                    else:
                        return ProcessingResult(entry_id, 0, 0, True)

                    return ProcessingResult(entry_id, len(prices) if prices else 0, errors, True), prices

            # Process in batches
            total_prices = 0
            for i in range(0, len(entries), self.commit_every):
                batch = entries[i:i + self.commit_every]
                tasks = [process_one(e) for e in batch]
                batch_results = await asyncio.gather(*tasks, return_exceptions=True)

                for r in batch_results:
                    if isinstance(r, Exception):
                        results.append(ProcessingResult('unknown', 0, 1, False))
                        continue
                    if isinstance(r, tuple):
                        proc_result, prices = r
                        if prices:
                            count = self._write_prices(wc, prices)
                            total_prices += count
                            proc_result = ProcessingResult(proc_result.entry_id, count, proc_result.errors_count, True)
                        # Mark entry processed
                        wc.execute(
                            "UPDATE download_entries SET processed_status = true, updated_at = NOW() WHERE id = %s",
                            (proc_result.entry_id,)
                        )
                        results.append(proc_result)
                    else:
                        results.append(r)

                wconn.commit()
                if (i + self.commit_every) % 500 == 0:
                    print(f"  Progress: {min(i + self.commit_every, len(entries))}/{len(entries)}, {total_prices:,} prices")

        executor.shutdown(wait=False)
        wc.close()
        wconn.close()
        return results

    # ==================== SYNC PARSE HELPERS (run in thread pool) ====================

    @staticmethod
    def _parse_pdf_sync(pdf_data: bytes, pdf_id, entry_id, storage_path):
        """Parse a PDF synchronously (called from thread pool)."""
        fd, tmp = tempfile.mkstemp(suffix='.pdf')
        try:
            os.write(fd, pdf_data)
            os.close(fd)
            parser = PDFParser(download_entry_id=entry_id, extracted_pdf_id=pdf_id)
            result = parser.parse(tmp, storage_path)

            # OCR fallback for scanned images
            if not result.prices and is_scanned_pdf(tmp):
                ocr_prices, ocr_errors = ocr_extract_prices(
                    tmp, storage_path,
                    download_entry_id=entry_id, extracted_pdf_id=pdf_id
                )
                if ocr_prices:
                    return (pdf_id, ocr_prices, len(ocr_errors))
                return (pdf_id, None, len(result.errors) + len(ocr_errors))

            return (pdf_id, result.prices if result.prices else None, len(result.errors))
        except Exception:
            return (pdf_id, None, 1)
        finally:
            if os.path.exists(tmp):
                os.unlink(tmp)

    @staticmethod
    def _parse_excel_sync(excel_data: bytes, entry_id, storage_path, row_date=None):
        """Parse an Excel file synchronously (called from thread pool)."""
        suffix = '.xlsx' if storage_path.lower().endswith('.xlsx') else '.xls'
        fd, tmp = tempfile.mkstemp(suffix=suffix)
        try:
            os.write(fd, excel_data)
            os.close(fd)
            parser = ExcelParser(download_entry_id=entry_id, row_date=row_date)
            result = parser.parse(tmp, storage_path)
            return (entry_id, result.prices if result.prices else None, len(result.errors))
        except Exception:
            return (entry_id, None, 1)
        finally:
            if os.path.exists(tmp):
                os.unlink(tmp)

    # ==================== ZIP EXTRACTION (sync, run in thread pool) ====================

    @staticmethod
    def _extract_zip_sync(zip_path: str) -> List[Tuple[str, bytes, str]]:
        """Extract PDFs from a ZIP file. Returns list of (filename, data, storage_path)."""
        results = []
        try:
            with zipfile.ZipFile(zip_path, 'r') as zf:
                for name in zf.namelist():
                    if name.lower().endswith('.pdf') and not name.startswith('._') and '__MACOSX' not in name:
                        pdf_filename = os.path.basename(name)
                        pdf_data = zf.read(name)

                        # Parse date from filename for storage path
                        city, market, pdf_date = AsyncDataProcessor._parse_pdf_filename(pdf_filename)
                        if pdf_date:
                            storage_path = f"extracted/{pdf_date.year}/{pdf_date.month:02d}/{pdf_date.day:02d}/{pdf_filename}"
                        else:
                            storage_path = f"extracted/unknown_date/{pdf_filename}"

                        results.append((pdf_filename, pdf_data, storage_path))
        except zipfile.BadZipFile:
            pass
        return results

    @staticmethod
    def _parse_pdf_filename(filename: str) -> Tuple[str, str, Optional[date]]:
        """Parse city, market, date from PDF filename."""
        city = ""
        market = ""
        pdf_date = None

        name = filename.replace('.pdf', '').replace('.PDF', '')
        date_pattern = r'-(\d{1,2})-(\d{1,2})-(\d{4})$'
        date_match = re.search(date_pattern, name)

        if date_match:
            day, month, year = date_match.groups()
            try:
                pdf_date = date(int(year), int(month), int(day))
            except ValueError:
                pass
            name = re.sub(date_pattern, '', name)

        if ',' in name:
            parts = name.split(',', 1)
            city = parts[0].strip()
            market = parts[1].strip() if len(parts) > 1 else ""
        else:
            city = name.strip()

        return city, market, pdf_date

    # ==================== DB WRITE HELPERS ====================

    def _write_prices(self, cursor, prices: List[ProcessedPrice]) -> int:
        """Bulk insert prices via psycopg2. Returns count inserted."""
        if not prices:
            return 0

        # Filter overflow values
        valid = [p for p in prices if not (
            (p.min_price and abs(p.min_price) > MAX_PRICE) or
            (p.max_price and abs(p.max_price) > MAX_PRICE) or
            (p.avg_price and abs(p.avg_price) > MAX_PRICE)
        )]
        if not valid:
            return 0

        records = [(
            p.category, p.subcategory or '', p.product, p.presentation or '', p.units or '',
            p.price_date.isoformat() if p.price_date else None,
            p.round, p.min_price, p.max_price, p.avg_price,
            p.source_type, p.source_path, p.download_entry_id, p.extracted_pdf_id,
            p.city, p.market or '', datetime.now().isoformat()
        ) for p in valid]

        cols = ('category,subcategory,product,presentation,units,price_date,round,'
                'min_price,max_price,avg_price,source_type,source_path,'
                'download_entry_id,extracted_pdf_id,city,market,processed_date')
        ph = ','.join(['%s'] * 17)

        try:
            vals = ','.join([cursor.mogrify(f"({ph})", r).decode() for r in records])
            cursor.execute(f"INSERT INTO processed_prices ({cols}) VALUES {vals}")
            return len(records)
        except Exception:
            # Fallback: row-by-row
            count = 0
            for r in records:
                try:
                    cursor.execute(f"INSERT INTO processed_prices ({cols}) VALUES ({ph})", r)
                    count += 1
                except Exception:
                    pass
            return count
