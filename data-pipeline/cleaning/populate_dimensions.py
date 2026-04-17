#!/usr/bin/env python3
"""
Populate dimension tables from processed_prices data.

Extracts all unique raw strings, normalizes them into canonical entities,
creates alias mappings, and populates price_observations with UUID references.

Usage:
    python -m cleaning.populate_dimensions [--dry-run] [--skip-observations]
"""

import os
import re
import sys
import unicodedata
from collections import defaultdict
from datetime import datetime
from pathlib import Path

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

from backend.supabase_client import get_db_connection


# ============================================================
# STRING NORMALIZATION
# ============================================================

def fix_encoding(s: str) -> str:
    """
    Fix common encoding issues in SIPSA data.

    The PDF parser sometimes produces uppercase accented characters
    (e.g., "CÍtricos" instead of "Cítricos") due to encoding mismatches.
    """
    # Map of incorrectly-cased accented chars to their correct form
    fixes = {
        'Á': 'á', 'É': 'é', 'Í': 'í', 'Ó': 'ó', 'Ú': 'ú',
        'Ñ': 'ñ',
    }
    result = s
    # Only fix mid-word uppercase accented chars (not at start of word)
    for i, ch in enumerate(result):
        if ch in fixes and i > 0 and result[i-1].isalpha() and result[i-1].islower():
            result = result[:i] + fixes[ch] + result[i+1:]
    return result


def normalize_string(s: str) -> str:
    """Normalize a string for comparison: fix encoding, strip, collapse whitespace."""
    if not s:
        return ''
    s = fix_encoding(s.strip())
    s = re.sub(r'\s+', ' ', s)
    return s


# ============================================================
# KNOWN ENTITY MERGES
# Hard-coded mappings for known variants that can't be resolved
# by string normalization alone.
# ============================================================

# City canonical names and their raw variants
# Format: canonical -> [raw variants that map to it]
CITY_MERGES = {
    'Bogotá, D.C.': ['Bogotá', 'Bogotá D.C.', 'Bogotá, D.C.'],
    'Bucaramanga': ['Bucaramanga', 'Bucaramanga Centroabastos'],
    'Cúcuta': ['Cúcuta', 'Cúcuta Cenabastos'],
    'Ibagué': ['Ibagué', 'Ibagué Plaza La 21'],
    'San Vicente Ferrer': ['San Vicente', 'San Vicente Ferrer'],
    'Villavicencio': ['Villavicencio', 'Villavicencio CAV'],
}

# Market canonical names and their raw variants
MARKET_MERGES = {
    'El Potrerillo': ['El Potrerillo', 'El Potrerrillo', 'Potrerillo'],
    'Plaza La 21': ['Plaza La 21', 'Plaza la 21', 'Plaza la  21', 'La 21'],
    'Centro Galerías': ['Centro Galerías', 'Centro Galerias'],
    'Central Mayorista de Antioquia': ['Central Mayorista de Antioquia', 'Central Mayorista'],
    'Santa Elena': ['Santa Elena', 'Santa Helena'],
}

# Category canonical names and their raw variants
# Only includes the real SIPSA categories, not junk data
CATEGORY_MERGES = {
    'Frutas': ['Frutas', 'Frutas frescas', 'FRUTAS FRESCAS'],
    'Verduras y hortalizas': ['Verduras y hortalizas', 'Hortalizas y verduras'],
    'Tubérculos, raíces y plátanos': [
        'Tuberculos, raices y platanos',
        'Tubérculos, raíces y plátanos',
        'Tubérculos y plátanos',
        'Tubérculos, plátanos',
        'Tubérculos, raíes y plátanos',
    ],
    'Procesados': ['Procesados'],
    'Carnes': ['Carnes'],
    'Granos y cereales': ['Granos y cereales'],
    'Pescados': ['Pescados'],
    'Lácteos y huevos': ['Lacteos y huevos', 'Lácteos y huevos'],
}

# Subcategory encoding fixes (canonical -> raw variants)
SUBCATEGORY_MERGES = {
    'Cítricos': ['CÍtricos', 'Cítricos'],
    'Plátano': ['PlÁtano', 'Plátano'],
    'Lácteos': ['LÁcteos', 'Lácteos'],
    'Azúcar': ['AzÚcar', 'Azúcar'],
}

# Presentation encoding fixes
PRESENTATION_MERGES = {
    'Caja de cartón': ['Caja de cartÓn', 'Caja de cartón'],
}

