#!/usr/bin/env python3
"""
Find the ~24 processed_prices rows that failed the JOIN in populate_observations,
identify WHY they failed, and create missing aliases to fix them.
"""

import os
import sys
from pathlib import Path

_parent = str(Path(__file__).parent.parent)
if _parent not in sys.path:
    sys.path.insert(0, _parent)

if sys.platform == 'win32':
    os.environ.setdefault('PYTHONIOENCODING', 'utf-8')
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    if hasattr(sys.stderr, 'reconfigure'):
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')

from backend.supabase_client import get_db_connection


def run(fix=False):
    conn = get_db_connection(new_connection=True)
    cursor = conn.cursor()
    cursor.execute("SET statement_timeout = '120s'")

    # Find processed_prices rows that DON'T have matching aliases
    # These are the rows that would be skipped by populate_observations

    print("=== Finding rows with missing product aliases ===")
    cursor.execute("""
        SELECT pp.product, pp.city, pp.category, pp.source_type, COUNT(*) as cnt
        FROM processed_prices pp
        LEFT JOIN alias_product ap ON ap.raw_value = pp.product
        WHERE ap.product_id IS NULL
          AND pp.product IS NOT NULL AND pp.product != ''
        GROUP BY pp.product, pp.city, pp.category, pp.source_type
        ORDER BY cnt DESC
    """)
    missing_products = cursor.fetchall()
    print(f"  {len(missing_products)} groups with missing product alias:")
    for row in missing_products:
        print(f"    product={row['product']!r} city={row['city']!r} cat={row['category']!r} src={row['source_type']} ({row['cnt']} rows)")

    print("\n=== Finding rows with missing city aliases ===")
    cursor.execute("""
        SELECT pp.city, pp.source_type, COUNT(*) as cnt
        FROM processed_prices pp
        LEFT JOIN alias_city ac ON ac.raw_value = pp.city
        WHERE ac.city_id IS NULL
          AND pp.city IS NOT NULL AND pp.city != ''
        GROUP BY pp.city, pp.source_type
        ORDER BY cnt DESC
    """)
    missing_cities = cursor.fetchall()
    print(f"  {len(missing_cities)} groups with missing city alias:")
    for row in missing_cities:
        print(f"    city={row['city']!r} src={row['source_type']} ({row['cnt']} rows)")

    print("\n=== Finding rows with empty/null city ===")
    cursor.execute("""
        SELECT pp.product, pp.city, pp.category, pp.source_type, COUNT(*) as cnt
        FROM processed_prices pp
        WHERE pp.city IS NULL OR pp.city = ''
        GROUP BY pp.product, pp.city, pp.category, pp.source_type
    """)
    empty_cities = cursor.fetchall()
    print(f"  {len(empty_cities)} groups with empty/null city:")
    for row in empty_cities:
        print(f"    product={row['product']!r} city={row['city']!r} ({row['cnt']} rows)")

    # Count total unmatched rows
    print("\n=== Total unmatched rows ===")
    cursor.execute("""
        SELECT COUNT(*) as cnt FROM processed_prices pp
        LEFT JOIN alias_product ap ON ap.raw_value = pp.product
        LEFT JOIN alias_city ac ON ac.raw_value = pp.city
        WHERE ap.product_id IS NULL
           OR ac.city_id IS NULL
           OR pp.city IS NULL OR pp.city = ''
    """)
    total = cursor.fetchone()['cnt']
    print(f"  Total rows that would be skipped: {total}")

    if fix and (missing_products or missing_cities):
        print("\n=== FIXING missing aliases ===")

        # For missing products: find best matching dim_product and create alias
        for row in missing_products:
            raw_product = row['product']
            # Try to find a close match in dim_product
            cursor.execute(
                "SELECT id, canonical_name FROM dim_product WHERE canonical_name ILIKE %s LIMIT 1",
                (raw_product,))
            match = cursor.fetchone()
            if match:
                print(f"  Creating product alias: {raw_product!r} -> {match['canonical_name']}")
                cursor.execute(
                    "INSERT INTO alias_product (raw_value, product_id) VALUES (%s, %s) ON CONFLICT DO NOTHING",
                    (raw_product, match['id']))
            else:
                print(f"  NO MATCH for product: {raw_product!r}")

        # For missing cities: find best matching dim_city and create alias
        for row in missing_cities:
            raw_city = row['city']
            cursor.execute(
                "SELECT id, canonical_name FROM dim_city WHERE canonical_name ILIKE %s LIMIT 1",
                (raw_city,))
            match = cursor.fetchone()
            if match:
                print(f"  Creating city alias: {raw_city!r} -> {match['canonical_name']}")
                cursor.execute(
                    "INSERT INTO alias_city (raw_value, city_id) VALUES (%s, %s) ON CONFLICT DO NOTHING",
                    (raw_city, match['id']))
            else:
                print(f"  NO MATCH for city: {raw_city!r}")

        conn.commit()
        print("  Changes committed.")
    else:
        print("\n  (Run with --fix to create missing aliases)")

    cursor.close()
    conn.close()


if __name__ == '__main__':
    fix = '--fix' in sys.argv
    run(fix=fix)
