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
    process             Process all unprocessed entries
    retry-errors        Retry failed processing
    download-errors     Download files that had processing errors
    migrate             Run database migrations
    upload-divipola     Upload DIVIPOLA reference data
    export-tuples       Export data tuples for cleaning review
    generate-dimensions Generate dimension tables from reviewed data
"""

import argparse
import sys
from datetime import date, datetime
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))


def cmd_run_current(args):
    """Scrape current month and process."""
    from scraping.current_month import CurrentMonthScraper
    from processing.processor import DataProcessor

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

        processor = DataProcessor(max_threads=args.threads)
        process_result = processor.process_all_pending(parallel=not args.sequential)

        return 0 if process_result['failed'] == 0 else 1

    return 0


def cmd_run_historical(args):
    """Scrape historical data and process."""
    from scraping.historical import HistoricalScraper
    from processing.processor import DataProcessor

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

        processor = DataProcessor(max_threads=args.threads)
        process_result = processor.process_all_pending(parallel=not args.sequential)

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


def cmd_process(args):
    """Process unprocessed entries."""
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
        result = processor.process_all_pending(parallel=not args.sequential)
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
        'process': cmd_process,
        'retry-errors': cmd_retry_errors,
        'download-errors': cmd_download_errors,
        'migrate': cmd_migrate,
        'upload-divipola': cmd_upload_divipola,
        'export-tuples': cmd_export_tuples,
        'generate-dimensions': cmd_generate_dimensions,
    }

    handler = commands.get(args.command)
    if handler:
        return handler(args)
    else:
        parser.print_help()
        return 1


if __name__ == '__main__':
    sys.exit(main())
