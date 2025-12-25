"""
Dimension table generator for creating cleaned fact tables.

Reads reviewed TSV files and generates dimension tables with unique IDs.
"""

import os
from pathlib import Path
from typing import Dict, List, Optional

import pandas as pd

import sys

_parent_dir = str(Path(__file__).parent.parent)
if _parent_dir not in sys.path:
    sys.path.insert(0, _parent_dir)

from config import EXPORTS_DIR
from backend.supabase_client import get_db_connection
from cleaning.standardizer import Standardizer


def read_reviewed_tsv(filepath: Path) -> Optional[pd.DataFrame]:
    """Read a reviewed TSV file if it exists."""
    if not filepath.exists():
        print(f"  Warning: {filepath.name} not found")
        return None

    df = pd.read_csv(filepath, sep='\t')
    return df


def create_dimension_tables(conn):
    """Create dimension tables in the database."""
    cursor = conn.cursor()

    # Create dimension tables
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS dim_categories (
            id SERIAL PRIMARY KEY,
            name VARCHAR(200) NOT NULL UNIQUE,
            standardized_key VARCHAR(200) NOT NULL
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS dim_subcategories (
            id SERIAL PRIMARY KEY,
            category_id INTEGER REFERENCES dim_categories(id),
            name VARCHAR(200) NOT NULL,
            standardized_key VARCHAR(200) NOT NULL,
            UNIQUE(category_id, name)
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS dim_products (
            id SERIAL PRIMARY KEY,
            subcategory_id INTEGER REFERENCES dim_subcategories(id),
            name VARCHAR(300) NOT NULL,
            standardized_key VARCHAR(300) NOT NULL,
            UNIQUE(subcategory_id, name)
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS dim_presentations (
            id SERIAL PRIMARY KEY,
            name VARCHAR(200) NOT NULL UNIQUE,
            standardized_key VARCHAR(200) NOT NULL
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS dim_departments (
            id SERIAL PRIMARY KEY,
            codigo VARCHAR(2) NOT NULL UNIQUE,
            name VARCHAR(100) NOT NULL
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS dim_municipalities (
            id SERIAL PRIMARY KEY,
            department_id INTEGER REFERENCES dim_departments(id),
            codigo VARCHAR(5) NOT NULL UNIQUE,
            name VARCHAR(100) NOT NULL,
            standardized_key VARCHAR(100) NOT NULL,
            latitud DECIMAL(12, 8),
            longitud DECIMAL(12, 8)
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS dim_markets (
            id SERIAL PRIMARY KEY,
            municipality_id INTEGER REFERENCES dim_municipalities(id),
            name VARCHAR(200) NOT NULL,
            standardized_key VARCHAR(200) NOT NULL,
            UNIQUE(municipality_id, name)
        )
    """)

    # Create cleaned prices fact table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS cleaned_prices (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            product_id INTEGER REFERENCES dim_products(id),
            presentation_id INTEGER REFERENCES dim_presentations(id),
            market_id INTEGER REFERENCES dim_markets(id),
            price_date DATE NOT NULL,
            round INTEGER DEFAULT 1,
            min_price DECIMAL(12, 2),
            max_price DECIMAL(12, 2),
            source_type VARCHAR(20) NOT NULL,
            processed_price_id UUID,
            created_at TIMESTAMP DEFAULT NOW()
        )
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_cleaned_prices_product ON cleaned_prices(product_id)
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_cleaned_prices_market ON cleaned_prices(market_id)
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_cleaned_prices_date ON cleaned_prices(price_date)
    """)

    # Enable RLS
    for table in ['dim_categories', 'dim_subcategories', 'dim_products',
                  'dim_presentations', 'dim_departments', 'dim_municipalities',
                  'dim_markets', 'cleaned_prices']:
        cursor.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")

        # Public read access
        cursor.execute(f"""
            DROP POLICY IF EXISTS "Public read access for {table}" ON {table}
        """)
        cursor.execute(f"""
            CREATE POLICY "Public read access for {table}"
            ON {table} FOR SELECT
            USING (true)
        """)

        # Service role full access
        cursor.execute(f"""
            DROP POLICY IF EXISTS "Service role access for {table}" ON {table}
        """)
        cursor.execute(f"""
            CREATE POLICY "Service role access for {table}"
            ON {table} FOR ALL
            USING (auth.role() = 'service_role')
        """)

    conn.commit()
    cursor.close()


def populate_categories(conn, input_dir: Path) -> Dict[str, int]:
    """Populate dim_categories from reviewed TSV."""
    cursor = conn.cursor()
    category_map = {}

    tsv_path = input_dir / 'categories.tsv'
    df = read_reviewed_tsv(tsv_path)

    if df is None or df.empty:
        # Fall back to extracting from processed_prices
        cursor.execute("SELECT DISTINCT category FROM processed_prices WHERE category IS NOT NULL")
        categories = [row['category'] for row in cursor.fetchall()]

        for cat in categories:
            std = Standardizer.get_all_standardizations(cat, 'category')
            cursor.execute("""
                INSERT INTO dim_categories (name, standardized_key)
                VALUES (%s, %s)
                ON CONFLICT (name) DO NOTHING
                RETURNING id
            """, (std['standardized'], std['comparison_key']))

            result = cursor.fetchone()
            if result:
                category_map[cat] = result['id']
            else:
                cursor.execute("SELECT id FROM dim_categories WHERE name = %s", (std['standardized'],))
                result = cursor.fetchone()
                if result:
                    category_map[cat] = result['id']
    else:
        # Use reviewed data
        for _, row in df.iterrows():
            raw = row['raw_value']
            canonical = row.get('canonical_name') or row.get('standardized_value') or raw
            key = Standardizer.create_comparison_key(canonical)

            cursor.execute("""
                INSERT INTO dim_categories (name, standardized_key)
                VALUES (%s, %s)
                ON CONFLICT (name) DO NOTHING
                RETURNING id
            """, (canonical, key))

            result = cursor.fetchone()
            if result:
                category_map[raw] = result['id']
            else:
                cursor.execute("SELECT id FROM dim_categories WHERE name = %s", (canonical,))
                result = cursor.fetchone()
                if result:
                    category_map[raw] = result['id']

    conn.commit()
    cursor.close()

    print(f"  Populated {len(category_map)} categories")
    return category_map


def populate_departments_municipalities(conn) -> Dict[str, int]:
    """Populate dim_departments and dim_municipalities from DIVIPOLA."""
    cursor = conn.cursor()
    municipality_map = {}

    # Get DIVIPOLA data
    cursor.execute("SELECT * FROM divipola_municipios")
    divipola = cursor.fetchall()

    if not divipola:
        print("  Warning: No DIVIPOLA data found")
        return {}

    # Insert departments
    departments = {}
    for row in divipola:
        dept_code = row['codigo_departamento']
        if dept_code not in departments:
            cursor.execute("""
                INSERT INTO dim_departments (codigo, name)
                VALUES (%s, %s)
                ON CONFLICT (codigo) DO UPDATE SET name = EXCLUDED.name
                RETURNING id
            """, (dept_code, row['nombre_departamento']))
            result = cursor.fetchone()
            departments[dept_code] = result['id']

    # Insert municipalities
    for row in divipola:
        muni_code = row['codigo_municipio']
        dept_id = departments[row['codigo_departamento']]
        key = Standardizer.create_comparison_key(row['nombre_municipio'])

        cursor.execute("""
            INSERT INTO dim_municipalities (department_id, codigo, name, standardized_key, latitud, longitud)
            VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT (codigo) DO UPDATE SET
                name = EXCLUDED.name,
                standardized_key = EXCLUDED.standardized_key
            RETURNING id
        """, (dept_id, muni_code, row['nombre_municipio'], key,
              row.get('latitud'), row.get('longitud')))

        result = cursor.fetchone()
        municipality_map[row['nombre_municipio']] = result['id']

    conn.commit()
    cursor.close()

    print(f"  Populated {len(departments)} departments and {len(municipality_map)} municipalities")
    return municipality_map


def generate_dimensions(input_dir: str = None) -> int:
    """
    Generate dimension tables from reviewed data.

    Args:
        input_dir: Directory containing reviewed TSV files

    Returns:
        0 on success, 1 on error
    """
    print("=" * 60)
    print("Generating Dimension Tables")
    print("=" * 60)

    if input_dir:
        in_path = Path(input_dir)
    else:
        in_path = EXPORTS_DIR

    print(f"Input directory: {in_path}")

    try:
        conn = get_db_connection(new_connection=True)

        # Create tables
        print("\nCreating dimension tables...")
        create_dimension_tables(conn)

        # Populate dimensions
        print("\nPopulating dimensions...")

        print("  Loading departments and municipalities from DIVIPOLA...")
        municipality_map = populate_departments_municipalities(conn)

        print("  Loading categories...")
        category_map = populate_categories(conn, in_path)

        print("\n" + "=" * 60)
        print("Dimension Tables Created")
        print("=" * 60)
        print("\nNext steps:")
        print("1. Review the dimension tables in the database")
        print("2. Populate subcategories, products, presentations, and markets")
        print("3. Run the cleaned_prices population script")

        conn.close()
        return 0

    except Exception as e:
        print(f"\nError: {e}")
        return 1


if __name__ == '__main__':
    import sys
    sys.exit(generate_dimensions())
