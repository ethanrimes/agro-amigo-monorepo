#!/usr/bin/env python3
"""
Validate data coverage for SIPSA price data.

Checks that we have extracted price data for Monday-Saturday of all days
since March 2020, excluding Colombian holidays.

Usage:
    python scripts/validate_coverage.py
    python scripts/validate_coverage.py --output coverage_report.md
"""

import argparse
import sys
from pathlib import Path
from datetime import date, timedelta
from collections import defaultdict

sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.supabase_client import get_db_connection, close_connections

# Colombian national holidays by year (2020-2026)
# Source: Official Colombian holiday calendar
COLOMBIAN_HOLIDAYS = {
    2020: [
        (1, 1),    # New Year's Day
        (1, 6),    # Epiphany
        (3, 23),   # St. Joseph's Day
        (4, 9),    # Maundy Thursday
        (4, 10),   # Good Friday
        (5, 1),    # Labor Day
        (5, 25),   # Ascension Day
        (6, 15),   # Corpus Christi
        (6, 22),   # Sacred Heart
        (6, 29),   # St. Peter & St. Paul
        (7, 20),   # Independence Day
        (8, 7),    # Battle of Boyacá
        (8, 17),   # Assumption Day
        (10, 12),  # Columbus Day
        (11, 2),   # All Saints' Day
        (11, 16),  # Independence of Cartagena
        (12, 8),   # Immaculate Conception
        (12, 25),  # Christmas Day
    ],
    2021: [
        (1, 1),    # New Year's Day
        (1, 11),   # Epiphany
        (3, 22),   # St. Joseph's Day
        (4, 1),    # Maundy Thursday
        (4, 2),    # Good Friday
        (5, 1),    # Labor Day
        (5, 17),   # Ascension Day
        (6, 7),    # Corpus Christi
        (6, 14),   # Sacred Heart
        (7, 5),    # St. Peter & St. Paul
        (7, 20),   # Independence Day
        (8, 7),    # Battle of Boyacá
        (8, 16),   # Assumption Day
        (10, 18),  # Columbus Day
        (11, 1),   # All Saints' Day
        (11, 15),  # Independence of Cartagena
        (12, 8),   # Immaculate Conception
        (12, 25),  # Christmas Day
    ],
    2022: [
        (1, 1),    # New Year's Day
        (1, 10),   # Epiphany
        (3, 21),   # St. Joseph's Day
        (4, 14),   # Maundy Thursday
        (4, 15),   # Good Friday
        (5, 1),    # Labor Day
        (5, 30),   # Ascension Day
        (6, 20),   # Corpus Christi
        (6, 27),   # Sacred Heart
        (7, 4),    # St. Peter & St. Paul
        (7, 20),   # Independence Day
        (8, 7),    # Battle of Boyacá
        (8, 15),   # Assumption Day
        (10, 17),  # Columbus Day
        (11, 7),   # All Saints' Day
        (11, 14),  # Independence of Cartagena
        (12, 8),   # Immaculate Conception
        (12, 25),  # Christmas Day
    ],
    2023: [
        (1, 1),    # New Year's Day
        (1, 9),    # Epiphany
        (3, 20),   # St. Joseph's Day
        (4, 6),    # Maundy Thursday
        (4, 7),    # Good Friday
        (5, 1),    # Labor Day
        (5, 22),   # Ascension Day
        (6, 12),   # Corpus Christi
        (6, 19),   # Sacred Heart
        (7, 3),    # St. Peter & St. Paul
        (7, 20),   # Independence Day
        (8, 7),    # Battle of Boyacá
        (8, 21),   # Assumption Day
        (10, 16),  # Columbus Day
        (11, 6),   # All Saints' Day
        (11, 13),  # Independence of Cartagena
        (12, 8),   # Immaculate Conception
        (12, 25),  # Christmas Day
    ],
    2024: [
        (1, 1),    # New Year's Day
        (1, 8),    # Epiphany
        (3, 25),   # St. Joseph's Day
        (3, 28),   # Maundy Thursday
        (3, 29),   # Good Friday
        (5, 1),    # Labor Day
        (5, 13),   # Ascension Day
        (6, 3),    # Corpus Christi
        (6, 10),   # Sacred Heart
        (7, 1),    # St. Peter & St. Paul
        (7, 20),   # Independence Day
        (8, 7),    # Battle of Boyacá
        (8, 19),   # Assumption Day
        (10, 14),  # Columbus Day
        (11, 4),   # All Saints' Day
        (11, 11),  # Independence of Cartagena
        (12, 8),   # Immaculate Conception
        (12, 25),  # Christmas Day
    ],
    2025: [
        (1, 1),    # New Year's Day
        (1, 6),    # Epiphany
        (3, 24),   # St. Joseph's Day
        (4, 17),   # Maundy Thursday
        (4, 18),   # Good Friday
        (5, 1),    # Labor Day
        (6, 2),    # Ascension Day
        (6, 23),   # Corpus Christi
        (6, 30),   # Sacred Heart / St. Peter & St. Paul
        (7, 20),   # Independence Day
        (8, 7),    # Battle of Boyacá
        (8, 18),   # Assumption Day
        (10, 13),  # Columbus Day
        (11, 3),   # All Saints' Day
        (11, 17),  # Independence of Cartagena
        (12, 8),   # Immaculate Conception
        (12, 25),  # Christmas Day
    ],
    2026: [
        (1, 1),    # New Year's Day
        (1, 12),   # Epiphany
        (3, 23),   # St. Joseph's Day
        (4, 2),    # Maundy Thursday
        (4, 3),    # Good Friday
        (5, 1),    # Labor Day
        (5, 18),   # Ascension Day
        (6, 8),    # Corpus Christi
        (6, 15),   # Sacred Heart
        (6, 29),   # St. Peter & St. Paul
        (7, 20),   # Independence Day
        (8, 7),    # Battle of Boyacá
        (8, 17),   # Assumption Day
        (10, 12),  # Columbus Day
        (11, 2),   # All Saints' Day
        (11, 16),  # Independence of Cartagena
        (12, 8),   # Immaculate Conception
        (12, 25),  # Christmas Day
    ],
}


