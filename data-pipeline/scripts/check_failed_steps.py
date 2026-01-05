#!/usr/bin/env python3
"""
Script to identify processing workflow steps that have permanently failed.
Cross-references error tables with success indicators to find items that
have never been successfully processed despite retries.
"""

import sys
from pathlib import Path
from datetime import datetime, timezone

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.supabase_client import get_db_connection, close_connections


def get_truly_failed_items():
    """
    Get items that have failed and were never successfully processed.
    Cross-references error tables with success tables.
    """
    conn = get_db_connection()
    cursor = conn.cursor()

    results = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "download_errors": [],
        "processing_errors": [],
        "unprocessed_downloads": [],
        "unprocessed_pdfs": []
    }

    # 1. Download errors where the URL was never successfully downloaded
    # (no matching entry in download_entries)
    cursor.execute("""
        SELECT de.*
        FROM download_errors de
        LEFT JOIN download_entries dn ON de.download_url = dn.download_link
        WHERE de.resolved = FALSE
          AND dn.id IS NULL
        ORDER BY de.error_type, de.created_at DESC
    """)
    results["download_errors"] = [dict(row) for row in cursor.fetchall()]

    # 2. Processing errors where the source was never successfully processed
    # Check: no prices exist for that source_path
    cursor.execute("""
        SELECT pe.*
        FROM processing_errors pe
        LEFT JOIN processed_prices pp ON pe.source_path = pp.source_path
        WHERE pe.resolved = FALSE
          AND pp.id IS NULL
        ORDER BY pe.error_type, pe.created_at DESC
    """)
    results["processing_errors"] = [dict(row) for row in cursor.fetchall()]

    # 3. Download entries that are unprocessed AND have no associated prices
    cursor.execute("""
        SELECT de.*
        FROM download_entries de
        LEFT JOIN processed_prices pp ON de.id = pp.download_entry_id
        WHERE de.processed_status = FALSE
          AND pp.id IS NULL
        ORDER BY de.file_type, de.row_date DESC
    """)
    results["unprocessed_downloads"] = [dict(row) for row in cursor.fetchall()]

    # 4. Extracted PDFs that are unprocessed AND have no associated prices
    cursor.execute("""
        SELECT ep.*
        FROM extracted_pdfs ep
        LEFT JOIN processed_prices pp ON ep.id = pp.extracted_pdf_id
        WHERE ep.processed_status = FALSE
          AND pp.id IS NULL
        ORDER BY ep.city, ep.pdf_date DESC
    """)
    results["unprocessed_pdfs"] = [dict(row) for row in cursor.fetchall()]

    return results


