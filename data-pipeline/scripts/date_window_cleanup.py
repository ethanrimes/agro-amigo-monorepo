"""Date-window cleanup: delete rows outside 2025-05-21..2026-05-21."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.supabase_client import get_db_connection

START = '2025-05-21'
END = '2026-05-21'

TABLES_WITH_DATE = [
    ('processed_prices', 'price_date'),
    ('price_observations', 'price_date'),
    ('supply_observations', 'observation_date'),
    ('insumo_prices_municipality', 'price_date'),
    ('insumo_prices_department', 'price_date'),
]

def main():
    conn = get_db_connection(new_connection=True)
    conn.autocommit = True
    cur = conn.cursor()

    # Now we know the date column names; skip schema-verification step.
    print(f"\n=== Pre-cleanup counts ===")
    for table, col in TABLES_WITH_DATE:
        try:
            cur.execute(f"SELECT COUNT(*) AS n FROM {table}")
            r = cur.fetchone(); n_all = r['n'] if isinstance(r, dict) else r[0]
            cur.execute(f"SELECT COUNT(*) AS n FROM {table} WHERE {col} >= %s AND {col} < %s", (START, END))
            r = cur.fetchone(); n_in = r['n'] if isinstance(r, dict) else r[0]
            print(f"  {table}: total {n_all:,}, in-window {n_in:,}, OUT-of-window {n_all - n_in:,}")
        except Exception as e:
            print(f"  {table}: ERROR {e}")

    if '--dry-run' in sys.argv:
        print("\nDRY RUN — no deletes")
        return

    print(f"\n=== Deleting rows OUTSIDE [{START}, {END}) ===")
    for table, col in TABLES_WITH_DATE:
        try:
            cur.execute(f"DELETE FROM {table} WHERE {col} < %s OR {col} >= %s", (START, END))
            print(f"  {table}: deleted {cur.rowcount:,}")
        except Exception as e:
            print(f"  {table}: ERROR {e}")

    print(f"\n=== Post-cleanup counts ===")
    for table, col in TABLES_WITH_DATE:
        try:
            cur.execute(f"SELECT COUNT(*) AS n FROM {table}")
            r = cur.fetchone(); n = r['n'] if isinstance(r, dict) else r[0]
            print(f"  {table}: {n:,}")
        except Exception:
            pass

if __name__ == '__main__':
    main()
