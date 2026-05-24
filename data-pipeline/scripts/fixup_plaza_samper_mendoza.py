"""One-off: create dim_market 'Plaza Samper Mendoza' under Bogotá D.C.
and reattribute the supply_observations rows currently bucketed into
'Mercado municipal de Bogotá, D.C.'.

Background:
The previous resolve_city_market fell through to municipal whenever the
market name in the source was non-empty but unknown to dim_market. The
audit (scripts/audit_market_names.py) confirms exactly 15,118 source
rows have city_market = 'Bogotá, D.C., Plaza Samper Mendoza', and zero
Bogotá rows have empty market names. So every supply row currently
linked to the Bogotá municipal market actually belongs to Plaza Samper
Mendoza and can be safely reattributed.

After this script the resolver fix (resolve_city_market) will create the
correct dim_market row on its own for future ingests.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from backend.supabase_client import get_db_connection

BOGOTA_CITY_ID = '776732eb-259c-4818-8218-c872cb74283a'
BOGOTA_MUNICIPAL_MARKET_ID = '96c8cdfd-32a2-4462-8c91-86319f81274c'
NEW_MARKET_NAME = 'Plaza Samper Mendoza'


def main(dry_run: bool) -> int:
    conn = get_db_connection(new_connection=True)
    cur = conn.cursor()

    # Sanity: verify the Bogotá municipal market only holds rows that should
    # become Plaza Samper Mendoza (i.e., no rows with empty source-side market
    # — those would legitimately stay in municipal).
    cur.execute(
        "SELECT COUNT(*) AS n FROM supply_observations WHERE market_id = %s",
        (BOGOTA_MUNICIPAL_MARKET_ID,),
    )
    municipal_count = cur.fetchone()['n']
    print(f'rows currently in Bogotá municipal market: {municipal_count:,}')
    print(f'audit expected (Plaza Samper Mendoza):     15,118')
    if municipal_count != 15118:
        print('  WARNING: count mismatch with audit. Aborting to avoid mis-attribution.')
        cur.close(); conn.close()
        return 1

    # Check if Plaza Samper Mendoza already exists.
    cur.execute(
        "SELECT id FROM dim_market WHERE canonical_name = %s",
        (NEW_MARKET_NAME,),
    )
    row = cur.fetchone()
    if row:
        new_market_id = row['id']
        print(f"dim_market '{NEW_MARKET_NAME}' already exists: {new_market_id}")
    else:
        print(f"would INSERT dim_market '{NEW_MARKET_NAME}' under city {BOGOTA_CITY_ID}")
        new_market_id = None

    if dry_run:
        print('[dry-run] no changes made')
        cur.close(); conn.close()
        return 0

    if not new_market_id:
        cur.execute(
            "INSERT INTO dim_market (canonical_name, city_id) VALUES (%s, %s) "
            "RETURNING id",
            (NEW_MARKET_NAME, BOGOTA_CITY_ID),
        )
        new_market_id = cur.fetchone()['id']
        print(f'created dim_market: {new_market_id}')

        cur.execute(
            "INSERT INTO alias_market (raw_value, market_id) VALUES (%s, %s) "
            "ON CONFLICT (raw_value) DO NOTHING",
            (NEW_MARKET_NAME, new_market_id),
        )
        print(f'inserted alias_market row for "{NEW_MARKET_NAME}"')

    cur.execute(
        "UPDATE supply_observations SET market_id = %s WHERE market_id = %s",
        (new_market_id, BOGOTA_MUNICIPAL_MARKET_ID),
    )
    moved = cur.rowcount
    print(f'reattributed {moved:,} supply_observations rows to Plaza Samper Mendoza')

    conn.commit()
    cur.close(); conn.close()
    return 0


if __name__ == '__main__':
    sys.exit(main(dry_run='--dry-run' in sys.argv))