# City -> Divipola municipality name mapping (for divipola_code lookup)
CITY_TO_DIVIPOLA = {
    'Bogotá, D.C.': 'BOGOTÁ, D.C.',
    'Cali': 'SANTIAGO DE CALI',
    'Cartagena': 'CARTAGENA DE INDIAS',
    'Cúcuta': 'SAN JOSÉ DE CÚCUTA',
    'Armenia': ('ARMENIA', 'QUINDÍO'),  # Disambiguate: Quindío not Antioquia
    'Florencia': ('FLORENCIA', 'CAQUETÁ'),
    'La Unión': ('LA UNIÓN', 'VALLE DEL CAUCA'),
    'Rionegro': ('RIONEGRO', 'ANTIOQUIA'),
    'Santa Bárbara': ('SANTA BÁRBARA', 'ANTIOQUIA'),
}

# Market -> City mapping (for markets that appear in city-embedded variants)
MARKET_CITY_OVERRIDES = {
    # When city is "Bucaramanga Centroabastos", market is Centroabastos
    'Centroabastos_from_Bucaramanga Centroabastos': ('Centroabastos', 'Bucaramanga'),
    'Cenabastos_from_Cúcuta Cenabastos': ('Cenabastos', 'Cúcuta'),
    'Plaza La 21_from_Ibagué Plaza La 21': ('Plaza La 21', 'Ibagué'),
    'CAV_from_Villavicencio CAV': ('CAV', 'Villavicencio'),
}

# Junk city values to exclude
JUNK_CITIES = {
    'PRODUCTOS DE PRIMERA CALIDAD - BOLETIN GRATUITO',
}

# Known valid categories (only records with these categories will be included)
VALID_CATEGORIES = set()
for variants in CATEGORY_MERGES.values():
    VALID_CATEGORIES.update(variants)


# ============================================================
# DIMENSION POPULATION
# ============================================================