def get_colombian_holidays(year: int) -> set:
    """
    Get all Colombian holidays for a given year.
    Uses hardcoded dates from official Colombian holiday calendar.
    """
    holidays = set()

    if year in COLOMBIAN_HOLIDAYS:
        for month, day in COLOMBIAN_HOLIDAYS[year]:
            holidays.add(date(year, month, day))
    else:
        print(f"Warning: No holiday data for year {year}")

    return holidays


def get_all_holidays(start_year: int, end_year: int) -> set:
    """Get all Colombian holidays for a range of years."""
    all_holidays = set()
    for year in range(start_year, end_year + 1):
        all_holidays.update(get_colombian_holidays(year))
    return all_holidays


def get_price_dates_from_db() -> set:
    """Get all unique price_date values from processed_prices table."""
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT DISTINCT price_date FROM processed_prices WHERE price_date IS NOT NULL ORDER BY price_date")

    dates = set()
    for row in cursor.fetchall():
        if row['price_date']:
            dates.add(row['price_date'])

    cursor.close()
    return dates


def get_expected_dates(start_date: date, end_date: date, holidays: set) -> set:
    """
    Get all expected business days (Monday-Saturday) between start and end dates,
    excluding holidays.
    """
    expected = set()
    current = start_date

    while current <= end_date:
        # Monday=0, Tuesday=1, ..., Saturday=5, Sunday=6
        if current.weekday() < 6:  # Monday through Saturday
            if current not in holidays:
                expected.add(current)
        current += timedelta(days=1)

    return expected


