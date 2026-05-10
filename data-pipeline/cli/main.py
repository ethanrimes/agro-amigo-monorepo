#!/usr/bin/env python3
"""
AgroAmigo Data Pipeline CLI

Main command-line interface for all pipeline operations.

Usage:
    python -m cli.main <command> [options]

Commands:
    run-current         Scrape current month + process
    run-historical      Scrape historical data + process
    scrape-current      Only scrape current month
    scrape-historical   Only scrape historical data
    scrape-all          Scrape all available data (current + all historical)
    process             Process all unprocessed entries
    retry-errors        Retry failed processing
    download-errors     Download files that had processing errors
    migrate             Run database migrations
    upload-divipola     Upload DIVIPOLA reference data
    export-tuples       Export data tuples for cleaning review
    generate-dimensions Generate dimension tables from reviewed data
"""

import argparse
import os
import sys

from datetime import date, datetime
from pathlib import Path

# Fix Windows console encoding for Unicode characters (e.g. Colombian city names)
if sys.platform == 'win32':
    os.environ.setdefault('PYTHONIOENCODING', 'utf-8')
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    if hasattr(sys.stderr, 'reconfigure'):
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))


def cmd_run_current(args):
    """Scrape current month and process."""
    from scraping.current_month import CurrentMonthScraper

    print("=" * 60)
    print("Running Current Month Pipeline")
    print("=" * 60)

    # Scrape
    scraper = CurrentMonthScraper(dry_run=args.dry_run)
    scrape_result = scraper.run(
        anexo_only=args.anexo_only,
        informes_only=args.informes_only,
        include_boletin=args.include_boletin
    )

    if args.dry_run:
        print("\n[DRY-RUN] Skipping processing")
        return 0

    # Process
    if scrape_result['entry_ids']:
        print("\n" + "=" * 60)
        print("Processing Downloaded Files")
        print("=" * 60)

        if args.sequential:
            from processing.processor import DataProcessor
            processor = DataProcessor(max_threads=args.threads)
            process_result = processor.process_all_pending(parallel=False)
        else:
            import asyncio
            from processing.async_processor import AsyncDataProcessor
            processor = AsyncDataProcessor()
            process_result = asyncio.run(processor.process_all_pending())

        return 0 if process_result['failed'] == 0 else 1

    return 0


def cmd_run_historical(args):
    """Scrape historical data and process."""
    from scraping.historical import HistoricalScraper

    # Parse dates
    start = parse_date_arg(args)
    end = date.today() if not args.end_date else datetime.strptime(args.end_date, '%Y-%m-%d').date()

    print("=" * 60)
    print("Running Historical Pipeline")
    print("=" * 60)

    # Scrape
    scraper = HistoricalScraper(dry_run=args.dry_run, max_threads=args.threads)
    scrape_result = scraper.run(
        start_date=start,
        end_date=end,
        anexo_only=args.anexo_only,
        informes_only=args.informes_only,
        include_boletin=args.include_boletin,
        parallel=not args.sequential
    )

    if args.dry_run:
        print("\n[DRY-RUN] Skipping processing")
        return 0

    # Process
    if scrape_result['entry_ids']:
        print("\n" + "=" * 60)
        print("Processing Downloaded Files")
        print("=" * 60)

        if args.sequential:
            from processing.processor import DataProcessor
            processor = DataProcessor(max_threads=args.threads)
            process_result = processor.process_all_pending(parallel=False)
        else:
            import asyncio
            from processing.async_processor import AsyncDataProcessor
            processor = AsyncDataProcessor()
            process_result = asyncio.run(processor.process_all_pending())

        return 0 if process_result['failed'] == 0 else 1

    return 0


def cmd_scrape_current(args):
    """Only scrape current month."""
    from scraping.current_month import CurrentMonthScraper

    scraper = CurrentMonthScraper(dry_run=args.dry_run)
    result = scraper.run(
        anexo_only=args.anexo_only,
        informes_only=args.informes_only,
        include_boletin=args.include_boletin
    )

    return 0 if result['failed'] == 0 else 1


def cmd_scrape_historical(args):
    """Only scrape historical data."""
    from scraping.historical import HistoricalScraper

    start = parse_date_arg(args)
    end = date.today() if not args.end_date else datetime.strptime(args.end_date, '%Y-%m-%d').date()

    scraper = HistoricalScraper(dry_run=args.dry_run, max_threads=args.threads)
    result = scraper.run(
        start_date=start,
        end_date=end,
        anexo_only=args.anexo_only,
        informes_only=args.informes_only,
        include_boletin=args.include_boletin,
        parallel=not args.sequential
    )

    return 0 if result['failed'] == 0 else 1


def cmd_scrape_all(args):
    """Scrape all available data (current month + all historical)."""
    from scraping.current_month import CurrentMonthScraper
    from scraping.historical import HistoricalScraper

    # SIPSA data starts from June 2012
    EARLIEST_DATE = date(2012, 6, 1)

    print("=" * 60)
    print("SIPSA Complete Data Scraper")
    print("=" * 60)
    print(f"Scraping all data from {EARLIEST_DATE} to today")
    if args.dry_run:
        print("Mode: DRY RUN")
    print("=" * 60)

    total_downloaded = 0
    total_skipped = 0
    total_failed = 0

    # Step 1: Scrape current month
    print("\n[1/2] Scraping current month...")
    current_scraper = CurrentMonthScraper(dry_run=args.dry_run)
    current_result = current_scraper.run(
        anexo_only=args.anexo_only,
        informes_only=args.informes_only,
        include_boletin=args.include_boletin
    )
    total_downloaded += current_result['downloaded']
    total_skipped += current_result['skipped']
    total_failed += current_result['failed']

    # Step 2: Scrape all historical data
    print("\n[2/2] Scraping historical data...")
    historical_scraper = HistoricalScraper(dry_run=args.dry_run, max_threads=args.threads)
    historical_result = historical_scraper.run(
        start_date=EARLIEST_DATE,
        end_date=date.today(),
        anexo_only=args.anexo_only,
        informes_only=args.informes_only,
        include_boletin=args.include_boletin,
        parallel=not args.sequential
    )
    total_downloaded += historical_result['downloaded']
    total_skipped += historical_result['skipped']
    total_failed += historical_result['failed']

    # Final summary
    print("\n" + "=" * 60)
    print("Complete Scrape Summary")
    print("=" * 60)
    print(f"  Total downloaded: {total_downloaded}")
    print(f"  Total skipped (already exist): {total_skipped}")
    print(f"  Total failed: {total_failed}")
    print("=" * 60)

    return 0 if total_failed == 0 else 1


