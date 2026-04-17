#!/usr/bin/env python3
"""
Migration 023: Deduplicate and clean markets.

Categories:
1. Abbreviation/typo duplicates (CMA = Central Mayorista de Antioquia)
2. Junk entries (city/dept/product names leaked into market column)
3. Generic "Mercado municipal de X" that should merge into named markets
"""

import os, sys, psycopg2
from psycopg2.extras import RealDictCursor
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / '.env')
if sys.platform == 'win32':
    os.environ.setdefault('PYTHONIOENCODING', 'utf-8')
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')

DB_URL = os.getenv('SUPABASE_DB_URL')

# Merge target -> [sources to merge FROM]
MARKET_MERGES = {
    # --- Abbreviation / typo duplicates ---
    'Central Mayorista de Antioquia': ['CMA'],
    'CAV': ['Central de Abastos de Villavicencio (CAV)'],
    'Complejo de servicios del Sur': ['Compeljo de servicios del Sur'],
    'Plaza de Mercado del Barrio Bolívar': [
        'Plaza de Mercado del Barrio Bolvar',
        'Plaza del Barrio Bolívar',
    ],
    'La 41': ['La 41-Impala'],

    # --- Junk entries (city/dept/product names in market column) ---
    'Granabastos': ['Barranquilla'],           # City name leaked (Barranquilla)
    'Mercado municipal de Santa Marta': ['Magdalena'],  # Dept name leaked
    'Mercado municipal de La Ceja': ['Antioquia'],      # Dept name leaked
    'Mercado municipal de San Gil': ['panela'],          # Product name leaked
    'Mercado municipal de Rionegro': ['PRECIOS DE VENTA MAYORISTA'],  # Report header
    'Mercado municipal de Peñol': ['Peñol (Antioquia)'],  # City name with qualifier
    'Mercado municipal de Tuluá': ['Tuluá (Valle del Cauca)'],  # City name with qualifier

    # --- Generic "Mercado municipal" -> named wholesale markets ---
    # These are cities where SIPSA tracks a specific named wholesale market
    # and the generic "Mercado municipal de X" represents the same place.
    'Central Mayorista de Antioquia': ['Mercado municipal de Medellin'],
    'Plaza La 21': ['Mercado municipal de Ibague'],
    'CAV': ['Mercado municipal de VILLAVICENCIO'],
    'Surabastos': ['Mercado municipal de NEIVA'],
    'El Potrerillo': ['Mercado municipal de PASTO'],
    'Centro Galerías': ['Mercado municipal de MANIZALES'],
    'Nuevo Mercado': ['Mercado municipal de SINCELEJO'],
    'Mercabastos': ['Mercado municipal de VALLEDUPAR', 'Mercado Nuevo'],
    'Mercaplaza': ['Mercado municipal de DUITAMA'],
    'Coomproriente': ['Mercado municipal de TIBASOSA'],
    'Complejo de servicios del Sur': ['Mercado municipal de TUNJA'],
    'Mercado del Sur': ['Mercado municipal de Monteria'],
    'Mercasa': ['Mercado municipal de PEREIRA'],
    'Plaza de Mercado del Barrio Bolívar': ['Mercado municipal de Popayan'],
}

# Renames for consistency after merging
MARKET_RENAMES = {
    'Mercado municipal de LA CEJA': 'Mercado municipal de La Ceja',
    'Mercado municipal de IPIALES': 'Mercado municipal de Ipiales',
    'Mercado municipal de AIPE': 'Mercado municipal de Aipe',
    'Mercado municipal de ILES': 'Mercado municipal de Iles',
    'Mercado municipal de LA PAZ': 'Mercado municipal de La Paz',
    'Mercado municipal de COTA': 'Mercado municipal de Cota',
    'Mercado municipal de SUSA': 'Mercado municipal de Susa',
    'Mercado municipal de TAME': 'Mercado municipal de Tame',
    'Mercado municipal de TOCA': 'Mercado municipal de Toca',
    'Complejo de servicios del Sur': 'Complejo de Servicios del Sur',
}


