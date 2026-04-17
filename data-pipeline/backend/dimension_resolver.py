"""
Dimension resolver — resolves raw strings to dimension UUIDs using the alias tables.

Used at data-ingestion time to map raw strings (product names, city names, etc.)
to their canonical UUID entries in the dimension tables. Creates new entries
on the fly when encountering unknown values.
"""

import re
import sys
import unicodedata
from typing import Optional, Dict, Tuple
from pathlib import Path

_parent_dir = str(Path(__file__).parent.parent)
if _parent_dir not in sys.path:
    sys.path.insert(0, _parent_dir)

from backend.supabase_client import get_db_connection


def _fix_encoding(s: str) -> str:
    """Fix mid-word uppercase accented characters."""
    fixes = {'Á': 'á', 'É': 'é', 'Í': 'í', 'Ó': 'ó', 'Ú': 'ú', 'Ñ': 'ñ'}
    result = s
    for i, ch in enumerate(result):
        if ch in fixes and i > 0 and result[i-1].isalpha() and result[i-1].islower():
            result = result[:i] + fixes[ch] + result[i+1:]
    return result


def _normalize(s: str) -> str:
    if not s:
        return ''
    s = _fix_encoding(s.strip())
    return re.sub(r'\s+', ' ', s)


def _strip_accents(s: str) -> str:
    nfkd = unicodedata.normalize('NFKD', s)
    return ''.join(c for c in nfkd if not unicodedata.combining(c))


# Category name normalization map (raw uppercase/variant → canonical)
_CATEGORY_MAP = {
    'FRUTAS': 'Frutas',
    'FRUTAS FRESCAS': 'Frutas',
    'VERDURAS Y HORTALIZAS': 'Verduras y hortalizas',
    'HORTALIZAS Y VERDURAS': 'Verduras y hortalizas',
    'TUBERCULOS, RAICES Y PLATANOS': 'Tubérculos, raíces y plátanos',
    'TUBÉRCULOS, RAÍCES Y PLÁTANOS': 'Tubérculos, raíces y plátanos',
    'TUBÉRCULOS Y PLÁTANOS': 'Tubérculos, raíces y plátanos',
    'PROCESADOS': 'Procesados',
    'CARNES': 'Carnes',
    'GRANOS Y CEREALES': 'Granos y cereales',
    'PESCADOS': 'Pescados',
    'PESCADOS Y MARISCOS': 'Pescados',
    'LACTEOS Y HUEVOS': 'Lácteos y huevos',
    'LÁCTEOS Y HUEVOS': 'Lácteos y huevos',
    'HUEVOS Y LÁCTEOS': 'Lácteos y huevos',
    'HUEVOS Y LACTEOS': 'Lácteos y huevos',
}