def cmd_process(args):
    """Process unprocessed entries."""
    if args.sequential:
        # Sync fallback
        from processing.processor import DataProcessor
        processor = DataProcessor(max_threads=args.threads)
        if args.entry_id:
            result = processor.process_entry(args.entry_id)
            print(f"Result: {result}")
            return 0 if result.success else 1
        elif args.date:
            result = processor.process_by_date(args.date)
            return 0 if result.get('failed', 0) == 0 else 1
        else:
            result = processor.process_all_pending(parallel=False)
            return 0 if result['failed'] == 0 else 1
    else:
        # Async (default) — parallel downloads via aiohttp
        import asyncio
        from processing.async_processor import AsyncDataProcessor
        processor = AsyncDataProcessor()
        if args.entry_id:
            result = asyncio.run(processor.process_entry(args.entry_id))
            print(f"Result: {result}")
            return 0 if result.success else 1
        else:
            result = asyncio.run(processor.process_all_pending())
            return 0 if result['failed'] == 0 else 1


def cmd_retry_errors(args):
    """Retry failed processing."""
    from processing.processor import DataProcessor

    processor = DataProcessor(max_threads=args.threads)
    result = processor.retry_errors(error_type=args.error_type)

    print(f"Resolved: {result['resolved']} / {result['total']}")
    return 0


def cmd_download_errors(args):
    """Download files that had processing errors."""
    from processing.download_errors import download_error_files, list_error_types

    # Handle list-error-types
    if args.list_error_types:
        types = list_error_types()
        print("Available error types:")
        for t in types:
            print(f"  - {t}")
        return 0

    # Validate output is provided
    if not args.output:
        print("Error: --output is required unless using --list-error-types")
        return 1

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
                print("Error: Invalid start-time format. Use 'YYYY-MM-DD' or 'YYYY-MM-DD HH:MM:SS'")
                return 1

    if args.end_time:
        try:
            end_time = datetime.strptime(args.end_time, '%Y-%m-%d %H:%M:%S')
        except ValueError:
            try:
                end_time = datetime.strptime(args.end_time, '%Y-%m-%d')
            except ValueError:
                print("Error: Invalid end-time format. Use 'YYYY-MM-DD' or 'YYYY-MM-DD HH:MM:SS'")
                return 1

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


def cmd_migrate(args):
    """Run database migrations."""
    from migrations.run_migrations import run_all_migrations, list_migrations

    if args.list:
        list_migrations()
        return 0

    return run_all_migrations()


def cmd_upload_divipola(args):
    """Upload DIVIPOLA reference data."""
    import pandas as pd
    from config import DIVIPOLA_PATH
    from backend.supabase_client import get_db_connection

    print("=" * 60)
    print("Uploading DIVIPOLA Reference Data")
    print("=" * 60)

    if not DIVIPOLA_PATH.exists():
        print(f"Error: DIVIPOLA file not found at {DIVIPOLA_PATH}")
        return 1

    # Read TSV file
    print(f"Reading: {DIVIPOLA_PATH}")
    df = pd.read_csv(DIVIPOLA_PATH, sep='\t')

    print(f"Found {len(df)} municipalities")

    # Rename columns to match database
    column_mapping = {
        'Código (Departamento)': 'codigo_departamento',
        'Nombre (Departamento)': 'nombre_departamento',
        'Código (Municipio)': 'codigo_municipio',
        'Nombre (Municipio)': 'nombre_municipio',
        '"Municipio, Isla, Área no municipalizada"': 'tipo',
        'Longitud': 'longitud',
        'Latitud': 'latitud'
    }

    # Try both quote styles
    for old_col in list(df.columns):
        for pattern, new_col in column_mapping.items():
            if pattern in old_col or old_col.strip('"') == pattern.strip('"'):
                df = df.rename(columns={old_col: new_col})
                break

    # Ensure correct column types
    df['codigo_departamento'] = df['codigo_departamento'].astype(str).str.zfill(2)
    df['codigo_municipio'] = df['codigo_municipio'].astype(str).str.zfill(5)

    # Connect to database
    conn = get_db_connection(new_connection=True)
    cursor = conn.cursor()

    try:
        # Clear existing data
        if args.replace:
            print("Clearing existing DIVIPOLA data...")
            cursor.execute("DELETE FROM divipola_municipios")

        # Insert data
        print("Inserting data...")
        inserted = 0

        for _, row in df.iterrows():
            try:
                cursor.execute("""
                    INSERT INTO divipola_municipios
                    (codigo_departamento, nombre_departamento, codigo_municipio,
                     nombre_municipio, tipo, longitud, latitud)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (codigo_municipio) DO UPDATE SET
                        nombre_departamento = EXCLUDED.nombre_departamento,
                        nombre_municipio = EXCLUDED.nombre_municipio,
                        tipo = EXCLUDED.tipo,
                        longitud = EXCLUDED.longitud,
                        latitud = EXCLUDED.latitud
                """, (
                    row.get('codigo_departamento'),
                    row.get('nombre_departamento'),
                    row.get('codigo_municipio'),
                    row.get('nombre_municipio'),
                    row.get('tipo'),
                    row.get('longitud'),
                    row.get('latitud')
                ))
                inserted += 1
            except Exception as e:
                print(f"  Error inserting {row.get('nombre_municipio')}: {e}")

        conn.commit()
        print(f"Inserted/updated {inserted} municipalities")

    finally:
        cursor.close()
        conn.close()

    return 0


def cmd_export_tuples(args):
    """Export data tuples for cleaning review."""
    from cleaning.export_tuples import export_all_tuples

    return export_all_tuples(output_dir=args.output)


def cmd_generate_dimensions(args):
    """Generate dimension tables from reviewed data."""
    from cleaning.id_generator import generate_dimensions

    return generate_dimensions(input_dir=args.input)