def fresh():
    conn = psycopg2.connect(DB_URL, cursor_factory=RealDictCursor)
    conn.autocommit = True
    c = conn.cursor()
    c.execute("SET statement_timeout = '120s'")
    return conn, c


def merge_market(conn, c, surv_name, dup_name):
    """Merge dup_name market into surv_name, updating all FKs."""
    # Find surviving market
    c.execute('SELECT id FROM dim_market WHERE canonical_name = %s', (surv_name,))
    sr = c.fetchone()
    if not sr:
        c.execute('SELECT id, canonical_name FROM dim_market WHERE canonical_name ILIKE %s', (surv_name,))
        sr = c.fetchone()
        if not sr:
            print(f'  SKIP {surv_name}: not found', flush=True)
            return conn, c
    surv_id = sr['id']

    # Find duplicate market
    c.execute('SELECT id FROM dim_market WHERE canonical_name = %s', (dup_name,))
    dr = c.fetchone()
    if not dr:
        return conn, c  # Already merged
    dup_id = dr['id']

    # 1. Rewire alias_market (handle unique conflicts)
    c.execute('DELETE FROM alias_market WHERE market_id=%s AND raw_value IN '
              '(SELECT raw_value FROM alias_market WHERE market_id=%s)', (dup_id, surv_id))
    c.execute('UPDATE alias_market SET market_id=%s WHERE market_id=%s', (surv_id, dup_id))

    # 2. Rewire price_observations.market_id (batched)
    total = 0
    while True:
        try:
            c.execute('WITH b AS (SELECT id FROM price_observations WHERE market_id=%s LIMIT 5000) '
                      'UPDATE price_observations SET market_id=%s WHERE id IN (SELECT id FROM b)',
                      (dup_id, surv_id))
            if c.rowcount == 0:
                break
            total += c.rowcount
        except Exception as e:
            print(f'    price err: {e}', flush=True)
            conn.close()
            conn, c = fresh()
            break

    # 3. Rewire supply_observations.market_id (batched)
    while True:
        try:
            c.execute('WITH b AS (SELECT id FROM supply_observations WHERE market_id=%s LIMIT 5000) '
                      'UPDATE supply_observations SET market_id=%s WHERE id IN (SELECT id FROM b)',
                      (dup_id, surv_id))
            if c.rowcount == 0:
                break
            total += c.rowcount
        except Exception as e:
            print(f'    supply err: {e}', flush=True)
            conn.close()
            conn, c = fresh()
            break

    # 4. Delete duplicate
    try:
        c.execute('DELETE FROM alias_market WHERE market_id=%s', (dup_id,))
        c.execute('DELETE FROM dim_market WHERE id=%s', (dup_id,))
        print(f'  {dup_name} -> {surv_name} ({total} rows)', flush=True)
    except Exception as e:
        print(f'  DELETE FAIL {dup_name}: {e}', flush=True)
        conn.close()
        conn, c = fresh()

    return conn, c


def run():
    conn, c = fresh()
    c.execute('SELECT COUNT(*) FROM dim_market')
    print(f'Markets before: {c.fetchone()["count"]}', flush=True)

    # Process merges
    for surv_name, dup_names in MARKET_MERGES.items():
        for dn in dup_names:
            conn, c = merge_market(conn, c, surv_name, dn)

    # Renames
    renamed = 0
    for old, new in MARKET_RENAMES.items():
        c.execute('UPDATE dim_market SET canonical_name=%s WHERE canonical_name=%s', (new, old))
        if c.rowcount > 0:
            renamed += 1
    print(f'Renamed {renamed} markets', flush=True)

    c.execute('SELECT COUNT(*) FROM dim_market')
    print(f'Markets after: {c.fetchone()["count"]}', flush=True)
    conn.close()
    print('DONE', flush=True)


if __name__ == '__main__':
    run()
