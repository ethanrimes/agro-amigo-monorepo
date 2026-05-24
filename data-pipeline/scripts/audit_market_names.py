"""Audit every distinct (city, market) string in the abastecimiento source files
against dim_market.canonical_name.

Reports per market name:
  - exact match in dim_market
  - normalized/case-insensitive match
  - no match (will be created or fall back to municipal)

Use this to verify the resolver will correctly classify every row before
re-ingestion finishes.
"""
import json
import os
import sys
import unicodedata
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import urllib.parse
import urllib.request

from processing.abastecimiento_parser import AbastecimientoParser
from backend.dimension_resolver import _normalize


def _load_env():
    env_path = ROOT / '.env'
    if not env_path.exists():
        return
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith('#') or '=' not in line:
            continue
        k, v = line.split('=', 1)
        os.environ.setdefault(k.strip(), v.strip())


def fetch_dim_markets():
    _load_env()
    url = os.environ['SUPABASE_URL'].rstrip('/')
    key = os.environ.get('SUPABASE_PUBLISHABLE_KEY') or os.environ['SUPABASE_SECRET_KEY']
    req = urllib.request.Request(
        f'{url}/rest/v1/dim_market?select=id,canonical_name,city_id',
        headers={'apikey': key, 'Authorization': f'Bearer {key}'},
    )
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read().decode('utf-8'))


def _strip_accents(s: str) -> str:
    nfkd = unicodedata.normalize('NFKD', s)
    return ''.join(c for c in nfkd if not unicodedata.combining(c))


def _split_city_market(combined: str):
    """Mirror DimensionResolver._split_city_market."""
    combined = combined.strip()
    if combined.startswith('Bogotá, D.C.,') or combined.startswith('Bogota, D.C.,'):
        parts = combined.split(',', 2)
        city = f"{parts[0].strip()}, {parts[1].strip()}"
        market = parts[2].strip() if len(parts) > 2 else ''
        return city, market
    parts = combined.rsplit(',', 1)
    if len(parts) == 2:
        return parts[0].strip(), parts[1].strip()
    return combined, ''


def main(files):
    parser = AbastecimientoParser()
    seen = defaultdict(int)  # (city, market) -> row_count
    for f in files:
        print(f'parsing {f} ...')
        rows, _ = parser.parse(f)
        for r in rows:
            c, m = _split_city_market(r.city_market)
            seen[(c, m)] += 1
        print(f'  cumulative distinct (city,market) pairs: {len(seen)}')

    dim_markets = fetch_dim_markets()
    by_name = {m['canonical_name']: m for m in dim_markets}
    by_name_lower = {m['canonical_name'].lower(): m for m in dim_markets}
    by_name_stripped = {_strip_accents(m['canonical_name']).lower(): m for m in dim_markets}

    matches = []
    case_only = []
    accent_only = []
    missing = []
    empty = []

    for (city, market), n in sorted(seen.items(), key=lambda kv: -kv[1]):
        if not market:
            empty.append((city, n))
            continue
        norm = _normalize(market)
        if norm in by_name:
            matches.append((city, market, n))
        elif market.lower() in by_name_lower or norm.lower() in by_name_lower:
            case_only.append((city, market, n))
        elif _strip_accents(norm).lower() in by_name_stripped:
            accent_only.append((city, market, n))
        else:
            missing.append((city, market, n))

    print(f'\n=== summary ===')
    print(f'  total distinct (city,market) pairs: {len(seen)}')
    print(f'  total rows across all pairs:        {sum(seen.values()):,}')
    print(f'  exact canonical_name match:         {len(matches)}')
    print(f'  case-only mismatch:                 {len(case_only)}')
    print(f'  accent-only mismatch:               {len(accent_only)}')
    print(f'  no dim_market match (need create):  {len(missing)}')
    print(f'  empty market name (-> municipal):    {len(empty)}')

    if missing:
        print('\n=== markets that will NOT resolve (currently fall through to municipal) ===')
        for city, market, n in missing:
            print(f'  "{city}" || "{market}"  ({n:,} rows)')

    if case_only:
        print('\n=== case-only mismatches (treat as needing alias) ===')
        for city, market, n in case_only:
            target = by_name_lower[market.lower()]['canonical_name']
            print(f'  "{market}" vs dim "{target}"  ({n:,} rows)')

    if accent_only:
        print('\n=== accent-only mismatches ===')
        for city, market, n in accent_only:
            target = by_name_stripped[_strip_accents(market).lower()]['canonical_name']
            print(f'  "{market}" vs dim "{target}"  ({n:,} rows)')

    if empty:
        print('\n=== rows with empty market name (municipal fallback path) ===')
        for city, n in empty:
            print(f'  "{city}"  ({n:,} rows)')


if __name__ == '__main__':
    files = [
        str(ROOT / 'exports' / 'abastecimiento' / 'anex-Microdato-abastecimiento-2025.xlsx'),
        str(ROOT / 'exports' / 'abastecimiento' / 'anex-Microdato-abastecimiento-2026.xlsx'),
    ]
    main(files)