def cmd_scrape_milk(args):
    """Scrape SIPSA milk price data."""
    from scraping.milk_scraper import MilkScraper

    scraper = MilkScraper(dry_run=args.dry_run)

    if args.historical:
        result = scraper.scrape_historical()
    elif args.current:
        result = scraper.scrape_current()
    else:
        hist = scraper.scrape_historical()
        curr = scraper.scrape_current()
        result = {
            'downloaded': hist['downloaded'] + curr['downloaded'],
            'failed': hist['failed'] + curr['failed'],
            'entry_ids': hist['entry_ids'] + curr['entry_ids'],
        }

    return 0 if result['failed'] == 0 else 1


def cmd_process_milk(args):
    """Process unprocessed milk price files."""
    from backend.storage import StorageClient
    from backend.database import DatabaseClient
    from processing.milk_parser import MilkParser

    db = DatabaseClient()
    storage = StorageClient()

    # Find unprocessed milk entries
    from backend.supabase_client import get_supabase_client
    client = get_supabase_client()

    if args.entry_id:
        response = client.table('download_entries').select('*').eq('id', args.entry_id).execute()
    else:
        response = client.table('download_entries').select('*').eq(
            'processed_status', False
        ).ilike('storage_path', 'milk/%').execute()

    entries = response.data or []
    print(f"Found {len(entries)} unprocessed milk entries")

    total_prices = 0
    total_errors = 0

    for entry in entries:
        entry_id = entry['id']
        storage_path = entry['storage_path']
        print(f"\n[Processing] {entry['row_name']}")

        # Download to temp
        suffix = '.xlsx' if storage_path.lower().endswith('.xlsx') else '.xls'
        temp_file = storage.download_to_temp(storage_path, suffix=suffix)
        if not temp_file:
            print(f"  [ERROR] Failed to download: {storage_path}")
            total_errors += 1
            continue

        try:
            parser = MilkParser(download_entry_id=entry_id)
            prices, errors = parser.parse(temp_file, storage_path)

            if prices:
                success, err_count = db.bulk_insert_prices(prices)
                print(f"  Extracted {success} milk prices")
                total_prices += success
            else:
                print(f"  No prices extracted")

            for e in errors:
                db.create_processing_error(e)
                total_errors += 1

            # Mark as processed
            if prices or not errors:
                db.update_download_entry_status(entry_id, True)

        finally:
            import os
            if os.path.exists(temp_file):
                os.remove(temp_file)

    print(f"\nTotal: {total_prices} prices, {total_errors} errors")
    return 0


def cmd_populate_dimensions(args):
    """Populate dimension tables from processed_prices."""
    from cleaning.populate_dimensions import DimensionPopulator

    populator = DimensionPopulator(dry_run=args.dry_run)
    populator.run(skip_observations=args.skip_observations)
    return 0


def cmd_scrape_abastecimiento(args):
    """Scrape SIPSA abastecimiento data."""
    from scraping.abastecimiento_scraper import AbastecimientoScraper

    scraper = AbastecimientoScraper(dry_run=args.dry_run)

    if args.historical:
        result = scraper.scrape_historical()
    elif args.current:
        result = scraper.scrape_current()
    else:
        hist = scraper.scrape_historical()
        curr = scraper.scrape_current()
        result = {
            'downloaded': hist['downloaded'] + curr['downloaded'],
            'failed': hist['failed'] + curr['failed'],
            'entry_ids': hist['entry_ids'] + curr['entry_ids'],
        }

    return 0 if result['failed'] == 0 else 1


def cmd_process_abastecimiento(args):
    """Process unprocessed abastecimiento files."""
    from backend.database import DatabaseClient
    from backend.dimension_resolver import DimensionResolver
    from processing.abastecimiento_parser import AbastecimientoParser
    from backend.supabase_client import get_supabase_client, get_db_connection

    client = get_supabase_client()
    db = DatabaseClient()

    # Find unprocessed abastecimiento entries (stored locally with 'local:' prefix)
    if args.entry_id:
        response = client.table('download_entries').select('*').eq('id', args.entry_id).execute()
    else:
        response = client.table('download_entries').select('*').eq(
            'processed_status', False
        ).ilike('storage_path', 'local:%abastecimiento%').execute()

    entries = response.data or []
    print(f"Found {len(entries)} unprocessed abastecimiento entries")

    if not entries:
        return 0

    # Use a single DB connection for both resolver and inserts
    conn = get_db_connection(new_connection=True)
    resolver = DimensionResolver(conn=conn)
    cursor = conn.cursor()
    cursor.execute("SET statement_timeout = '300s'")

    grand_total_inserted = 0
    grand_total_skipped = 0

    for entry in entries:
        entry_id = entry['id']
        storage_path = entry['storage_path']
        print(f"\n[Processing] {entry['row_name']}")

        # Get local file path (strip 'local:' prefix)
        local_path = storage_path.replace('local:', '')
        if not os.path.exists(local_path):
            print(f"  [ERROR] Local file not found: {local_path}")
            continue

        parser = AbastecimientoParser()
        supply_rows, cpc_map = parser.parse(local_path)

        if not supply_rows:
            print(f"  No supply rows parsed")
            db.update_download_entry_status(entry_id, True)
            continue

        batch = []
        batch_size = 2000
        file_inserted = 0
        file_skipped = 0

        for row in supply_rows:
            # Resolve category
            cat_id = resolver.resolve_category(row.group)
            if not cat_id:
                file_skipped += 1
                continue

            # Resolve product (use CPC from row or from CPC map)
            cpc = row.cpc_code or cpc_map.get(row.alimento, '')
            prod_id = resolver.resolve_product(row.alimento, cat_id, cpc_code=cpc)
            if not prod_id:
                file_skipped += 1
                continue

            # Resolve city + market
            city_id, market_id = resolver.resolve_city_market(row.city_market)
            if not city_id:
                file_skipped += 1
                continue

            cpc_clean = cpc.strip().strip("'") if cpc else None

            batch.append((
                row.observation_date.isoformat(),
                city_id, market_id,
                row.provenance_dept_code or None,
                row.provenance_muni_code or None,
                row.provenance_dept_name or None,
                row.provenance_muni_name or None,
                cat_id, prod_id, cpc_clean,
                row.quantity_kg,
                storage_path, entry_id
            ))

            if len(batch) >= batch_size:
                _insert_supply_batch(cursor, batch)
                file_inserted += len(batch)
                batch = []
                conn.commit()
                if file_inserted % 50000 == 0:
                    print(f"    Progress: {file_inserted} inserted...")

        # Flush remaining
        if batch:
            _insert_supply_batch(cursor, batch)
            file_inserted += len(batch)
            conn.commit()

        # Mark entry as processed
        db.update_download_entry_status(entry_id, True)
        print(f"  Inserted: {file_inserted}, Skipped: {file_skipped}")
        grand_total_inserted += file_inserted
        grand_total_skipped += file_skipped

    cursor.close()
    resolver.close()
    print(f"\nGrand Total: {grand_total_inserted} inserted, {grand_total_skipped} skipped")
    return 0


