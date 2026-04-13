#!/usr/bin/env python3
"""
Async PDF reprocessor — uses aiohttp for parallel storage downloads.

Downloads N PDFs concurrently via async HTTP, parses them in a thread pool,
and writes results to DB via a single psycopg2 connection.

This is 10-20x faster than sequential processing because the bottleneck
(Supabase storage HTTP downloads) is fully parallelized.
"""

import asyncio
import os
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from urllib.parse import quote

import aiohttp

_parent_dir = str(Path(__file__).parent.parent)
if _parent_dir not in sys.path:
    sys.path.insert(0, _parent_dir)

# Fix Windows console encoding
if sys.platform == 'win32':
    os.environ.setdefault('PYTHONIOENCODING', 'utf-8')
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    if hasattr(sys.stderr, 'reconfigure'):
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')

from dotenv import load_dotenv
load_dotenv(Path(_parent_dir) / '.env')

SUPABASE_URL = os.getenv('SUPABASE_URL')
SUPABASE_KEY = os.getenv('SUPABASE_SECRET_KEY')
BUCKET = 'sipsa-raw-files'
MAX_PRICE = 9999999999.99

# Concurrency settings
DOWNLOAD_CONCURRENCY = 20   # Parallel HTTP downloads
PARSE_WORKERS = 4           # Thread pool for CPU-bound PDF parsing
COMMIT_EVERY = 100          # DB commit interval


async def download_pdf(session: aiohttp.ClientSession, storage_path: str) -> bytes | None:
    """Download a PDF from Supabase storage via async HTTP."""
    # Encode path segments individually (preserve /)
    parts = storage_path.split('/')
    encoded = '/'.join(quote(p, safe='') for p in parts)
    url = f"{SUPABASE_URL}/storage/v1/object/{BUCKET}/{encoded}"

    try:
        async with session.get(url) as resp:
            if resp.status == 200:
                return await resp.read()
    except Exception:
        pass
    return None


def parse_pdf_sync(pdf_data: bytes, pdf_id: str, entry_id: str, storage_path: str):
    """Parse a PDF synchronously (called from thread pool)."""
    from processing.pdf_parser import PDFParser

    fd, tmp = tempfile.mkstemp(suffix='.pdf')
    try:
        os.write(fd, pdf_data)
        os.close(fd)
        parser = PDFParser(download_entry_id=entry_id, extracted_pdf_id=pdf_id)
        result = parser.parse(tmp, storage_path)
        return (pdf_id, result.prices, len(result.errors))
    except Exception:
        return (pdf_id, None, 1)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def write_batch(cursor, conn, batch):
    """Write a batch of parsed results to the DB."""
    total_prices = 0
    total_ok = 0

    for pdf_id, prices, err_count in batch:
        if prices is None:
            continue

        if prices:
            # Filter overflow
            valid = [p for p in prices if not (
                (p.min_price and abs(p.min_price) > MAX_PRICE) or
                (p.max_price and abs(p.max_price) > MAX_PRICE) or
                (p.avg_price and abs(p.avg_price) > MAX_PRICE)
            )]
            if valid:
                records = [(
                    p.category, p.subcategory or '', p.product, p.presentation or '', p.units or '',
                    p.price_date.isoformat() if p.price_date else None,
                    p.round, p.min_price, p.max_price, p.avg_price,
                    p.source_type, p.source_path, p.download_entry_id, p.extracted_pdf_id,
                    p.city, p.market or '', datetime.now().isoformat()
                ) for p in valid]
                cols = 'category,subcategory,product,presentation,units,price_date,round,min_price,max_price,avg_price,source_type,source_path,download_entry_id,extracted_pdf_id,city,market,processed_date'
                ph = ','.join(['%s'] * 17)
                try:
                    vals = ','.join([cursor.mogrify(f"({ph})", r).decode() for r in records])
                    cursor.execute(f"INSERT INTO processed_prices ({cols}) VALUES {vals}")
                    total_prices += len(records)
                except Exception:
                    conn.rollback()
                    # Fallback: insert one by one
                    for r in records:
                        try:
                            cursor.execute(f"INSERT INTO processed_prices ({cols}) VALUES ({ph})", r)
                            total_prices += 1
                        except Exception:
                            conn.rollback()

        if prices or not err_count:
            cursor.execute(
                "UPDATE extracted_pdfs SET processed_status = true, updated_at = NOW() WHERE id = %s",
                (pdf_id,)
            )
            total_ok += 1

    conn.commit()
    return total_prices, total_ok