def generate_markdown_report(results):
    """Generate a structured markdown report."""
    lines = []

    lines.append("# Processing Workflow Failure Report")
    lines.append(f"\n**Generated:** {results['generated_at']}")
    lines.append("\nThis report identifies items that have **permanently failed** - they have errors")
    lines.append("and were never successfully processed in subsequent retries.")

    # Summary
    lines.append("\n## Summary")
    lines.append("")
    lines.append("| Category | Count |")
    lines.append("|----------|------:|")
    lines.append(f"| Download Errors (never downloaded) | {len(results['download_errors'])} |")
    lines.append(f"| Processing Errors (never processed) | {len(results['processing_errors'])} |")
    lines.append(f"| Unprocessed Download Entries | {len(results['unprocessed_downloads'])} |")
    lines.append(f"| Unprocessed Extracted PDFs | {len(results['unprocessed_pdfs'])} |")

    # Download Errors Section
    if results['download_errors']:
        lines.append("\n## Download Errors (Never Successfully Downloaded)")
        lines.append("")

        # Group by error type
        by_type = {}
        for err in results['download_errors']:
            etype = err.get('error_type', 'unknown')
            if etype not in by_type:
                by_type[etype] = []
            by_type[etype].append(err)

        for etype, errors in sorted(by_type.items()):
            lines.append(f"\n### {etype} ({len(errors)} errors)")
            lines.append("")
            lines.append("| URL | Error Code | Message | Retries |")
            lines.append("|-----|-----------|---------|--------:|")
            for err in errors:
                url = err.get('download_url', 'N/A')
                code = err.get('error_code') or '-'
                msg = (err.get('error_message', '') or '').replace('|', '\\|').replace('\n', ' ')
                retries = err.get('retry_count', 0)
                lines.append(f"| {url} | {code} | {msg} | {retries} |")

    # Processing Errors Section
    if results['processing_errors']:
        lines.append("\n## Processing Errors (Never Successfully Processed)")
        lines.append("")

        # Group by error type
        by_type = {}
        for err in results['processing_errors']:
            etype = err.get('error_type', 'unknown')
            if etype not in by_type:
                by_type[etype] = []
            by_type[etype].append(err)

        for etype, errors in sorted(by_type.items()):
            lines.append(f"\n### {etype} ({len(errors)} errors)")
            lines.append("")
            lines.append("| Source Path | Source Type | Message | Retries |")
            lines.append("|-------------|-------------|---------|--------:|")
            for err in errors:
                path = err.get('source_path', 'N/A')
                stype = err.get('source_type', '-')
                msg = (err.get('error_message', '') or '').replace('|', '\\|').replace('\n', ' ')
                retries = err.get('retry_count', 0)
                lines.append(f"| {path} | {stype} | {msg} | {retries} |")

    # Unprocessed Downloads Section
    if results['unprocessed_downloads']:
        lines.append("\n## Unprocessed Download Entries")
        lines.append("")

        # Group by file type
        by_type = {}
        for entry in results['unprocessed_downloads']:
            ftype = entry.get('file_type', 'unknown')
            if ftype not in by_type:
                by_type[ftype] = []
            by_type[ftype].append(entry)

        for ftype, entries in sorted(by_type.items()):
            lines.append(f"\n### {ftype} files ({len(entries)} entries)")
            lines.append("")
            lines.append("| Row Name | Row Date | Storage Path |")
            lines.append("|----------|----------|--------------|")
            for entry in entries:
                name = (entry.get('row_name', 'N/A') or '').replace('|', '\\|')
                date = str(entry.get('row_date', '-'))
                path = entry.get('storage_path', 'N/A')
                lines.append(f"| {name} | {date} | {path} |")

    # Unprocessed PDFs Section
    if results['unprocessed_pdfs']:
        lines.append("\n## Unprocessed Extracted PDFs")
        lines.append("")

        # Group by city
        by_city = {}
        for pdf in results['unprocessed_pdfs']:
            city = pdf.get('city', 'unknown') or 'unknown'
            if city not in by_city:
                by_city[city] = []
            by_city[city].append(pdf)

        lines.append("| City | Count | PDF Dates |")
        lines.append("|------|------:|-----------|")
        for city, pdfs in sorted(by_city.items(), key=lambda x: -len(x[1])):
            dates = sorted(set(str(p.get('pdf_date', '')) for p in pdfs if p.get('pdf_date')))
            dates_str = ', '.join(dates[:5])
            if len(dates) > 5:
                dates_str += f" (+{len(dates)-5} more)"
            lines.append(f"| {city} | {len(pdfs)} | {dates_str} |")

        lines.append("\n### Full PDF List")
        lines.append("")
        lines.append("| City | Market | PDF Date | Filename |")
        lines.append("|------|--------|----------|----------|")
        for pdf in results['unprocessed_pdfs']:
            city = (pdf.get('city', '-') or '-').replace('|', '\\|')
            market = (pdf.get('market', '-') or '-').replace('|', '\\|')
            date = str(pdf.get('pdf_date', '-'))
            filename = (pdf.get('pdf_filename', '-') or '-').replace('|', '\\|')
            lines.append(f"| {city} | {market} | {date} | {filename} |")

    return "\n".join(lines)


def main():
    """Main entry point."""
    try:
        print("Querying database for permanently failed items...")
        results = get_truly_failed_items()

        print(f"Found:")
        print(f"  - {len(results['download_errors'])} download errors (never downloaded)")
        print(f"  - {len(results['processing_errors'])} processing errors (never processed)")
        print(f"  - {len(results['unprocessed_downloads'])} unprocessed download entries")
        print(f"  - {len(results['unprocessed_pdfs'])} unprocessed extracted PDFs")

        # Generate markdown report
        report = generate_markdown_report(results)

        # Save report
        output_path = Path(__file__).parent.parent / "exports" / "failed_steps_report.md"
        output_path.parent.mkdir(parents=True, exist_ok=True)

        with open(output_path, 'w') as f:
            f.write(report)

        print(f"\nReport saved to: {output_path}")

    finally:
        close_connections()


if __name__ == "__main__":
    main()
