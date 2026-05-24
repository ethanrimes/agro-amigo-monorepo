"""Reattribute supply/price/market FKs from one dim_city row to another.

Used to fix homonym-resolution mistakes: when DIVIPOLA has more than one
municipality with the same name (Armenia, Florencia, ...), the resolver
created two dim_city rows and bucketed the wholesale-market data into
the wrong one. This script re-points every dependent row to the correct
target row and deletes the empty source row.

Specifies the migrations inline. Run with --dry-run first.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from backend.supabase_client import get_db_connection


# (wrong_city_id, correct_city_id, label, expected_alias_to_keep)
MIGRATIONS = [
    # Armenia: data is on the Antioquia row but the wholesale market is in Quindío.
    ('d3af6e3e-a037-446a-afe1-4850498521c2',
     'e8151462-9020-4485-87c8-e930fec04929',
     'Armenia (ANTIOQUIA -> QUINDÍO)',
     'Armenia'),
    # Florencia: data is on the Cauca row but the wholesale market is in Caquetá.
    ('?',  # placeholder - will be resolved by query
     '?',
     'Florencia (CAUCA -> CAQUETÁ)',
     'Florencia'),
]


def resolve_florencia(cur):
    """Look up the two Florencia city_ids dynamically (their UUIDs weren't pinned)."""
    cur.execute("""
        SELECT c.id, d.canonical_name AS dept
        FROM dim_city c JOIN dim_department d ON d.id = c.department_id
        WHERE UPPER(c.canonical_name) = 'FLORENCIA'
    """)
    wrong = right = None
    for r in cur.fetchall():
        dept = (r['dept'] or '').upper()
        if 'CAUCA' in dept and 'CAQUET' not in dept:
            wrong = r['id']
        elif 'CAQUET' in dept:
            right = r['id']
    return wrong, right


def migrate(cur, wrong_id, correct_id, label, alias_value, dry_run: bool):
    print(f'\n--- {label} ---')
    if not wrong_id or not correct_id:
        print('  resolution failed, skipping')
        return

    cur.execute("SELECT canonical_name, divipola_code FROM dim_city WHERE id = %s", (wrong_id,))
    w = cur.fetchone()
    cur.execute("SELECT canonical_name, divipola_code FROM dim_city WHERE id = %s", (correct_id,))
    c = cur.fetchone()
    if not w or not c:
        print(f'  one side is missing, skipping (wrong={w}, correct={c})')
        return
    w_name, w_dvp = w['canonical_name'], w['divipola_code']
    c_name, c_dvp = c['canonical_name'], c['divipola_code']
    print(f'  source: {w_name!r:25s} divipola={w_dvp:>6} id={wrong_id}')
    print(f'  target: {c_name!r:25s} divipola={c_dvp:>6} id={correct_id}')

    cur.execute("SELECT COUNT(*) AS n FROM dim_market WHERE city_id = %s", (wrong_id,))
    nm = cur.fetchone()['n']
    cur.execute("SELECT COUNT(*) AS n FROM price_observations WHERE city_id = %s", (wrong_id,))
    np = cur.fetchone()['n']
    cur.execute("SELECT COUNT(*) AS n FROM supply_observations WHERE city_id = %s", (wrong_id,))
    ns = cur.fetchone()['n']
    cur.execute("SELECT COUNT(*) AS n FROM alias_city WHERE city_id = %s", (wrong_id,))
    na = cur.fetchone()['n']
    print(f'  to reattribute: markets={nm}, price_obs={np:,}, supply_obs={ns:,}, alias_city={na}')

    # Conflict check: are there dim_market rows on BOTH sides with the same name?
    # If so we'd violate the unique(canonical_name) constraint on UPDATE. The
    # only known case is "Mercado municipal de X" placeholders that exist on
    # both rows. Delete the empty placeholder before re-pointing.
    cur.execute("""
        SELECT m1.id AS wrong_market, m1.canonical_name, m2.id AS correct_market
        FROM dim_market m1
        JOIN dim_market m2 ON m2.canonical_name = m1.canonical_name AND m2.id <> m1.id
        WHERE m1.city_id = %s AND m2.city_id = %s
    """, (wrong_id, correct_id))
    conflicts = cur.fetchall()
    if conflicts:
        print(f'  market name conflicts on both sides:')
        for c2 in conflicts:
            cn = c2['canonical_name']
            print(f'    {cn!r}: wrong_id={c2["wrong_market"]} correct_id={c2["correct_market"]}')

    if dry_run:
        print('  [dry-run] no changes made')
        return

    # If conflicts: keep whichever side actually has data, delete the other.
    for c2 in conflicts:
        cur.execute("SELECT COUNT(*) AS n FROM price_observations WHERE market_id = %s", (c2['wrong_market'],))
        wp = cur.fetchone()['n']
        cur.execute("SELECT COUNT(*) AS n FROM supply_observations WHERE market_id = %s", (c2['wrong_market'],))
        ws = cur.fetchone()['n']
        cur.execute("SELECT COUNT(*) AS n FROM price_observations WHERE market_id = %s", (c2['correct_market'],))
        cp = cur.fetchone()['n']
        cur.execute("SELECT COUNT(*) AS n FROM supply_observations WHERE market_id = %s", (c2['correct_market'],))
        cs = cur.fetchone()['n']
        # wrong side has wp+ws rows, correct side has cp+cs rows
        # Keep whichever has more; if tied at zero, keep the correct-side one.
        if (wp + ws) > (cp + cs):
            # Move data from the correct-side market to the wrong-side market, delete correct-side, then proceed.
            cur.execute("UPDATE price_observations SET market_id = %s WHERE market_id = %s",
                        (c2['wrong_market'], c2['correct_market']))
            cur.execute("UPDATE supply_observations SET market_id = %s WHERE market_id = %s",
                        (c2['wrong_market'], c2['correct_market']))
            cur.execute("DELETE FROM alias_market WHERE market_id = %s", (c2['correct_market'],))
            cur.execute("DELETE FROM dim_market WHERE id = %s", (c2['correct_market'],))
            cn = c2['canonical_name']
            print(f'    merged {cn!r}: kept wrong-side row (had more data)')
        else:
            # Move data from wrong-side market to correct-side market, delete wrong-side.
            cur.execute("UPDATE price_observations SET market_id = %s WHERE market_id = %s",
                        (c2['correct_market'], c2['wrong_market']))
            cur.execute("UPDATE supply_observations SET market_id = %s WHERE market_id = %s",
                        (c2['correct_market'], c2['wrong_market']))
            cur.execute("DELETE FROM alias_market WHERE market_id = %s", (c2['wrong_market'],))
            cur.execute("DELETE FROM dim_market WHERE id = %s", (c2['wrong_market'],))
            cn = c2['canonical_name']
            print(f'    merged {cn!r}: kept correct-side row')

    cur.execute("UPDATE dim_market SET city_id = %s WHERE city_id = %s",
                (correct_id, wrong_id))
    print(f'  re-pointed {cur.rowcount} dim_market rows')

    cur.execute("UPDATE price_observations SET city_id = %s WHERE city_id = %s",
                (correct_id, wrong_id))
    print(f'  re-pointed {cur.rowcount} price_observations rows')

    cur.execute("UPDATE supply_observations SET city_id = %s WHERE city_id = %s",
                (correct_id, wrong_id))
    print(f'  re-pointed {cur.rowcount} supply_observations rows')

    cur.execute("UPDATE insumo_prices_municipality SET city_id = %s WHERE city_id = %s",
                (correct_id, wrong_id))
    print(f'  re-pointed {cur.rowcount} insumo_prices_municipality rows')

    # alias_city: re-point any aliases pointing at the wrong row to the correct
    # row, ignoring conflicts (correct row may already have its own alias).
    cur.execute("""
        UPDATE alias_city SET city_id = %s
        WHERE city_id = %s
          AND raw_value NOT IN (SELECT raw_value FROM alias_city WHERE city_id = %s)
    """, (correct_id, wrong_id, correct_id))
    cur.execute("DELETE FROM alias_city WHERE city_id = %s", (wrong_id,))

    # Ensure the canonical name alias points to the correct row.
    cur.execute("""
        INSERT INTO alias_city (raw_value, city_id) VALUES (%s, %s)
        ON CONFLICT (raw_value) DO UPDATE SET city_id = EXCLUDED.city_id
    """, (alias_value, correct_id))

    cur.execute("DELETE FROM dim_city WHERE id = %s", (wrong_id,))
    print(f'  deleted source dim_city row')


def main(dry_run: bool) -> int:
    conn = get_db_connection(new_connection=True)
    conn.autocommit = False
    cur = conn.cursor()

    fw, fc = resolve_florencia(cur)
    migrations = [
        ('d3af6e3e-a037-446a-afe1-4850498521c2',
         'e8151462-9020-4485-87c8-e930fec04929',
         'Armenia (ANTIOQUIA -> QUINDÍO)', 'Armenia'),
        (fw, fc, 'Florencia (CAUCA -> CAQUETÁ)', 'Florencia'),
    ]

    for wrong_id, correct_id, label, alias in migrations:
        migrate(cur, wrong_id, correct_id, label, alias, dry_run)

    if not dry_run:
        conn.commit()
    cur.close()
    conn.close()
    return 0


if __name__ == '__main__':
    sys.exit(main(dry_run='--dry-run' in sys.argv))