async def process_batch(session, semaphore, loop, executor, pdfs):
    """Download + parse a batch of PDFs concurrently."""
    results = []

    async def download_and_parse(pdf):
        async with semaphore:
            data = await download_pdf(session, pdf['storage_path'])
            if data is None:
                return (pdf['id'], None, 0)
            # Parse in thread pool (CPU-bound)
            return await loop.run_in_executor(
                executor,
                parse_pdf_sync, data, pdf['id'], pdf['download_entry_id'], pdf['storage_path']
            )

    tasks = [download_and_parse(pdf) for pdf in pdfs]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    # Filter out exceptions
    clean = []
    for r in results:
        if isinstance(r, Exception):
            clean.append((None, None, 1))
        else:
            clean.append(r)
    return clean


async def main():
    from backend.supabase_client import get_db_connection
    from concurrent.futures import ThreadPoolExecutor

    # Get pending PDFs
    conn = get_db_connection(new_connection=True)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, storage_path, download_entry_id
        FROM extracted_pdfs WHERE processed_status = false
        ORDER BY pdf_date
    """)
    pending = cursor.fetchall()
    cursor.close()
    conn.close()
    print(f"Unprocessed: {len(pending)}")

    if not pending:
        return

    # DB write connection
    wconn = get_db_connection(new_connection=True)
    wc = wconn.cursor()

    # Async HTTP session with connection pooling
    connector = aiohttp.TCPConnector(limit=DOWNLOAD_CONCURRENCY, limit_per_host=DOWNLOAD_CONCURRENCY)
    headers = {
        'apikey': SUPABASE_KEY,
        'Authorization': f'Bearer {SUPABASE_KEY}'
    }

    semaphore = asyncio.Semaphore(DOWNLOAD_CONCURRENCY)
    loop = asyncio.get_event_loop()
    executor = ThreadPoolExecutor(max_workers=PARSE_WORKERS)

    total_prices = 0
    total_ok = 0
    total_fail = 0
    done = 0

    print(f"Processing with {DOWNLOAD_CONCURRENCY} concurrent downloads, {PARSE_WORKERS} parse workers...")

    async with aiohttp.ClientSession(connector=connector, headers=headers) as session:
        # Process in chunks
        chunk_size = COMMIT_EVERY
        for i in range(0, len(pending), chunk_size):
            chunk = pending[i:i + chunk_size]
            results = await process_batch(session, semaphore, loop, executor, chunk)

            # Write to DB
            prices, ok = write_batch(wc, wconn, results)
            total_prices += prices
            total_ok += ok
            total_fail += sum(1 for r in results if r[1] is None)
            done += len(chunk)

            if done % 500 == 0 or done == len(pending):
                print(f"  {done}/{len(pending)}: {total_prices:,} prices, {total_ok:,} ok, {total_fail} fail")

    # Mark ZIPs done
    wc.execute("""
        UPDATE download_entries SET processed_status = true
        WHERE file_type = 'zip' AND processed_status = false
          AND NOT EXISTS (
              SELECT 1 FROM extracted_pdfs ep
              WHERE ep.download_entry_id = download_entries.id AND ep.processed_status = false
          )
    """)
    zips = wc.rowcount
    wconn.commit()
    wc.close()
    wconn.close()
    executor.shutdown()

    print(f"\n{'=' * 60}")
    print(f"DONE: {total_ok:,} PDFs, {total_prices:,} prices, {total_fail} fail, {zips} ZIPs")


if __name__ == '__main__':
    asyncio.run(main())
