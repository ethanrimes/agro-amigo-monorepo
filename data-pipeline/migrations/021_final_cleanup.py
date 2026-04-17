#!/usr/bin/env python3
"""Final cleanup of remaining product duplicates missed by earlier passes."""

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

MERGES = [
    ('Maracuyá antioqueño', ['Maracuyá antioqueña']),
    ('Piernas de pollo', ['Pierna de pollo']),
    ('Panela redonda morena', ['Panela morena redonda']),
    ('Aceite girasol', ['Aceite Girasol']),
    ('Plátano hartón verde Eje Cafetero', ['Plátano hartón Eje Cafetero']),
    ('Zanahoria', ['Zanahorias']),
    ('Plátano dominico hartón verde', ['Plátano dom.hart.verd.']),
]


def fresh():
    conn = psycopg2.connect(DB_URL, cursor_factory=RealDictCursor)
    conn.autocommit = True
    c = conn.cursor()
    c.execute("SET statement_timeout = '120s'")
    return conn, c


def merge_one(conn, c, surv_name, dup_name):
    c.execute('SELECT id FROM dim_product WHERE canonical_name = %s', (surv_name,))
    sr = c.fetchone()
    if not sr:
        c.execute('SELECT id, canonical_name FROM dim_product WHERE canonical_name ILIKE %s', (surv_name,))
        sr = c.fetchone()
        if not sr:
            print(f'  SKIP {surv_name}: not found', flush=True)
            return conn, c
    surv_id = sr['id']

    c.execute('SELECT id FROM dim_product WHERE canonical_name = %s', (dup_name,))
    dr = c.fetchone()
    if not dr:
        return conn, c
    did = dr['id']

    # Rewire aliases
    c.execute('DELETE FROM alias_product WHERE product_id=%s AND raw_value IN '
              '(SELECT raw_value FROM alias_product WHERE product_id=%s)', (did, surv_id))
    c.execute('UPDATE alias_product SET product_id=%s WHERE product_id=%s', (surv_id, did))

    # Batch rewire supply
    total = 0
    while True:
        try:
            c.execute('WITH b AS (SELECT id FROM supply_observations WHERE product_id=%s LIMIT 2000) '
                      'UPDATE supply_observations SET product_id=%s WHERE id IN (SELECT id FROM b)',
                      (did, surv_id))
            if c.rowcount == 0:
                break
            total += c.rowcount
        except Exception as e:
            print(f'    supply err: {e}', flush=True)
            conn.close()
            conn, c = fresh()
            break

    # Rewire price
    try:
        c.execute('WITH b AS (SELECT id FROM price_observations WHERE product_id=%s LIMIT 5000) '
                  'UPDATE price_observations SET product_id=%s WHERE id IN (SELECT id FROM b)',
                  (did, surv_id))
        total += c.rowcount
    except Exception as e:
        print(f'    price err: {e}', flush=True)
        conn.close()
        conn, c = fresh()

    # Check remaining refs
    c.execute('SELECT COUNT(*) FROM supply_observations WHERE product_id=%s', (did,))
    s_left = c.fetchone()['count']
    c.execute('SELECT COUNT(*) FROM price_observations WHERE product_id=%s', (did,))
    p_left = c.fetchone()['count']

    if s_left == 0 and p_left == 0:
        c.execute('DELETE FROM alias_product WHERE product_id=%s', (did,))
        c.execute('DELETE FROM dim_product WHERE id=%s', (did,))
        print(f'  {dup_name} -> {surv_name} ({total} rows rewired, deleted)', flush=True)
    else:
        print(f'  {dup_name}: {s_left} supply + {p_left} price still remain', flush=True)

    return conn, c


def run():
    conn, c = fresh()
    c.execute('SELECT COUNT(*) FROM dim_product')
    print(f'Products before: {c.fetchone()["count"]}', flush=True)

    for surv_name, dup_names in MERGES:
        for dn in dup_names:
            conn, c = merge_one(conn, c, surv_name, dn)

    # Also find and merge any remaining Pastas alimenticias variants
    c.execute("SELECT id, canonical_name FROM dim_product WHERE canonical_name ILIKE 'pasta%%alimenticias%%' ORDER BY canonical_name")
    pastas = c.fetchall()
    if len(pastas) > 1:
        surv = pastas[0]
        for dup in pastas[1:]:
            conn, c = merge_one(conn, c, surv['canonical_name'], dup['canonical_name'])

    c.execute('SELECT COUNT(*) FROM dim_product')
    print(f'Products after: {c.fetchone()["count"]}', flush=True)
    conn.close()
    print('DONE', flush=True)


if __name__ == '__main__':
    run()
