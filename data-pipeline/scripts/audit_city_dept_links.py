"""Find dim_city rows whose department link is suspect.

For each dim_city, looks up divipola_municipios for all municipalities sharing
that name. If DIVIPOLA has multiple homonyms (e.g., Armenia, Florencia), the
city is ambiguous; flag whether the currently-linked department matches the
likely wholesale-market city. Also lists every dim_city whose markets carry
real data so we know which row each duplicate set should keep.
"""
import sys
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from backend.supabase_client import get_db_connection


def _norm(s: str) -> str:
    if not s:
        return ''
    nfkd = unicodedata.normalize('NFKD', s.strip())
    return ''.join(c for c in nfkd if not unicodedata.combining(c)).upper()


def main() -> int:
    conn = get_db_connection(new_connection=True)
    cur = conn.cursor()

    # Pull all dim_city + their dept + usage counts.
    cur.execute('''
        SELECT
            c.id AS city_id,
            c.canonical_name AS city_name,
            c.divipola_code,
            d.canonical_name AS dept,
            d.divipola_code AS dept_code,
            (SELECT COUNT(*) FROM dim_market WHERE city_id = c.id) AS market_count,
            (SELECT COUNT(*) FROM price_observations WHERE city_id = c.id) AS price_count,
            (SELECT COUNT(*) FROM supply_observations WHERE city_id = c.id) AS supply_count
        FROM dim_city c LEFT JOIN dim_department d ON d.id = c.department_id
    ''')
    cities = cur.fetchall()

    # DIVIPOLA homonym index.
    cur.execute('SELECT codigo_municipio, nombre_municipio, codigo_departamento, nombre_departamento FROM divipola_municipios')
    divipola = cur.fetchall()
    by_norm_name: dict = {}
    for r in divipola:
        by_norm_name.setdefault(_norm(r['nombre_municipio']), []).append(r)

    flagged = []
    safe = []
    no_divipola = []
    for c in cities:
        # Look up homonyms in DIVIPOLA.
        homonyms = by_norm_name.get(_norm(c['city_name']), [])
        if not homonyms:
            no_divipola.append(c)
            continue
        # Is the city's current dept one of the homonyms' depts?
        dept_norm = _norm(c['dept'])
        matching = [h for h in homonyms if _norm(h['nombre_departamento']) == dept_norm]
        ambiguous = len(homonyms) > 1
        if matching and not ambiguous:
            safe.append(c)
        elif matching and ambiguous:
            # Linked dept is one of several valid options. Need human judgement.
            flagged.append(('AMBIGUOUS', c, homonyms))
        else:
            # Linked dept isn't even in DIVIPOLA for this name. Definitely wrong.
            flagged.append(('WRONG', c, homonyms))

    n_amb = sum(1 for f in flagged if f[0] == 'AMBIGUOUS')
    n_wrong = sum(1 for f in flagged if f[0] == 'WRONG')
    print(f'total dim_city rows:                   {len(cities)}')
    print(f'  unambiguous + valid dept link:       {len(safe)}')
    print(f'  ambiguous (homonym in DIVIPOLA):     {n_amb}')
    print(f'  wrong (dept not even valid):         {n_wrong}')
    print(f'  name not in DIVIPOLA:                {len(no_divipola)}')

    if flagged:
        print('\n=== flagged cities ===')
        # Sort by usage so the meaningful ones come first.
        flagged.sort(key=lambda x: -(x[1]['price_count'] + x[1]['supply_count'] + x[1]['market_count']*100))
        for kind, c, homs in flagged:
            name = c['city_name']
            dvp = c['divipola_code'] or '?'
            dept = c['dept']
            usage = f"market={c['market_count']} price={c['price_count']:,} supply={c['supply_count']:,}"
            print(f'  [{kind:9s}] {name!r:30s} divipola={dvp:>6} dept={dept!r:30s} {usage}')
            for h in homs:
                marker = '  *' if _norm(h['nombre_departamento']) == _norm(c['dept'] or '') else '   '
                hc = h['codigo_municipio']
                hm = h['nombre_municipio']
                hd = h['nombre_departamento']
                print(f'    {marker} divipola says {hc:>6}  {hm!r:30s}  {hd!r}')

    if no_divipola:
        print(f'\n=== dim_city rows whose name is NOT in DIVIPOLA ({len(no_divipola)}) ===')
        for c in no_divipola[:30]:
            name = c['city_name']
            dvp = c['divipola_code'] or '?'
            dept = c['dept']
            usage = f"market={c['market_count']} price={c['price_count']:,} supply={c['supply_count']:,}"
            print(f'  {name!r:35s} divipola={dvp:>6} dept={dept!r}  {usage}')

    cur.close(); conn.close()
    return 0


if __name__ == '__main__':
    sys.exit(main())