def cmd_scrape_rice(args):
    """Scrape SIPSA rice mill price data."""
    from scraping.rice_scraper import RiceScraper
    scraper = RiceScraper(dry_run=args.dry_run)
    if args.historical:
        result = scraper.scrape_historical()
    elif args.current:
        result = scraper.scrape_current()
    else:
        hist = scraper.scrape_historical()
        curr = scraper.scrape_current()
        result = {'downloaded': hist['downloaded'] + curr['downloaded'],
                  'failed': hist['failed'] + curr['failed'],
                  'entry_ids': hist['entry_ids'] + curr['entry_ids']}
    return 0 if result['failed'] == 0 else 1


def cmd_process_rice(args):
    """Process unprocessed rice price files."""
    from backend.storage import StorageClient
    from backend.database import DatabaseClient
    from processing.rice_parser import RiceParser
    from backend.supabase_client import get_supabase_client

    client = get_supabase_client()
    db = DatabaseClient()
    storage = StorageClient()

    if args.entry_id:
        response = client.table('download_entries').select('*').eq('id', args.entry_id).execute()
    else:
        response = client.table('download_entries').select('*').eq(
            'processed_status', False
        ).ilike('storage_path', 'rice/%').execute()

    entries = response.data or []
    print(f"Found {len(entries)} unprocessed rice entries")

    total_prices = 0
    for entry in entries:
        entry_id = entry['id']
        storage_path = entry['storage_path']
        print(f"\n[Processing] {entry['row_name']}")

        temp = storage.download_to_temp(storage_path, suffix='.xlsx')
        if not temp:
            print(f"  [ERROR] Failed to download")
            continue
        try:
            parser = RiceParser(download_entry_id=entry_id)
            prices, errors = parser.parse(temp, storage_path)
            if prices:
                success, _ = db.bulk_insert_prices(prices)
                print(f"  Extracted {success} rice prices")
                total_prices += success
            for e in errors:
                db.create_processing_error(e)
            if prices or not errors:
                db.update_download_entry_status(entry_id, True)
        finally:
            if os.path.exists(temp):
                os.remove(temp)

    print(f"\nTotal: {total_prices} rice prices")
    return 0


def cmd_scrape_insumos(args):
    """Scrape SIPSA insumos price data."""
    from scraping.insumos_scraper import InsumosScraper

    scraper = InsumosScraper(dry_run=args.dry_run)

    if args.historical:
        result = scraper.scrape_historical()
    elif args.current:
        result = scraper.scrape_current()
    else:
        result = scraper.scrape_all()

    return 0 if result['failed'] == 0 else 1


def cmd_process_insumos(args):
    """Process unprocessed insumos files."""
    from backend.database import DatabaseClient
    from backend.dimension_resolver import DimensionResolver
    from processing.insumos_parser import InsumosParser
    from backend.supabase_client import get_supabase_client, get_db_connection

    client = get_supabase_client()
    db = DatabaseClient()

    # Find unprocessed insumos entries
    if args.entry_id:
        response = client.table('download_entries').select('*').eq('id', args.entry_id).execute()
    else:
        response = client.table('download_entries').select('*').eq(
            'processed_status', False
        ).ilike('storage_path', 'local:%insumos%').execute()

    entries = response.data or []
    print(f"Found {len(entries)} unprocessed insumos entries")

    if not entries:
        return 0

    conn = get_db_connection(new_connection=True)
    cursor = conn.cursor()
    cursor.execute("SET statement_timeout = '300s'")

    # Simple caches for insumo and casa comercial dimensions
    insumo_cache = {}   # product_name -> insumo_id
    casa_cache = {}     # casa_name -> casa_comercial_id
    dept_cache = {}     # dept_name -> department_id
    grupo_cache = {}    # grupo_name -> grupo_id
    subgrupo_cache = {} # subgrupo_name -> subgrupo_id
    city_cache = {}     # muni_code -> city_id

    parser = InsumosParser()
    grand_total = 0

    for entry in entries:
        entry_id = entry['id']
        storage_path = entry['storage_path']
        local_path = storage_path.replace('local:', '')
        print(f"\n[Processing] {entry['row_name']}")

        if not os.path.exists(local_path):
            print(f"  [ERROR] Local file not found: {local_path}")
            continue

        is_dept = 'Dep' in entry['row_name'] or 'Dep' in local_path

        if is_dept:
            rows = parser.parse_department(local_path)
            file_inserted = _insert_dept_insumos(
                cursor, conn, rows, storage_path, entry_id,
                insumo_cache, casa_cache, dept_cache, grupo_cache, subgrupo_cache
            )
        else:
            rows = parser.parse_municipality(local_path)
            file_inserted = _insert_mun_insumos(
                cursor, conn, rows, storage_path, entry_id,
                insumo_cache, dept_cache, grupo_cache, subgrupo_cache, city_cache
            )

        conn.commit()
        db.update_download_entry_status(entry_id, True)
        print(f"  Inserted: {file_inserted}")
        grand_total += file_inserted

    cursor.close()
    conn.close()
    print(f"\nGrand Total: {grand_total} insumo prices inserted")
    return 0