def analyze_coverage(start_date: date, end_date: date):
    """Analyze data coverage and return missing dates."""
    print(f"Analyzing coverage from {start_date} to {end_date}...")

    # Get holidays
    holidays = get_all_holidays(start_date.year, end_date.year)
    print(f"  Identified {len(holidays)} Colombian holidays in range")

    # Get expected dates
    expected_dates = get_expected_dates(start_date, end_date, holidays)
    print(f"  Expected business days (Mon-Sat, excl holidays): {len(expected_dates)}")

    # Get actual dates from database
    actual_dates = get_price_dates_from_db()
    print(f"  Dates with extracted prices: {len(actual_dates)}")

    # Find missing dates
    missing_dates = expected_dates - actual_dates

    # Also find dates we have data for but weren't expected (weekends/holidays with data)
    unexpected_dates = actual_dates - expected_dates

    return {
        'start_date': start_date,
        'end_date': end_date,
        'expected_count': len(expected_dates),
        'actual_count': len(actual_dates),
        'missing_count': len(missing_dates),
        'missing_dates': sorted(missing_dates),
        'unexpected_count': len(unexpected_dates),
        'holidays': sorted([h for h in holidays if start_date <= h <= end_date]),
        'coverage_pct': (len(expected_dates) - len(missing_dates)) / len(expected_dates) * 100 if expected_dates else 0
    }


def generate_report(results: dict) -> str:
    """Generate markdown report from coverage analysis."""
    lines = []

    lines.append("# SIPSA Data Coverage Report")
    lines.append(f"\n**Analysis Period:** {results['start_date']} to {results['end_date']}")
    lines.append(f"**Generated:** {date.today()}")

    lines.append("\n## Summary\n")
    lines.append("| Metric | Value |")
    lines.append("|--------|------:|")
    lines.append(f"| Expected Business Days | {results['expected_count']} |")
    lines.append(f"| Days with Price Data | {results['actual_count']} |")
    lines.append(f"| Missing Days | {results['missing_count']} |")
    lines.append(f"| Coverage | {results['coverage_pct']:.1f}% |")

    if results['missing_dates']:
        lines.append("\n## Missing Days\n")
        lines.append("These business days (Monday-Saturday, excluding Colombian holidays) have no extracted price data.\n")

        # Group by year-month
        by_month = defaultdict(list)
        for d in results['missing_dates']:
            by_month[(d.year, d.month)].append(d)

        for (year, month), dates in sorted(by_month.items()):
            month_name = date(year, month, 1).strftime('%B %Y')
            lines.append(f"\n### {month_name} ({len(dates)} days)\n")

            # Show dates in a compact format
            date_strs = []
            for d in dates:
                day_name = d.strftime('%a')
                date_strs.append(f"{d.day} ({day_name})")

            # Wrap to ~80 chars per line
            current_line = []
            for ds in date_strs:
                current_line.append(ds)
                if len(', '.join(current_line)) > 70:
                    lines.append(', '.join(current_line[:-1]))
                    current_line = [ds]
            if current_line:
                lines.append(', '.join(current_line))
    else:
        lines.append("\n## Missing Days\n")
        lines.append("**No missing days found!** Full coverage achieved.")

    # Show holidays for reference
    lines.append("\n## Colombian Holidays in Range\n")
    lines.append("These dates were excluded from the expected coverage.\n")

    holiday_by_year = defaultdict(list)
    for h in results['holidays']:
        holiday_by_year[h.year].append(h)

    for year, holidays in sorted(holiday_by_year.items()):
        lines.append(f"\n### {year}\n")
        for h in holidays:
            lines.append(f"- {h.strftime('%B %d')} ({h.strftime('%A')})")

    lines.append("\n---")
    lines.append("\n*Note: This report checks for Mon-Sat coverage. SIPSA data is published on business days.*")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description='Validate SIPSA data coverage')
    parser.add_argument('--start-date', type=str, default='2020-03-01',
                        help='Start date (YYYY-MM-DD, default: 2020-03-01)')
    parser.add_argument('--end-date', type=str, default=None,
                        help='End date (YYYY-MM-DD, default: today)')
    parser.add_argument('--output', '-o', type=str, default='exports/coverage_report.md',
                        help='Output file path')
    args = parser.parse_args()

    from datetime import datetime

    start = datetime.strptime(args.start_date, '%Y-%m-%d').date()
    end = datetime.strptime(args.end_date, '%Y-%m-%d').date() if args.end_date else date.today()

    try:
        results = analyze_coverage(start, end)
        report = generate_report(results)

        output_path = Path(__file__).parent.parent / args.output
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(report)

        print(f"\nCoverage: {results['coverage_pct']:.1f}%")
        print(f"Missing days: {results['missing_count']}")
        print(f"Report saved to: {output_path}")

    finally:
        close_connections()


if __name__ == "__main__":
    main()
