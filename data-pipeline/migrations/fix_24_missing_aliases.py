#!/usr/bin/env python3
"""
Fix the 24 processed_prices rows that couldn't be joined due to missing aliases.
Creates alias_product entries mapping malformed raw values to correct dim_product entities.
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

from backend.supabase_client import get_db_connection

# Map: malformed raw_value -> correct canonical_name in dim_product
ALIAS_FIXES = {
    'Sardinas enlata': 'Sardinas en lata',
    'Aceitevegetalmezcla': 'Aceite vegetal mezcla',
    'Avena enhojuelas': 'Avena en hojuelas',
    'Lomitos de atún enlata': 'Lomitos de atún en lata',
    'Aceite depalma': 'Aceite de palma',
    'Jugo instantáneo(sobre)': 'Jugo instantáneo (sobre)',
    'Bocachico importado congelad': 'Bocachico importado congelado',
    'Name criollo': 'Ñame criollo',
    'Name diamante': 'Ñame diamante',
    'Name espino': 'Ñame espino',
    'FFrrííjjooll ccaarrggaammaannttoo rroojjoo': 'Fríjol cargamanto rojo',
    'HHuueevvoo bbllaannccoo AA': 'Huevo blanco A',
}


def run(dry_run=False):
    conn = get_db_connection(new_connection=True)
    cursor = conn.cursor()

    created = 0
    for raw_value, canonical in ALIAS_FIXES.items():
        # Find the dim_product id for the canonical name
        cursor.execute(
            "SELECT id FROM dim_product WHERE canonical_name = %s", (canonical,))
        row = cursor.fetchone()
        if not row:
            # Try case-insensitive
            cursor.execute(
                "SELECT id, canonical_name FROM dim_product WHERE canonical_name ILIKE %s",
                (canonical,))
            row = cursor.fetchone()
            if row:
                print(f"  Found case-insensitive: {canonical!r} -> {row['canonical_name']!r}")
            else:
                print(f"  ERROR: No dim_product for {canonical!r}")
                continue

        product_id = row['id']
        print(f"  {raw_value!r} -> {canonical} (id={str(product_id)[:8]}...)")

        if not dry_run:
            cursor.execute(
                "INSERT INTO alias_product (raw_value, product_id) VALUES (%s, %s) "
                "ON CONFLICT (raw_value) DO NOTHING",
                (raw_value, product_id))
            created += 1

    if dry_run:
        conn.rollback()
        print(f"\nDry run: {created} aliases would be created")
    else:
        conn.commit()
        print(f"\nCreated {created} aliases")

    # Now re-run the observation INSERT for the previously-skipped rows
    if not dry_run:
        print("\n=== Re-inserting skipped observations ===")
        cursor.execute("SET statement_timeout = '120s'")

        # Insert observations for rows that now have aliases but didn't before
        cursor.execute("""
            INSERT INTO price_observations (
                price_date, round, min_price, max_price, avg_price,
                category_id, subcategory_id, product_id,
                presentation_id, units_id,
                department_id, city_id, market_id,
                source_type, source_path,
                download_entry_id, extracted_pdf_id, processed_price_id
            )
            SELECT
                pp.price_date, pp.round, pp.min_price, pp.max_price, pp.avg_price,
                s.category_id,
                p.subcategory_id,
                ap.product_id,
                apres.presentation_id,
                au.units_id,
                c.department_id,
                ac.city_id,
                am.market_id,
                pp.source_type, pp.source_path,
                pp.download_entry_id, pp.extracted_pdf_id, pp.id
            FROM processed_prices pp
            JOIN alias_product ap ON ap.raw_value = pp.product
            JOIN dim_product p ON p.id = ap.product_id
            JOIN dim_subcategory s ON s.id = p.subcategory_id
            JOIN alias_city ac ON ac.raw_value = pp.city
            JOIN dim_city c ON c.id = ac.city_id
            LEFT JOIN alias_market am ON am.raw_value = pp.market AND pp.market != ''
            LEFT JOIN alias_presentation apres ON apres.raw_value = pp.presentation AND pp.presentation != ''
            LEFT JOIN alias_units au ON au.raw_value = pp.units AND pp.units != ''
            WHERE pp.product IN (%s)
              AND NOT EXISTS (
                  SELECT 1 FROM price_observations po
                  WHERE po.processed_price_id = pp.id
              )
        """ % ','.join(["'%s'" % v.replace("'", "''") for v in ALIAS_FIXES.keys()]))

        inserted = cursor.rowcount
        conn.commit()
        print(f"  Inserted {inserted} observations for previously-skipped rows")

    cursor.close()
    conn.close()


if __name__ == '__main__':
    dry_run = '--dry-run' in sys.argv
    run(dry_run=dry_run)