def _resolve_grupo(cursor, name, cache):
    """Resolve raw grupo string -> dim_insumo_grupo.id, creating dim/alias if missing."""
    if not name:
        return None
    if name in cache:
        return cache[name]

    cursor.execute("SELECT grupo_id FROM alias_insumo_grupo WHERE raw_value = %s", (name,))
    row = cursor.fetchone()
    if row:
        cache[name] = row['grupo_id']
        return row['grupo_id']

    cursor.execute("SELECT id FROM dim_insumo_grupo WHERE canonical_name = %s", (name,))
    row = cursor.fetchone()
    if row:
        gid = row['id']
    else:
        cursor.execute(
            "INSERT INTO dim_insumo_grupo (canonical_name) VALUES (%s) "
            "ON CONFLICT (canonical_name) DO NOTHING RETURNING id", (name,)
        )
        r = cursor.fetchone()
        if r:
            gid = r['id']
        else:
            cursor.execute("SELECT id FROM dim_insumo_grupo WHERE canonical_name = %s", (name,))
            gid = cursor.fetchone()['id']

    cursor.execute(
        "INSERT INTO alias_insumo_grupo (raw_value, grupo_id) VALUES (%s, %s) ON CONFLICT DO NOTHING",
        (name, gid)
    )
    cache[name] = gid
    return gid


def _resolve_subgrupo(cursor, name, grupo_id, cache):
    """Resolve raw subgrupo string -> dim_insumo_subgrupo.id, creating dim/alias if missing."""
    if not name:
        return None
    if name in cache:
        return cache[name]

    cursor.execute("SELECT subgrupo_id FROM alias_insumo_subgrupo WHERE raw_value = %s", (name,))
    row = cursor.fetchone()
    if row:
        cache[name] = row['subgrupo_id']
        return row['subgrupo_id']

    cursor.execute("SELECT id FROM dim_insumo_subgrupo WHERE canonical_name = %s", (name,))
    row = cursor.fetchone()
    if row:
        sgid = row['id']
    else:
        cursor.execute(
            "INSERT INTO dim_insumo_subgrupo (canonical_name, grupo_id) VALUES (%s, %s) "
            "ON CONFLICT (canonical_name) DO NOTHING RETURNING id",
            (name, grupo_id),
        )
        r = cursor.fetchone()
        if r:
            sgid = r['id']
        else:
            cursor.execute("SELECT id FROM dim_insumo_subgrupo WHERE canonical_name = %s", (name,))
            sgid = cursor.fetchone()['id']

    cursor.execute(
        "INSERT INTO alias_insumo_subgrupo (raw_value, subgrupo_id) VALUES (%s, %s) ON CONFLICT DO NOTHING",
        (name, sgid),
    )
    cache[name] = sgid
    return sgid


def _resolve_city_by_muni(cursor, muni_code, dept_id, cache):
    """Resolve a city by 5-digit DIVIPOLA muni_code, populating dim_city from divipola if missing."""
    if not muni_code:
        return None
    if muni_code in cache:
        return cache[muni_code]

    cursor.execute("SELECT id FROM dim_city WHERE divipola_code = %s", (muni_code,))
    row = cursor.fetchone()
    if row:
        cache[muni_code] = row['id']
        return row['id']

    # Lookup name from divipola_municipios and create dim_city
    cursor.execute(
        "SELECT nombre_municipio FROM divipola_municipios WHERE codigo_municipio = %s",
        (muni_code,),
    )
    row = cursor.fetchone()
    if not row:
        cache[muni_code] = None
        return None
    name = row['nombre_municipio']

    # dim_city has UNIQUE on canonical_name but not divipola_code, so try plain name first;
    # if a row with that name already exists for a different muni, suffix with the dept code.
    candidate_names = [name, f"{name} ({muni_code[:2]})"]
    cid = None
    for cand in candidate_names:
        try:
            cursor.execute(
                "INSERT INTO dim_city (canonical_name, department_id, divipola_code) "
                "VALUES (%s, %s, %s) ON CONFLICT (canonical_name) DO NOTHING RETURNING id",
                (cand, dept_id, muni_code),
            )
            r = cursor.fetchone()
        except Exception:
            r = None
        if r:
            cid = r['id']
            break
    if cid is None:
        # Either canonical_name collision with a different divipola, or insert raced — final lookup
        cursor.execute("SELECT id FROM dim_city WHERE divipola_code = %s", (muni_code,))
        row2 = cursor.fetchone()
        cid = row2['id'] if row2 else None
    cache[muni_code] = cid
    return cid


def _resolve_insumo(cursor, name, grupo_id, subgrupo_id, cpc_code, cache):
    """Resolve or create an insumo dimension entry. Updates grupo_id/subgrupo_id if missing."""
    if name in cache:
        return cache[name]

    cursor.execute("SELECT insumo_id FROM alias_insumo WHERE raw_value = %s", (name,))
    row = cursor.fetchone()
    if row:
        # Backfill grupo/subgrupo on dim_insumo if it's missing
        if grupo_id and subgrupo_id:
            cursor.execute(
                "UPDATE dim_insumo SET grupo_id = COALESCE(grupo_id, %s), "
                "subgrupo_id = COALESCE(subgrupo_id, %s) WHERE id = %s",
                (grupo_id, subgrupo_id, row['insumo_id']),
            )
        cache[name] = row['insumo_id']
        return row['insumo_id']

    cursor.execute("SELECT id FROM dim_insumo WHERE canonical_name = %s", (name,))
    row = cursor.fetchone()
    if row:
        cache[name] = row['id']
        if grupo_id and subgrupo_id:
            cursor.execute(
                "UPDATE dim_insumo SET grupo_id = COALESCE(grupo_id, %s), "
                "subgrupo_id = COALESCE(subgrupo_id, %s) WHERE id = %s",
                (grupo_id, subgrupo_id, row['id']),
            )
        cursor.execute(
            "INSERT INTO alias_insumo (raw_value, insumo_id) VALUES (%s, %s) ON CONFLICT DO NOTHING",
            (name, row['id'])
        )
        return row['id']

    cpc_clean = cpc_code.strip().strip("'") if cpc_code else None
    cursor.execute(
        "INSERT INTO dim_insumo (canonical_name, grupo_id, subgrupo_id, cpc_code) "
        "VALUES (%s, %s, %s, %s) ON CONFLICT (canonical_name) DO NOTHING RETURNING id",
        (name, grupo_id, subgrupo_id, cpc_clean)
    )
    r = cursor.fetchone()
    if r:
        insumo_id = r['id']
    else:
        cursor.execute("SELECT id FROM dim_insumo WHERE canonical_name = %s", (name,))
        insumo_id = cursor.fetchone()['id']

    cursor.execute(
        "INSERT INTO alias_insumo (raw_value, insumo_id) VALUES (%s, %s) ON CONFLICT DO NOTHING",
        (name, insumo_id)
    )
    cache[name] = insumo_id
    return insumo_id