class DimensionPopulator:
    """Populates dimension tables from processed_prices data."""

    def __init__(self, dry_run=False):
        self.dry_run = dry_run
        self.conn = get_db_connection(new_connection=True)
        self.cursor = self.conn.cursor()

        # Caches for created IDs
        self.department_ids = {}   # canonical_name -> uuid
        self.city_ids = {}         # canonical_name -> uuid
        self.market_ids = {}       # canonical_name -> uuid
        self.category_ids = {}     # canonical_name -> uuid
        self.subcategory_ids = {}  # canonical_name -> uuid
        self.product_ids = {}      # canonical_name -> uuid
        self.presentation_ids = {} # canonical_name -> uuid
        self.units_ids = {}        # canonical_name -> uuid

        # Alias caches (raw_value -> dimension_id)
        self.city_alias = {}
        self.market_alias = {}
        self.category_alias = {}
        self.subcategory_alias = {}
        self.product_alias = {}
        self.presentation_alias = {}
        self.units_alias = {}

    def run(self, skip_observations=False):
        """Run the full population pipeline."""
        print("=" * 60)
        print("Dimension Table Population")
        print("=" * 60)
        if self.dry_run:
            print("Mode: DRY RUN")

        try:
            self._populate_geography()
            self._populate_product_taxonomy()
            self._populate_presentations()
            self._populate_units()

            if not skip_observations:
                self._populate_observations()

            if not self.dry_run:
                self.conn.commit()
                print("\nAll changes committed.")
            else:
                self.conn.rollback()
                print("\nDry run - all changes rolled back.")

        except Exception as e:
            self.conn.rollback()
            raise e
        finally:
            self.cursor.close()
            self.conn.close()

    # ==================== GEOGRAPHY ====================

    def _populate_geography(self):
        """Populate departments, cities, markets and their aliases."""
        print("\n--- Geography Dimensions ---")

        # Load divipola data
        self.cursor.execute("""
            SELECT nombre_municipio, nombre_departamento, codigo_municipio, codigo_departamento
            FROM divipola_municipios
        """)
        divipola = {row['nombre_municipio']: row for row in self.cursor.fetchall()}

        # Get all unique city and market values from processed_prices
        self.cursor.execute("""
            SELECT DISTINCT city FROM processed_prices WHERE city != '' AND city IS NOT NULL
        """)
        raw_cities = sorted(set(row['city'] for row in self.cursor.fetchall()))

        self.cursor.execute("""
            SELECT DISTINCT market FROM processed_prices WHERE market != '' AND market IS NOT NULL
        """)
        raw_markets = sorted(set(row['market'] for row in self.cursor.fetchall()))

        # Get city-market pairs for hierarchy inference
        self.cursor.execute("""
            SELECT city, market, COUNT(*) as cnt
            FROM processed_prices
            WHERE city != '' AND market != ''
            GROUP BY city, market
        """)
        city_market_pairs = {}
        for row in self.cursor.fetchall():
            key = row['market']
            if key not in city_market_pairs or row['cnt'] > city_market_pairs[key][1]:
                city_market_pairs[key] = (row['city'], row['cnt'])

        # Build canonical city -> raw variants mapping
        city_to_raw = defaultdict(set)
        raw_to_canonical_city = {}

        for canonical, variants in CITY_MERGES.items():
            for v in variants:
                city_to_raw[canonical].add(v)
                raw_to_canonical_city[v] = canonical

        # Cities not in merge list get their own canonical entry
        for raw in raw_cities:
            if raw in JUNK_CITIES:
                continue
            if raw not in raw_to_canonical_city:
                normalized = normalize_string(raw)
                city_to_raw[normalized].add(raw)
                raw_to_canonical_city[raw] = normalized

        # Build canonical market -> raw variants mapping
        market_to_raw = defaultdict(set)
        raw_to_canonical_market = {}

        for canonical, variants in MARKET_MERGES.items():
            for v in variants:
                market_to_raw[canonical].add(v)
                raw_to_canonical_market[v] = canonical

        for raw in raw_markets:
            if raw not in raw_to_canonical_market:
                normalized = normalize_string(raw)
                market_to_raw[normalized].add(raw)
                raw_to_canonical_market[raw] = normalized

        # Step 1: Create departments
        departments_needed = set()
        for canonical_city in city_to_raw:
            dept = self._lookup_department(canonical_city, divipola)
            if dept:
                departments_needed.add(dept)

        print(f"  Departments: {len(departments_needed)}")
        for dept_name, dept_code in departments_needed:
            self._create_department(dept_name, dept_code)

        # Step 2: Create cities
        print(f"  Cities: {len(city_to_raw)}")
        for canonical_city in sorted(city_to_raw):
            dept_info = self._lookup_department(canonical_city, divipola)
            if not dept_info:
                print(f"    [WARN] No department for city: {canonical_city}")
                # Create an "Unknown" department
                dept_info = ('Desconocido', None)
                if 'Desconocido' not in self.department_ids:
                    self._create_department('Desconocido', None)

            dept_name = dept_info[0]
            dept_id = self.department_ids[dept_name]
            divipola_code = self._lookup_divipola_code(canonical_city, divipola)

            self._create_city(canonical_city, dept_id, divipola_code)

            # Create aliases
            for raw in city_to_raw[canonical_city]:
                self.city_alias[raw] = self.city_ids[canonical_city]
                self._create_alias('alias_city', raw, 'city_id', self.city_ids[canonical_city])

        # Step 3: Create markets
        print(f"  Markets: {len(market_to_raw)}")
        for canonical_market in sorted(market_to_raw):
            # Determine which city this market belongs to
            city_for_market = self._infer_market_city(
                canonical_market, market_to_raw[canonical_market],
                city_market_pairs, raw_to_canonical_city
            )
            if not city_for_market or city_for_market not in self.city_ids:
                print(f"    [WARN] No city for market: {canonical_market}")
                continue

            city_id = self.city_ids[city_for_market]
            self._create_market(canonical_market, city_id)

            for raw in market_to_raw[canonical_market]:
                self.market_alias[raw] = self.market_ids[canonical_market]
                self._create_alias('alias_market', raw, 'market_id', self.market_ids[canonical_market])

        # Step 4: Ensure every city has a "Mercado municipal de X" fallback market
        # This is used when PDF data has a city but no market name
        muni_created = 0
        for canonical_city in sorted(city_to_raw):
            city_id = self.city_ids.get(canonical_city)
            if not city_id:
                continue
            muni_name = f"Mercado municipal de {canonical_city}"
            if muni_name not in self.market_ids:
                self._create_market(muni_name, city_id)
                muni_created += 1
        if muni_created > 0:
            print(f"  Municipal market fallbacks created: {muni_created}")

        self._flush_aliases()
        print(f"  City aliases: {len(self.city_alias)}")
        print(f"  Market aliases: {len(self.market_alias)}")

    def _lookup_department(self, city_name, divipola):
        """Look up department for a city using divipola data."""
        # Check manual overrides first
        if city_name in CITY_TO_DIVIPOLA:
            val = CITY_TO_DIVIPOLA[city_name]
            if isinstance(val, tuple):
                muni_name, dept_name = val
                # Find the divipola entry
                for k, v in divipola.items():
                    if k.upper() == muni_name.upper() and v['nombre_departamento'].upper() == dept_name.upper():
                        return (v['nombre_departamento'], v['codigo_departamento'])
            else:
                # Simple name mapping
                for k, v in divipola.items():
                    if k.upper() == val.upper():
                        return (v['nombre_departamento'], v['codigo_departamento'])

        # Try direct match
        for k, v in divipola.items():
            if k.upper() == city_name.upper():
                return (v['nombre_departamento'], v['codigo_departamento'])

        # Try without accents
        city_norm = self._strip_accents(city_name).lower()
        for k, v in divipola.items():
            if self._strip_accents(k).lower() == city_norm:
                return (v['nombre_departamento'], v['codigo_departamento'])

        return None

    def _lookup_divipola_code(self, city_name, divipola):
        """Look up divipola municipality code for a city."""
        if city_name in CITY_TO_DIVIPOLA:
            val = CITY_TO_DIVIPOLA[city_name]
            if isinstance(val, tuple):
                muni_name, dept_name = val
                for k, v in divipola.items():
                    if k.upper() == muni_name.upper() and v['nombre_departamento'].upper() == dept_name.upper():
                        return v['codigo_municipio']
            else:
                for k, v in divipola.items():
                    if k.upper() == val.upper():
                        return v['codigo_municipio']

        for k, v in divipola.items():
            if k.upper() == city_name.upper():
                return v['codigo_municipio']

        return None

    def _strip_accents(self, s):
        """Remove accent marks from a string."""
        nfkd = unicodedata.normalize('NFKD', s)
        return ''.join(c for c in nfkd if not unicodedata.combining(c))

    def _infer_market_city(self, canonical_market, raw_variants, city_market_pairs, raw_to_canonical_city):
        """Determine which canonical city a market belongs to."""
        # Check city-market pairs: find the most frequent city for any raw variant
        best_city = None
        best_count = 0
        for raw_market in raw_variants:
            if raw_market in city_market_pairs:
                raw_city, count = city_market_pairs[raw_market]
                if count > best_count:
                    best_count = count
                    canonical_city = raw_to_canonical_city.get(raw_city, raw_city)
                    if canonical_city not in JUNK_CITIES:
                        best_city = canonical_city

        return best_city

    # ==================== PRODUCT TAXONOMY ====================

    def _populate_product_taxonomy(self):
        """Populate categories, subcategories, products and their aliases."""
        print("\n--- Product Taxonomy Dimensions ---")

        # Step 1: Create categories
        category_to_raw = defaultdict(set)
        raw_to_canonical_category = {}

        for canonical, variants in CATEGORY_MERGES.items():
            for v in variants:
                category_to_raw[canonical].add(v)
                raw_to_canonical_category[v] = canonical

        print(f"  Categories: {len(category_to_raw)}")
        for canonical in sorted(category_to_raw):
            self._create_category(canonical)
            for raw in category_to_raw[canonical]:
                self.category_alias[raw] = self.category_ids[canonical]
                self._create_alias('alias_category', raw, 'category_id', self.category_ids[canonical])

        # Step 2: Create subcategories
        # Get all category-subcategory pairs from data (only for valid categories)
        valid_cat_clause = ','.join(f"'{c}'" for c in VALID_CATEGORIES)
        self.cursor.execute(f"""
            SELECT category, subcategory, COUNT(*) as cnt
            FROM processed_prices
            WHERE subcategory != '' AND subcategory IS NOT NULL
              AND category IN ({valid_cat_clause})
            GROUP BY category, subcategory
            ORDER BY cnt DESC
        """)

        subcat_to_raw = defaultdict(set)
        raw_to_canonical_subcat = {}
        subcat_to_category = {}  # canonical_subcat -> canonical_category

        # Apply known merges first
        for canonical, variants in SUBCATEGORY_MERGES.items():
            for v in variants:
                subcat_to_raw[canonical].add(v)
                raw_to_canonical_subcat[v] = canonical

        for row in self.cursor.fetchall():
            raw_subcat = row['subcategory']
            raw_cat = row['category']
            canonical_cat = raw_to_canonical_category.get(raw_cat)
            if not canonical_cat:
                continue

            canonical_subcat = raw_to_canonical_subcat.get(raw_subcat, normalize_string(raw_subcat))
            subcat_to_raw[canonical_subcat].add(raw_subcat)
            raw_to_canonical_subcat[raw_subcat] = canonical_subcat

            # Assign category (use highest-frequency mapping)
            if canonical_subcat not in subcat_to_category:
                subcat_to_category[canonical_subcat] = canonical_cat

        # Add a catch-all subcategory per category for Excel records (no subcategory)
        for canonical_cat in category_to_raw:
            fallback = f"General ({canonical_cat})"
            subcat_to_raw[fallback] = set()
            subcat_to_category[fallback] = canonical_cat

        print(f"  Subcategories: {len(subcat_to_raw)}")
        for canonical_subcat in sorted(subcat_to_raw):
            cat_name = subcat_to_category.get(canonical_subcat)
            if not cat_name or cat_name not in self.category_ids:
                continue
            cat_id = self.category_ids[cat_name]
            self._create_subcategory(canonical_subcat, cat_id)

            for raw in subcat_to_raw[canonical_subcat]:
                self.subcategory_alias[raw] = self.subcategory_ids[canonical_subcat]
                self._create_alias('alias_subcategory', raw, 'subcategory_id', self.subcategory_ids[canonical_subcat])

        # Step 3: Create products
        # Get all product-subcategory-category triples
        self.cursor.execute(f"""
            SELECT product, subcategory, category, COUNT(*) as cnt
            FROM processed_prices
            WHERE product != '' AND product IS NOT NULL
              AND category IN ({valid_cat_clause})
            GROUP BY product, subcategory, category
            ORDER BY product, cnt DESC
        """)

        product_to_raw = defaultdict(set)
        raw_to_canonical_product = {}
        product_to_subcategory = {}  # canonical_product -> canonical_subcategory

        for row in self.cursor.fetchall():
            raw_product = row['product']
            raw_subcat = row['subcategory'] or ''
            raw_cat = row['category']

            canonical_product = normalize_string(raw_product)
            product_to_raw[canonical_product].add(raw_product)
            raw_to_canonical_product[raw_product] = canonical_product

            # Determine subcategory for this product
            if canonical_product not in product_to_subcategory:
                canonical_cat = raw_to_canonical_category.get(raw_cat)
                if raw_subcat:
                    canonical_subcat = raw_to_canonical_subcat.get(raw_subcat, normalize_string(raw_subcat))
                else:
                    # Excel records without subcategory -> use fallback
                    canonical_subcat = f"General ({canonical_cat})" if canonical_cat else None

                if canonical_subcat and canonical_subcat in self.subcategory_ids:
                    product_to_subcategory[canonical_product] = canonical_subcat

        # Also include products that only appear in records with invalid categories
        # but match a known product from valid records
        self.cursor.execute(f"""
            SELECT DISTINCT product
            FROM processed_prices
            WHERE product != '' AND product IS NOT NULL
              AND category NOT IN ({valid_cat_clause})
        """)
        for row in self.cursor.fetchall():
            raw_product = row['product']
            canonical_product = normalize_string(raw_product)
            if canonical_product in product_to_subcategory:
                # Already known from valid records
                product_to_raw[canonical_product].add(raw_product)
                raw_to_canonical_product[raw_product] = canonical_product

        print(f"  Products: {len(product_to_raw)}")
        # Batch insert products
        product_inserts = []  # (canonical, subcat_id)
        for canonical_product in sorted(product_to_raw):
            subcat_name = product_to_subcategory.get(canonical_product)
            if not subcat_name or subcat_name not in self.subcategory_ids:
                continue
            subcat_id = self.subcategory_ids[subcat_name]
            product_inserts.append((canonical_product, subcat_id))

        if product_inserts and not self.dry_run:
            chunk_size = 500
            for i in range(0, len(product_inserts), chunk_size):
                chunk = product_inserts[i:i+chunk_size]
                values_sql = ','.join(
                    self.cursor.mogrify("(%s, %s)", (name, sid)).decode()
                    for name, sid in chunk
                )
                self.cursor.execute(
                    f"INSERT INTO dim_product (canonical_name, subcategory_id) VALUES {values_sql} "
                    f"ON CONFLICT (canonical_name) DO NOTHING"
                )
            # Fetch all IDs
            self.cursor.execute("SELECT id, canonical_name FROM dim_product")
            for row in self.cursor.fetchall():
                self.product_ids[row['canonical_name']] = row['id']
        elif self.dry_run:
            for name, _ in product_inserts:
                self.product_ids[name] = f"dry-run-{name}"

        for canonical_product in sorted(product_to_raw):
            if canonical_product not in self.product_ids:
                continue
            for raw in product_to_raw[canonical_product]:
                self.product_alias[raw] = self.product_ids[canonical_product]
                self._create_alias('alias_product', raw, 'product_id', self.product_ids[canonical_product])

        self._flush_aliases()
        print(f"  Category aliases: {len(self.category_alias)}")
        print(f"  Subcategory aliases: {len(self.subcategory_alias)}")
        print(f"  Product aliases: {len(self.product_alias)}")

    # ==================== PRESENTATIONS & UNITS ====================

    def _populate_presentations(self):
        """Populate presentations and their aliases."""
        print("\n--- Presentation Dimension ---")

        self.cursor.execute("""
            SELECT DISTINCT presentation
            FROM processed_prices
            WHERE presentation != '' AND presentation IS NOT NULL
        """)
        raw_values = sorted(set(row['presentation'] for row in self.cursor.fetchall()))

        pres_to_raw = defaultdict(set)
        raw_to_canonical = {}

        for canonical, variants in PRESENTATION_MERGES.items():
            for v in variants:
                pres_to_raw[canonical].add(v)
                raw_to_canonical[v] = canonical

        for raw in raw_values:
            if raw not in raw_to_canonical:
                canonical = normalize_string(raw)
                pres_to_raw[canonical].add(raw)
                raw_to_canonical[raw] = canonical

        print(f"  Presentations: {len(pres_to_raw)}")
        # Batch insert all presentations
        self._batch_create_simple_dim('dim_presentation', sorted(pres_to_raw.keys()), self.presentation_ids)
        for canonical in sorted(pres_to_raw):
            for raw in pres_to_raw[canonical]:
                self.presentation_alias[raw] = self.presentation_ids[canonical]
                self._create_alias('alias_presentation', raw, 'presentation_id', self.presentation_ids[canonical])
        self._flush_aliases()

    def _populate_units(self):
        """Populate units and their aliases."""
        print("\n--- Units Dimension ---")

        self.cursor.execute("""
            SELECT DISTINCT units
            FROM processed_prices
            WHERE units != '' AND units IS NOT NULL
        """)
        raw_values = sorted(set(row['units'] for row in self.cursor.fetchall()))

        units_to_raw = defaultdict(set)
        raw_to_canonical = {}

        for raw in raw_values:
            canonical = normalize_string(raw)
            units_to_raw[canonical].add(raw)
            raw_to_canonical[raw] = canonical

        print(f"  Units: {len(units_to_raw)}")
        # Batch insert all units
        self._batch_create_simple_dim('dim_units', sorted(units_to_raw.keys()), self.units_ids)
        for canonical in sorted(units_to_raw):
            for raw in units_to_raw[canonical]:
                self.units_alias[raw] = self.units_ids[canonical]
                self._create_alias('alias_units', raw, 'units_id', self.units_ids[canonical])
        self._flush_aliases()

    # ==================== PRICE OBSERVATIONS ====================

    def _populate_observations(self):
        """Populate price_observations using server-side INSERT...SELECT for performance."""
        print("\n--- Populating price_observations ---")

        if self.dry_run:
            print("  [DRY-RUN] Skipping observation population")
            return

        # Count total records
        self.cursor.execute("SELECT COUNT(*) FROM processed_prices")
        total = self.cursor.fetchone()['count']
        print(f"  Total processed_prices records: {total}")

        # Use server-side INSERT...SELECT with JOINs on alias tables
        # Batch by month to avoid statement timeout on Supabase
        print("  Running server-side INSERT...SELECT in monthly batches...")

        # Increase statement timeout for this connection
        self.cursor.execute("SET statement_timeout = '300s'")

        # Get date range
        self.cursor.execute("SELECT MIN(price_date) as min_d, MAX(price_date) as max_d FROM processed_prices")
        row = self.cursor.fetchone()
        min_date = row['min_d']
        max_date = row['max_d']
        print(f"  Date range: {min_date} to {max_date}")

        total_inserted = 0
        from datetime import date as date_type
        import calendar

        current = date_type(min_date.year, min_date.month, 1)
        end = date_type(max_date.year, max_date.month, 1)

        while current <= end:
            last_day = calendar.monthrange(current.year, current.month)[1]
            month_end = date_type(current.year, current.month, last_day)

            self.cursor.execute("""
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
                    COALESCE(am.market_id, muni.id) as market_id,
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
                LEFT JOIN dim_market muni ON muni.city_id = ac.city_id
                    AND muni.canonical_name LIKE 'Mercado municipal de %%'
                    AND am.market_id IS NULL
                WHERE pp.price_date >= %s AND pp.price_date <= %s
            """, (current.isoformat(), month_end.isoformat()))

            batch_count = self.cursor.rowcount
            total_inserted += batch_count
            self.conn.commit()

            if batch_count > 0:
                print(f"  {current.strftime('%Y-%m')}: {batch_count} observations")

            # Next month
            if current.month == 12:
                current = date_type(current.year + 1, 1, 1)
            else:
                current = date_type(current.year, current.month + 1, 1)

        print(f"\n  Total inserted: {total_inserted} observations")
        print(f"  Skipped (no matching dimensions): {total - total_inserted}")

    # ==================== DB HELPERS ====================

    def _create_department(self, name, divipola_code):
        if name in self.department_ids:
            return
        if self.dry_run:
            self.department_ids[name] = f"dry-run-{name}"
            return
        self.cursor.execute(
            "INSERT INTO dim_department (canonical_name, divipola_code) VALUES (%s, %s) "
            "ON CONFLICT (canonical_name) DO NOTHING RETURNING id",
            (name, divipola_code)
        )
        result = self.cursor.fetchone()
        if result:
            self.department_ids[name] = result['id']
        else:
            self.cursor.execute(
                "SELECT id FROM dim_department WHERE canonical_name = %s", (name,)
            )
            self.department_ids[name] = self.cursor.fetchone()['id']

    def _create_city(self, name, department_id, divipola_code):
        if name in self.city_ids:
            return
        if self.dry_run:
            self.city_ids[name] = f"dry-run-{name}"
            return
        self.cursor.execute(
            "INSERT INTO dim_city (canonical_name, department_id, divipola_code) VALUES (%s, %s, %s) "
            "ON CONFLICT (canonical_name) DO NOTHING RETURNING id",
            (name, department_id, divipola_code)
        )
        result = self.cursor.fetchone()
        if result:
            self.city_ids[name] = result['id']
        else:
            self.cursor.execute(
                "SELECT id FROM dim_city WHERE canonical_name = %s", (name,)
            )
            self.city_ids[name] = self.cursor.fetchone()['id']

    def _create_market(self, name, city_id):
        if name in self.market_ids:
            return
        if self.dry_run:
            self.market_ids[name] = f"dry-run-{name}"
            return
        self.cursor.execute(
            "INSERT INTO dim_market (canonical_name, city_id) VALUES (%s, %s) "
            "ON CONFLICT (canonical_name) DO NOTHING RETURNING id",
            (name, city_id)
        )
        result = self.cursor.fetchone()
        if result:
            self.market_ids[name] = result['id']
        else:
            self.cursor.execute(
                "SELECT id FROM dim_market WHERE canonical_name = %s", (name,)
            )
            self.market_ids[name] = self.cursor.fetchone()['id']

    def _create_category(self, name):
        if name in self.category_ids:
            return
        if self.dry_run:
            self.category_ids[name] = f"dry-run-{name}"
            return
        self.cursor.execute(
            "INSERT INTO dim_category (canonical_name) VALUES (%s) "
            "ON CONFLICT (canonical_name) DO NOTHING RETURNING id",
            (name,)
        )
        result = self.cursor.fetchone()
        if result:
            self.category_ids[name] = result['id']
        else:
            self.cursor.execute(
                "SELECT id FROM dim_category WHERE canonical_name = %s", (name,)
            )
            self.category_ids[name] = self.cursor.fetchone()['id']

    def _create_subcategory(self, name, category_id):
        if name in self.subcategory_ids:
            return
        if self.dry_run:
            self.subcategory_ids[name] = f"dry-run-{name}"
            return
        self.cursor.execute(
            "INSERT INTO dim_subcategory (canonical_name, category_id) VALUES (%s, %s) "
            "ON CONFLICT (canonical_name) DO NOTHING RETURNING id",
            (name, category_id)
        )
        result = self.cursor.fetchone()
        if result:
            self.subcategory_ids[name] = result['id']
        else:
            self.cursor.execute(
                "SELECT id FROM dim_subcategory WHERE canonical_name = %s", (name,)
            )
            self.subcategory_ids[name] = self.cursor.fetchone()['id']

    def _create_product(self, name, subcategory_id):
        if name in self.product_ids:
            return
        if self.dry_run:
            self.product_ids[name] = f"dry-run-{name}"
            return
        self.cursor.execute(
            "INSERT INTO dim_product (canonical_name, subcategory_id) VALUES (%s, %s) "
            "ON CONFLICT (canonical_name) DO NOTHING RETURNING id",
            (name, subcategory_id)
        )
        result = self.cursor.fetchone()
        if result:
            self.product_ids[name] = result['id']
        else:
            self.cursor.execute(
                "SELECT id FROM dim_product WHERE canonical_name = %s", (name,)
            )
            self.product_ids[name] = self.cursor.fetchone()['id']

    def _create_presentation(self, name):
        if name in self.presentation_ids:
            return
        if self.dry_run:
            self.presentation_ids[name] = f"dry-run-{name}"
            return
        self.cursor.execute(
            "INSERT INTO dim_presentation (canonical_name) VALUES (%s) "
            "ON CONFLICT (canonical_name) DO NOTHING RETURNING id",
            (name,)
        )
        result = self.cursor.fetchone()
        if result:
            self.presentation_ids[name] = result['id']
        else:
            self.cursor.execute(
                "SELECT id FROM dim_presentation WHERE canonical_name = %s", (name,)
            )
            self.presentation_ids[name] = self.cursor.fetchone()['id']

    def _create_units(self, name):
        if name in self.units_ids:
            return
        if self.dry_run:
            self.units_ids[name] = f"dry-run-{name}"
            return
        self.cursor.execute(
            "INSERT INTO dim_units (canonical_name) VALUES (%s) "
            "ON CONFLICT (canonical_name) DO NOTHING RETURNING id",
            (name,)
        )
        result = self.cursor.fetchone()
        if result:
            self.units_ids[name] = result['id']
        else:
            self.cursor.execute(
                "SELECT id FROM dim_units WHERE canonical_name = %s", (name,)
            )
            self.units_ids[name] = self.cursor.fetchone()['id']

    def _create_alias(self, table, raw_value, fk_column, fk_id):
        """Buffer an alias mapping entry for batch insert."""
        if self.dry_run:
            return
        if not hasattr(self, '_alias_buffer'):
            self._alias_buffer = defaultdict(list)
        self._alias_buffer[(table, fk_column)].append((raw_value, fk_id))

    def _batch_create_simple_dim(self, table, canonical_names, id_cache):
        """Batch insert into a simple dimension table (only canonical_name column)."""
        if self.dry_run:
            for name in canonical_names:
                id_cache[name] = f"dry-run-{name}"
            return

        # Batch insert
        chunk_size = 500
        for i in range(0, len(canonical_names), chunk_size):
            chunk = canonical_names[i:i+chunk_size]
            values_sql = ','.join(
                self.cursor.mogrify("(%s)", (name,)).decode()
                for name in chunk
            )
            self.cursor.execute(
                f"INSERT INTO {table} (canonical_name) VALUES {values_sql} "
                f"ON CONFLICT (canonical_name) DO NOTHING"
            )

        # Fetch all IDs back
        self.cursor.execute(f"SELECT id, canonical_name FROM {table}")
        for row in self.cursor.fetchall():
            id_cache[row['canonical_name']] = row['id']

    def _flush_aliases(self):
        """Flush all buffered alias entries to database in batch."""
        if self.dry_run or not hasattr(self, '_alias_buffer'):
            return
        for (table, fk_column), entries in self._alias_buffer.items():
            if not entries:
                continue
            # Batch insert in chunks
            chunk_size = 500
            for i in range(0, len(entries), chunk_size):
                chunk = entries[i:i+chunk_size]
                values_sql = ','.join(
                    self.cursor.mogrify("(%s, %s)", (raw, fk)).decode()
                    for raw, fk in chunk
                )
                self.cursor.execute(
                    f"INSERT INTO {table} (raw_value, {fk_column}) VALUES {values_sql} "
                    f"ON CONFLICT (raw_value) DO NOTHING"
                )
        self._alias_buffer.clear()


def main():
    import argparse
    parser = argparse.ArgumentParser(description='Populate dimension tables from processed_prices')
    parser.add_argument('--dry-run', action='store_true', help='Preview without changes')
    parser.add_argument('--skip-observations', action='store_true',
                        help='Only populate dimensions, skip price_observations')
    args = parser.parse_args()

    populator = DimensionPopulator(dry_run=args.dry_run)
    populator.run(skip_observations=args.skip_observations)


if __name__ == '__main__':
    main()
