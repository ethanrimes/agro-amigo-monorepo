"""Unlink SIPSA milk + rice price observations from their phantom markets,
then delete any dim_market that ends up with zero price + zero supply rows.

Background:
SIPSA reports milk and rice prices at the city level only (no specific
wholesale market). The pipeline's _resolve_market falls through to
'Mercado municipal de <city>', which created ~190 phantom market rows
holding only milk/rice prices. The iPhone markets list shows these but
the market detail page can't surface anything since these aren't real
produce markets and observations are monthly aggregates outside the
iPhone's 14-day product window.

Fixing the pipeline (so milk_parser + rice_parser leave market_id NULL)
is a separate TODO; this script cleans up the artifacts already in DB.

Dry-run: python scripts/prune_empty_markets.py --dry-run
Live:    python scripts/prune_empty_markets.py
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from backend.supabase_client import get_db_connection


def main(dry_run: bool) -> int:
    conn = get_db_connection(new_connection=True)
    conn.autocommit = False
    cur = conn.cursor()

    CITY_LEVEL_PATTERNS = ("source_path LIKE 'milk/%'", "source_path LIKE 'rice/%'")
    city_level_where = ' OR '.join(CITY_LEVEL_PATTERNS)
    non_city_where   = ' AND '.join(f'NOT ({p})' for p in CITY_LEVEL_PATTERNS)

    for label, where in (('milk', "source_path LIKE 'milk/%'"),
                         ('rice', "source_path LIKE 'rice/%'")):
        cur.execute(f"SELECT COUNT(*) AS n, COUNT(DISTINCT market_id) AS mn "
                    f"FROM price_observations WHERE {where} AND market_id IS NOT NULL")
        r = cur.fetchone()
        print(f'{label} price obs to unlink: {r["n"]:,} (across {r["mn"]} markets)')

    if dry_run:
        cur.execute(f'''
            SELECT COUNT(*) AS n FROM dim_market m WHERE NOT EXISTS (
                SELECT 1 FROM price_observations
                WHERE market_id = m.id AND ({non_city_where})
            ) AND NOT EXISTS (
                SELECT 1 FROM supply_observations WHERE market_id = m.id
            )
        ''')
        would_delete = cur.fetchone()['n']
        print(f'markets that would be empty after unlink + deleted: {would_delete}')
        print('[dry-run] no changes made')
        cur.close(); conn.close()
        return 0

    # 1. Unlink milk + rice price obs from their markets.
    cur.execute(f"UPDATE price_observations SET market_id = NULL WHERE {city_level_where}")
    print(f'unlinked {cur.rowcount} milk+rice price_observations rows')

    # 2. Identify newly-empty markets.
    cur.execute('''
        SELECT m.id::text AS id, m.canonical_name
        FROM dim_market m
        WHERE NOT EXISTS (SELECT 1 FROM price_observations WHERE market_id = m.id)
          AND NOT EXISTS (SELECT 1 FROM supply_observations WHERE market_id = m.id)
    ''')
    empty = cur.fetchall()
    print(f'empty markets to delete: {len(empty)}')

    if empty:
        ids = [r['id'] for r in empty]
        cur.execute('DELETE FROM alias_market WHERE market_id::text = ANY(%s)', (ids,))
        print(f'  deleted {cur.rowcount} alias_market rows')
        cur.execute('DELETE FROM dim_market WHERE id::text = ANY(%s)', (ids,))
        print(f'  deleted {cur.rowcount} dim_market rows')

    # 3. Final summary.
    cur.execute('SELECT COUNT(*) AS n FROM dim_market')
    print(f'\nremaining dim_market rows: {cur.fetchone()["n"]}')

    conn.commit()
    cur.close(); conn.close()
    return 0


if __name__ == '__main__':
    sys.exit(main(dry_run='--dry-run' in sys.argv))