def _resolve_casa_comercial(cursor, name, cache):
    """Resolve or create a casa comercial dimension entry."""
    if not name:
        return None
    if name in cache:
        return cache[name]

    cursor.execute("SELECT casa_comercial_id FROM alias_casa_comercial WHERE raw_value = %s", (name,))
    row = cursor.fetchone()
    if row:
        cache[name] = row['casa_comercial_id']
        return row['casa_comercial_id']

    cursor.execute(
        "INSERT INTO dim_casa_comercial (canonical_name) VALUES (%s) "
        "ON CONFLICT (canonical_name) DO NOTHING RETURNING id", (name,)
    )
    r = cursor.fetchone()
    if r:
        cc_id = r['id']
    else:
        cursor.execute("SELECT id FROM dim_casa_comercial WHERE canonical_name = %s", (name,))
        cc_id = cursor.fetchone()['id']

    cursor.execute(
        "INSERT INTO alias_casa_comercial (raw_value, casa_comercial_id) VALUES (%s, %s) ON CONFLICT DO NOTHING",
        (name, cc_id)
    )
    cache[name] = cc_id
    return cc_id


def _resolve_dept(cursor, dept_name, dept_code, cache):
    """Resolve or create a department dimension entry."""
    if not dept_name:
        return None
    if dept_name in cache:
        return cache[dept_name]

    # Try case-insensitive match
    cursor.execute("SELECT id FROM dim_department WHERE UPPER(canonical_name) = %s", (dept_name.upper(),))
    row = cursor.fetchone()
    if row:
        cache[dept_name] = row['id']
        return row['id']

    # Create
    cursor.execute(
        "INSERT INTO dim_department (canonical_name, divipola_code) VALUES (%s, %s) "
        "ON CONFLICT (canonical_name) DO NOTHING RETURNING id", (dept_name, dept_code)
    )
    r = cursor.fetchone()
    dept_id = r['id'] if r else None
    if not dept_id:
        cursor.execute("SELECT id FROM dim_department WHERE canonical_name = %s", (dept_name,))
        dept_id = cursor.fetchone()['id']
    cache[dept_name] = dept_id
    return dept_id


def _insert_mun_insumos(cursor, conn, rows, storage_path, entry_id,
                        insumo_cache, dept_cache, grupo_cache, subgrupo_cache, city_cache):
    """Insert municipality-level insumo rows."""
    batch = []
    batch_size = 2000
    total = 0

    for row in rows:
        grupo_id = _resolve_grupo(cursor, row.grupo, grupo_cache)
        subgrupo_id = _resolve_subgrupo(cursor, row.subgrupo, grupo_id, subgrupo_cache)
        insumo_id = _resolve_insumo(cursor, row.product_name, grupo_id, subgrupo_id, '', insumo_cache)
        dept_id = _resolve_dept(cursor, row.dept_name, row.dept_code, dept_cache)
        city_id = _resolve_city_by_muni(cursor, row.muni_code, dept_id, city_cache)
        if not insumo_id or not dept_id:
            continue

        batch.append((
            row.price_date.isoformat(), dept_id, city_id,
            row.dept_code, row.muni_code,
            insumo_id, grupo_id, subgrupo_id,
            row.presentation, row.avg_price,
            storage_path, entry_id
        ))

        if len(batch) >= batch_size:
            _insert_mun_batch(cursor, batch)
            total += len(batch)
            batch = []
            conn.commit()
            if total % 50000 == 0:
                print(f"    Progress: {total} inserted...")

    if batch:
        _insert_mun_batch(cursor, batch)
        total += len(batch)

    return total


def _insert_mun_batch(cursor, batch):
    cols = (
        'price_date', 'department_id', 'city_id',
        'dept_code', 'muni_code',
        'insumo_id', 'grupo_id', 'subgrupo_id',
        'presentation', 'avg_price',
        'source_path', 'download_entry_id'
    )
    placeholders = ','.join(['%s'] * len(cols))
    values_template = f"({placeholders})"
    sql = f"INSERT INTO insumo_prices_municipality ({','.join(cols)}) VALUES {','.join([values_template] * len(batch))}"
    flat = []
    for row in batch:
        flat.extend(row)
    cursor.execute(sql, flat)


def _insert_dept_insumos(cursor, conn, rows, storage_path, entry_id,
                         insumo_cache, casa_cache, dept_cache, grupo_cache, subgrupo_cache):
    """Insert department-level insumo rows."""
    batch = []
    batch_size = 2000
    total = 0

    for row in rows:
        grupo_id = _resolve_grupo(cursor, row.grupo, grupo_cache)
        subgrupo_id = _resolve_subgrupo(cursor, row.subgrupo, grupo_id, subgrupo_cache)
        insumo_id = _resolve_insumo(cursor, row.product_name, grupo_id, subgrupo_id, row.cpc_code, insumo_cache)
        dept_id = _resolve_dept(cursor, row.dept_name, row.dept_code, dept_cache)
        casa_id = _resolve_casa_comercial(cursor, row.casa_comercial, casa_cache)
        if not insumo_id or not dept_id:
            continue

        cpc_clean = row.cpc_code.strip().strip("'") if row.cpc_code else None

        batch.append((
            row.price_date.isoformat(), dept_id, row.dept_code,
            insumo_id, grupo_id, subgrupo_id,
            row.articulo, casa_id, row.registro_ica,
            cpc_clean, row.presentation, row.avg_price,
            storage_path, entry_id
        ))

        if len(batch) >= batch_size:
            _insert_dept_batch(cursor, batch)
            total += len(batch)
            batch = []
            conn.commit()
            if total % 50000 == 0:
                print(f"    Progress: {total} inserted...")

    if batch:
        _insert_dept_batch(cursor, batch)
        total += len(batch)

    return total


def _insert_dept_batch(cursor, batch):
    cols = (
        'price_date', 'department_id', 'dept_code',
        'insumo_id', 'grupo_id', 'subgrupo_id',
        'articulo', 'casa_comercial_id', 'registro_ica',
        'cpc_code', 'presentation', 'avg_price',
        'source_path', 'download_entry_id'
    )
    placeholders = ','.join(['%s'] * len(cols))
    values_template = f"({placeholders})"
    sql = f"INSERT INTO insumo_prices_department ({','.join(cols)}) VALUES {','.join([values_template] * len(batch))}"
    flat = []
    for row in batch:
        flat.extend(row)
    cursor.execute(sql, flat)