class DimensionResolver:
    """
    Resolves raw strings to dimension UUIDs via the alias tables.

    Caches lookups in memory for the lifetime of the instance.
    Creates new dimension entries when encountering unknown values.
    """

    def __init__(self, conn=None):
        """
        Args:
            conn: Optional existing DB connection. If None, creates a new one.
        """
        self._owns_conn = conn is None
        self.conn = conn or get_db_connection(new_connection=True)
        self.cursor = self.conn.cursor()

        # Caches: raw_value -> uuid
        self._city_cache: Dict[str, Optional[str]] = {}
        self._market_cache: Dict[str, Optional[str]] = {}
        self._category_cache: Dict[str, Optional[str]] = {}
        self._product_cache: Dict[str, Optional[str]] = {}
        self._department_cache: Dict[str, Optional[str]] = {}

        # Reverse cache: city_id -> department_id
        self._city_dept_cache: Dict[str, str] = {}

    def close(self):
        self.cursor.close()
        if self._owns_conn:
            self.conn.close()

    def commit(self):
        self.conn.commit()

    # ==================== PUBLIC API ====================

    def resolve_category(self, raw_value: str) -> Optional[str]:
        """Resolve a raw category string to a category UUID."""
        if not raw_value:
            return None

        # Normalize category via the known map
        canonical = _CATEGORY_MAP.get(raw_value.upper().strip())
        if not canonical:
            canonical = _CATEGORY_MAP.get(_normalize(raw_value).upper())
        if not canonical:
            canonical = _normalize(raw_value)

        cache_key = canonical
        if cache_key in self._category_cache:
            return self._category_cache[cache_key]

        # Look up alias
        cat_id = self._lookup_alias('alias_category', 'category_id', raw_value)
        if not cat_id and canonical != raw_value:
            cat_id = self._lookup_alias('alias_category', 'category_id', canonical)
        if not cat_id:
            # Try direct dim lookup
            cat_id = self._lookup_dim('dim_category', canonical)
        if not cat_id:
            # Create new category
            cat_id = self._create_dim('dim_category', canonical)
            self._create_alias('alias_category', raw_value, 'category_id', cat_id)
            if canonical != raw_value:
                self._create_alias('alias_category', canonical, 'category_id', cat_id)

        self._category_cache[cache_key] = cat_id
        self._category_cache[raw_value] = cat_id
        return cat_id

    def resolve_product(self, raw_product: str, category_id: str,
                        cpc_code: str = None) -> Optional[str]:
        """
        Resolve a raw product name to a product UUID.

        If the product doesn't exist, creates it under a 'General (<category>)' subcategory.
        """
        if not raw_product:
            return None

        normalized = _normalize(raw_product)
        if normalized in self._product_cache:
            return self._product_cache[normalized]

        # Look up alias
        prod_id = self._lookup_alias('alias_product', 'product_id', raw_product)
        if not prod_id and normalized != raw_product:
            prod_id = self._lookup_alias('alias_product', 'product_id', normalized)
        if not prod_id:
            prod_id = self._lookup_dim('dim_product', normalized)

        if not prod_id:
            # Need to create product — first ensure subcategory exists
            subcat_id = self._ensure_general_subcategory(category_id)
            prod_id = self._create_product(normalized, subcat_id, cpc_code)
            self._create_alias('alias_product', raw_product, 'product_id', prod_id)
            if normalized != raw_product:
                self._create_alias('alias_product', normalized, 'product_id', prod_id)

        # Update CPC code if we have one and the product doesn't
        if cpc_code and prod_id:
            self._maybe_set_cpc(prod_id, cpc_code)

        self._product_cache[normalized] = prod_id
        self._product_cache[raw_product] = prod_id
        return prod_id

    def resolve_city_market(self, combined: str) -> Tuple[Optional[str], Optional[str]]:
        """
        Resolve a combined 'City, Market' string (e.g., 'Bogotá, D.C., Corabastos').

        Returns (city_id, market_id).
        When the market name is empty, falls back to "Mercado municipal de <city>".
        """
        if not combined:
            return None, None

        city_name, market_name = self._split_city_market(combined)
        city_id = self._resolve_city(city_name)
        market_id = self._resolve_market(market_name) if market_name else None

        # Fallback: if no market resolved, use "Mercado municipal de <city>"
        if city_id and not market_id:
            city_canonical = self._get_city_canonical(city_id)
            if city_canonical:
                muni_name = f"Mercado municipal de {city_canonical}"
                market_id = self._resolve_market(muni_name)
                if not market_id:
                    # Create the municipal market
                    market_id = self._create_market(city_id, muni_name)

        return city_id, market_id

    def _get_city_canonical(self, city_id: str) -> Optional[str]:
        """Get the canonical name for a city by ID."""
        self.cursor.execute(
            "SELECT canonical_name FROM dim_city WHERE id = %s", (city_id,)
        )
        row = self.cursor.fetchone()
        return row['canonical_name'] if row else None

    def _create_market(self, city_id: str, market_name: str) -> Optional[str]:
        """Create a new market entry."""
        self.cursor.execute(
            "INSERT INTO dim_market (canonical_name, city_id) VALUES (%s, %s) "
            "ON CONFLICT (canonical_name) DO NOTHING RETURNING id",
            (market_name, city_id)
        )
        row = self.cursor.fetchone()
        if row:
            mid = row['id']
        else:
            self.cursor.execute(
                "SELECT id FROM dim_market WHERE canonical_name = %s", (market_name,)
            )
            r = self.cursor.fetchone()
            mid = r['id'] if r else None
        if mid:
            self._market_cache[market_name] = mid
            # Also create an alias
            self.cursor.execute(
                "INSERT INTO alias_market (raw_value, market_id) VALUES (%s, %s) "
                "ON CONFLICT (raw_value) DO NOTHING",
                (market_name, mid)
            )
        return mid

    def get_department_id(self, city_id: str) -> Optional[str]:
        """Get the department_id for a city."""
        if city_id in self._city_dept_cache:
            return self._city_dept_cache[city_id]

        self.cursor.execute(
            "SELECT department_id FROM dim_city WHERE id = %s", (city_id,)
        )
        row = self.cursor.fetchone()
        if row:
            self._city_dept_cache[city_id] = row['department_id']
            return row['department_id']
        return None

    # ==================== PRIVATE HELPERS ====================

    def _split_city_market(self, combined: str) -> Tuple[str, str]:
        """
        Split 'City, Market' or 'Bogotá, D.C., Corabastos' into (city, market).

        Handles the tricky case of 'Bogotá, D.C.' where the comma is part of the city name.
        """
        combined = combined.strip()

        # Known patterns with multiple commas
        if combined.startswith('Bogotá, D.C.,') or combined.startswith('Bogota, D.C.,'):
            parts = combined.split(',', 2)
            city = f"{parts[0].strip()}, {parts[1].strip()}"
            market = parts[2].strip() if len(parts) > 2 else ''
            return city, market

        # Standard split on last comma
        parts = combined.rsplit(',', 1)
        if len(parts) == 2:
            return parts[0].strip(), parts[1].strip()
        return combined, ''

    def _resolve_city(self, city_name: str) -> Optional[str]:
        if not city_name:
            return None
        if city_name in self._city_cache:
            return self._city_cache[city_name]

        city_id = self._lookup_alias('alias_city', 'city_id', city_name)
        if not city_id:
            normalized = _normalize(city_name)
            city_id = self._lookup_alias('alias_city', 'city_id', normalized)
        if not city_id:
            city_id = self._lookup_dim('dim_city', _normalize(city_name))

        # If still not found, try to create via divipola
        if not city_id:
            city_id = self._create_city_from_divipola(city_name)

        self._city_cache[city_name] = city_id
        return city_id

    def _resolve_market(self, market_name: str) -> Optional[str]:
        if not market_name:
            return None
        if market_name in self._market_cache:
            return self._market_cache[market_name]

        market_id = self._lookup_alias('alias_market', 'market_id', market_name)
        if not market_id:
            normalized = _normalize(market_name)
            market_id = self._lookup_alias('alias_market', 'market_id', normalized)

        self._market_cache[market_name] = market_id
        return market_id

    def _lookup_alias(self, table: str, fk_col: str, raw_value: str) -> Optional[str]:
        self.cursor.execute(
            f"SELECT {fk_col} FROM {table} WHERE raw_value = %s", (raw_value,)
        )
        row = self.cursor.fetchone()
        return row[fk_col] if row else None

    def _lookup_dim(self, table: str, canonical: str) -> Optional[str]:
        self.cursor.execute(
            f"SELECT id FROM {table} WHERE canonical_name = %s", (canonical,)
        )
        row = self.cursor.fetchone()
        return row['id'] if row else None

    def _create_dim(self, table: str, canonical: str) -> str:
        self.cursor.execute(
            f"INSERT INTO {table} (canonical_name) VALUES (%s) "
            f"ON CONFLICT (canonical_name) DO NOTHING RETURNING id",
            (canonical,)
        )
        row = self.cursor.fetchone()
        if row:
            return row['id']
        self.cursor.execute(f"SELECT id FROM {table} WHERE canonical_name = %s", (canonical,))
        return self.cursor.fetchone()['id']

    def _create_alias(self, table: str, raw_value: str, fk_col: str, fk_id: str):
        self.cursor.execute(
            f"INSERT INTO {table} (raw_value, {fk_col}) VALUES (%s, %s) "
            f"ON CONFLICT (raw_value) DO NOTHING",
            (raw_value, fk_id)
        )

    def _ensure_general_subcategory(self, category_id: str) -> str:
        """Ensure a 'General (<category>)' subcategory exists for the given category."""
        # Get category name
        self.cursor.execute("SELECT canonical_name FROM dim_category WHERE id = %s", (category_id,))
        cat_row = self.cursor.fetchone()
        cat_name = cat_row['canonical_name'] if cat_row else 'Unknown'

        subcat_name = f"General ({cat_name})"
        self.cursor.execute(
            "SELECT id FROM dim_subcategory WHERE canonical_name = %s", (subcat_name,)
        )
        row = self.cursor.fetchone()
        if row:
            return row['id']

        self.cursor.execute(
            "INSERT INTO dim_subcategory (canonical_name, category_id) VALUES (%s, %s) "
            "ON CONFLICT (canonical_name) DO NOTHING RETURNING id",
            (subcat_name, category_id)
        )
        row = self.cursor.fetchone()
        if row:
            return row['id']
        self.cursor.execute(
            "SELECT id FROM dim_subcategory WHERE canonical_name = %s", (subcat_name,)
        )
        return self.cursor.fetchone()['id']

    def _create_product(self, canonical: str, subcategory_id: str,
                        cpc_code: str = None) -> str:
        self.cursor.execute(
            "INSERT INTO dim_product (canonical_name, subcategory_id, cpc_code) "
            "VALUES (%s, %s, %s) ON CONFLICT (canonical_name) DO NOTHING RETURNING id",
            (canonical, subcategory_id, cpc_code)
        )
        row = self.cursor.fetchone()
        if row:
            return row['id']
        self.cursor.execute(
            "SELECT id FROM dim_product WHERE canonical_name = %s", (canonical,)
        )
        return self.cursor.fetchone()['id']

    def _maybe_set_cpc(self, product_id: str, cpc_code: str):
        """Set CPC code on a product if it doesn't already have one."""
        cpc_clean = cpc_code.strip().strip("'")
        if not cpc_clean:
            return
        self.cursor.execute(
            "UPDATE dim_product SET cpc_code = %s WHERE id = %s AND (cpc_code IS NULL OR cpc_code = '')",
            (cpc_clean, product_id)
        )

    def _create_city_from_divipola(self, city_name: str) -> Optional[str]:
        """Try to create a city entry by looking it up in divipola."""
        normalized = _normalize(city_name)
        # Try exact match
        self.cursor.execute(
            "SELECT nombre_municipio, nombre_departamento, codigo_municipio, codigo_departamento "
            "FROM divipola_municipios WHERE UPPER(nombre_municipio) = %s",
            (normalized.upper(),)
        )
        row = self.cursor.fetchone()
        if not row:
            # Try without accents
            stripped = _strip_accents(normalized).upper()
            self.cursor.execute(
                "SELECT nombre_municipio, nombre_departamento, codigo_municipio, codigo_departamento "
                "FROM divipola_municipios"
            )
            for r in self.cursor.fetchall():
                if _strip_accents(r['nombre_municipio']).upper() == stripped:
                    row = r
                    break

        if not row:
            print(f"    [WARN] Could not find city in divipola: {city_name}")
            return None

        # Ensure department exists
        dept_name = row['nombre_departamento']
        dept_code = row['codigo_departamento']
        dept_id = self._lookup_dim('dim_department', dept_name)
        if not dept_id:
            self.cursor.execute(
                "INSERT INTO dim_department (canonical_name, divipola_code) VALUES (%s, %s) "
                "ON CONFLICT (canonical_name) DO NOTHING RETURNING id",
                (dept_name, dept_code)
            )
            r = self.cursor.fetchone()
            dept_id = r['id'] if r else self._lookup_dim('dim_department', dept_name)

        # Create city
        self.cursor.execute(
            "INSERT INTO dim_city (canonical_name, department_id, divipola_code) VALUES (%s, %s, %s) "
            "ON CONFLICT (canonical_name) DO NOTHING RETURNING id",
            (normalized, dept_id, row['codigo_municipio'])
        )
        r = self.cursor.fetchone()
        city_id = r['id'] if r else self._lookup_dim('dim_city', normalized)

        # Create alias
        self._create_alias('alias_city', city_name, 'city_id', city_id)
        if normalized != city_name:
            self._create_alias('alias_city', normalized, 'city_id', city_id)

        return city_id