def _insert_supply_batch(cursor, batch):
    """Bulk insert supply observations."""
    cols = (
        'observation_date', 'city_id', 'market_id',
        'provenance_dept_code', 'provenance_muni_code',
        'provenance_dept_name', 'provenance_muni_name',
        'category_id', 'product_id', 'cpc_code',
        'quantity_kg', 'source_path', 'download_entry_id'
    )
    placeholders = ','.join(['%s'] * len(cols))
    values_template = f"({placeholders})"

    sql = f"""
        INSERT INTO supply_observations ({','.join(cols)})
        VALUES {','.join([values_template] * len(batch))}
    """
    flat = []
    for row in batch:
        flat.extend(row)
    cursor.execute(sql, flat)


def parse_date_arg(args):
    """Parse date arguments (--year/--month or --start-date)."""
    if hasattr(args, 'year') and args.year:
        if hasattr(args, 'month') and args.month:
            return date(args.year, args.month, 1)
        return date(args.year, 1, 1)
    elif hasattr(args, 'start_date') and args.start_date:
        return datetime.strptime(args.start_date, '%Y-%m-%d').date()
    else:
        raise ValueError("Please specify --year or --start-date")


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description='AgroAmigo Data Pipeline CLI',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Run full current month pipeline
  python -m cli.main run-current

  # Run historical pipeline for 2024
  python -m cli.main run-historical --year 2024

  # Scrape only (no processing)
  python -m cli.main scrape-current --dry-run

  # Process pending entries
  python -m cli.main process

  # Run migrations
  python -m cli.main migrate

  # Upload DIVIPOLA reference data
  python -m cli.main upload-divipola
        """
    )

    subparsers = parser.add_subparsers(dest='command', help='Command to run')

    # ============== run-current ==============
    p_run_current = subparsers.add_parser(
        'run-current',
        help='Scrape current month and process'
    )
    p_run_current.add_argument('--dry-run', action='store_true')
    p_run_current.add_argument('--anexo-only', action='store_true')
    p_run_current.add_argument('--informes-only', action='store_true')
    p_run_current.add_argument('--include-boletin', action='store_true',
                                help='Include Boletín PDF files (excluded by default)')
    p_run_current.add_argument('--sequential', action='store_true')
    p_run_current.add_argument('--threads', type=int, default=8)

    # ============== run-historical ==============
    p_run_hist = subparsers.add_parser(
        'run-historical',
        help='Scrape historical data and process'
    )
    p_run_hist.add_argument('--start-date', type=str)
    p_run_hist.add_argument('--end-date', type=str)
    p_run_hist.add_argument('--year', type=int)
    p_run_hist.add_argument('--month', type=int, choices=range(1, 13))
    p_run_hist.add_argument('--dry-run', action='store_true')
    p_run_hist.add_argument('--anexo-only', action='store_true')
    p_run_hist.add_argument('--informes-only', action='store_true')
    p_run_hist.add_argument('--include-boletin', action='store_true',
                            help='Include Boletín PDF files (excluded by default)')
    p_run_hist.add_argument('--sequential', action='store_true')
    p_run_hist.add_argument('--threads', type=int, default=8)

    # ============== scrape-current ==============
    p_scrape_current = subparsers.add_parser(
        'scrape-current',
        help='Only scrape current month'
    )
    p_scrape_current.add_argument('--dry-run', action='store_true')
    p_scrape_current.add_argument('--anexo-only', action='store_true')
    p_scrape_current.add_argument('--informes-only', action='store_true')
    p_scrape_current.add_argument('--include-boletin', action='store_true',
                                   help='Include Boletín PDF files (excluded by default)')

    # ============== scrape-historical ==============
    p_scrape_hist = subparsers.add_parser(
        'scrape-historical',
        help='Only scrape historical data'
    )
    p_scrape_hist.add_argument('--start-date', type=str)
    p_scrape_hist.add_argument('--end-date', type=str)
    p_scrape_hist.add_argument('--year', type=int)
    p_scrape_hist.add_argument('--month', type=int, choices=range(1, 13))
    p_scrape_hist.add_argument('--dry-run', action='store_true')
    p_scrape_hist.add_argument('--anexo-only', action='store_true')
    p_scrape_hist.add_argument('--informes-only', action='store_true')
    p_scrape_hist.add_argument('--include-boletin', action='store_true',
                                help='Include Boletín PDF files (excluded by default)')
    p_scrape_hist.add_argument('--sequential', action='store_true')
    p_scrape_hist.add_argument('--threads', type=int, default=8)

    # ============== scrape-all ==============
    p_scrape_all = subparsers.add_parser(
        'scrape-all',
        help='Scrape all available data (current + all historical from June 2012)'
    )
    p_scrape_all.add_argument('--dry-run', action='store_true')
    p_scrape_all.add_argument('--anexo-only', action='store_true')
    p_scrape_all.add_argument('--informes-only', action='store_true')
    p_scrape_all.add_argument('--include-boletin', action='store_true',
                               help='Include Boletín PDF files (excluded by default)')
    p_scrape_all.add_argument('--sequential', action='store_true')
    p_scrape_all.add_argument('--threads', type=int, default=8)

    # ============== process ==============
    p_process = subparsers.add_parser(
        'process',
        help='Process unprocessed entries'
    )
    p_process.add_argument('--entry-id', type=str)
    p_process.add_argument('--date', type=str)
    p_process.add_argument('--sequential', action='store_true')
    p_process.add_argument('--threads', type=int, default=8)

    # ============== retry-errors ==============
    p_retry = subparsers.add_parser(
        'retry-errors',
        help='Retry failed processing'
    )
    p_retry.add_argument('--error-type', type=str)
    p_retry.add_argument('--threads', type=int, default=8)

    # ============== download-errors ==============
    p_download_errors = subparsers.add_parser(
        'download-errors',
        help='Download files that had processing errors'
    )
    p_download_errors.add_argument(
        '--output', '-o',
        type=str,
        help='Output directory (required unless using --list-error-types)'
    )
    p_download_errors.add_argument(
        '--error-type', '-t',
        type=str,
        help='Filter by error type (e.g., no_prices_extracted, corrupted_pdf)'
    )
    p_download_errors.add_argument(
        '--error-message', '-m',
        type=str,
        help='Filter by substring in error message'
    )
    p_download_errors.add_argument(
        '--start-time',
        type=str,
        help='Filter errors created after this time (YYYY-MM-DD or YYYY-MM-DD HH:MM:SS)'
    )
    p_download_errors.add_argument(
        '--end-time',
        type=str,
        help='Filter errors created before this time (YYYY-MM-DD or YYYY-MM-DD HH:MM:SS)'
    )
    p_download_errors.add_argument(
        '--resolved',
        choices=['true', 'false'],
        help='Filter by resolved status'
    )
    p_download_errors.add_argument(
        '--dry-run',
        action='store_true',
        help='List files without downloading'
    )
    p_download_errors.add_argument(
        '--list-error-types',
        action='store_true',
        help='List all error types in the database'
    )

    # ============== migrate ==============
    p_migrate = subparsers.add_parser(
        'migrate',
        help='Run database migrations'
    )
    p_migrate.add_argument('--list', action='store_true',
                           help='List migration status')

    # ============== upload-divipola ==============
    p_divipola = subparsers.add_parser(
        'upload-divipola',
        help='Upload DIVIPOLA reference data'
    )
    p_divipola.add_argument('--replace', action='store_true',
                            help='Replace existing data')

    # ============== export-tuples ==============
    p_export = subparsers.add_parser(
        'export-tuples',
        help='Export data tuples for cleaning review'
    )
    p_export.add_argument('--output', type=str, default='exports',
                          help='Output directory')

    # ============== generate-dimensions ==============
    p_dims = subparsers.add_parser(
        'generate-dimensions',
        help='Generate dimension tables from reviewed data'
    )
    p_dims.add_argument('--input', type=str, default='exports',
                        help='Input directory with reviewed TSVs')

    # ============== scrape-milk ==============
    p_milk = subparsers.add_parser(
        'scrape-milk',
        help='Scrape SIPSA milk price data (historical + current)'
    )
    p_milk.add_argument('--dry-run', action='store_true')
    p_milk.add_argument('--historical', action='store_true',
                        help='Only download historical series')
    p_milk.add_argument('--current', action='store_true',
                        help='Only download current month')

    # ============== process-milk ==============
    p_process_milk = subparsers.add_parser(
        'process-milk',
        help='Process unprocessed milk price files'
    )
    p_process_milk.add_argument('--entry-id', type=str,
                                help='Process specific entry by ID')

    # ============== populate-dimensions ==============
    p_pop_dims = subparsers.add_parser(
        'populate-dimensions',
        help='Populate dimension tables from processed_prices'
    )
    p_pop_dims.add_argument('--dry-run', action='store_true')
    p_pop_dims.add_argument('--skip-observations', action='store_true',
                            help='Only populate dimensions, skip price_observations')

    # ============== scrape-abastecimiento ==============
    p_abast_scrape = subparsers.add_parser(
        'scrape-abastecimiento',
        help='Scrape SIPSA abastecimiento (supply quantity) data'
    )
    p_abast_scrape.add_argument('--dry-run', action='store_true')
    p_abast_scrape.add_argument('--historical', action='store_true',
                                help='Only download historical files')
    p_abast_scrape.add_argument('--current', action='store_true',
                                help='Only download current year file')

    # ============== process-abastecimiento ==============
    p_abast_proc = subparsers.add_parser(
        'process-abastecimiento',
        help='Process unprocessed abastecimiento files'
    )
    p_abast_proc.add_argument('--entry-id', type=str,
                              help='Process specific entry by ID')

    # ============== scrape-insumos ==============
    p_insumos_scrape = subparsers.add_parser(
        'scrape-insumos',
        help='Scrape SIPSA insumos (agricultural input) price data'
    )
    p_insumos_scrape.add_argument('--dry-run', action='store_true')
    p_insumos_scrape.add_argument('--historical', action='store_true',
                                  help='Only download historical files')
    p_insumos_scrape.add_argument('--current', action='store_true',
                                  help='Only download current files')

    # ============== process-insumos ==============
    p_insumos_proc = subparsers.add_parser(
        'process-insumos',
        help='Process unprocessed insumos files'
    )
    p_insumos_proc.add_argument('--entry-id', type=str,
                                help='Process specific entry by ID')

    # ============== scrape-rice ==============
    p_rice_scrape = subparsers.add_parser(
        'scrape-rice',
        help='Scrape SIPSA rice mill price data'
    )
    p_rice_scrape.add_argument('--dry-run', action='store_true')
    p_rice_scrape.add_argument('--historical', action='store_true')
    p_rice_scrape.add_argument('--current', action='store_true')

    # ============== process-rice ==============
    p_rice_proc = subparsers.add_parser(
        'process-rice',
        help='Process unprocessed rice price files'
    )
    p_rice_proc.add_argument('--entry-id', type=str)

    # Parse and dispatch
    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return 1

    commands = {
        'run-current': cmd_run_current,
        'run-historical': cmd_run_historical,
        'scrape-current': cmd_scrape_current,
        'scrape-historical': cmd_scrape_historical,
        'scrape-all': cmd_scrape_all,
        'process': cmd_process,
        'retry-errors': cmd_retry_errors,
        'download-errors': cmd_download_errors,
        'migrate': cmd_migrate,
        'upload-divipola': cmd_upload_divipola,
        'export-tuples': cmd_export_tuples,
        'generate-dimensions': cmd_generate_dimensions,
        'scrape-milk': cmd_scrape_milk,
        'process-milk': cmd_process_milk,
        'populate-dimensions': cmd_populate_dimensions,
        'scrape-abastecimiento': cmd_scrape_abastecimiento,
        'process-abastecimiento': cmd_process_abastecimiento,
        'scrape-insumos': cmd_scrape_insumos,
        'process-insumos': cmd_process_insumos,
        'scrape-rice': cmd_scrape_rice,
        'process-rice': cmd_process_rice,
    }

    handler = commands.get(args.command)
    if handler:
        return handler(args)
    else:
        parser.print_help()
        return 1


if __name__ == '__main__':
    sys.exit(main())
