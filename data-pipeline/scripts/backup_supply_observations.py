"""Stream supply_observations (+ abastecimiento download_entries) to gzipped JSONL.

Run before reprocess_abastecimiento.py so we have a byte-for-byte snapshot of the
~2M rows that will be deleted. The source Excel files already encode the same
information, but this backup preserves UUIDs, created_at, and source_path so a
restore is fully deterministic if reprocessing goes sideways.

Usage:
    python scripts/backup_supply_observations.py

Output:
    data-pipeline/backups/supply_observations_<UTC>.jsonl.gz
    data-pipeline/backups/abastecimiento_download_entries_<UTC>.json
"""
import gzip
import json
import os
import sys
import time
import urllib.request
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# Honor the same env the rest of the pipeline reads.
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

_load_env()

SUPABASE_URL = os.environ['SUPABASE_URL'].rstrip('/')
KEY = os.environ.get('SUPABASE_PUBLISHABLE_KEY') or os.environ['SUPABASE_SECRET_KEY']
PAGE = 1000  # PostgREST default cap; safe for 5MB-ish JSON payloads


def _get(path: str, query: dict) -> bytes:
    qs = urllib.parse.urlencode(query, quote_via=urllib.parse.quote)
    req = urllib.request.Request(
        f'{SUPABASE_URL}{path}?{qs}',
        headers={'apikey': KEY, 'Authorization': f'Bearer {KEY}', 'Accept': 'application/json'},
    )
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read()


def dump_supply(out_path: Path) -> int:
    print(f'streaming supply_observations -> {out_path}')
    last_id = ''
    total = 0
    start = time.time()
    with gzip.open(out_path, 'wb', compresslevel=6) as f:
        while True:
            query = {
                'select': '*',
                'order': 'id.asc',
                'limit': str(PAGE),
            }
            if last_id:
                query['id'] = f'gt.{last_id}'
            for attempt in range(5):
                try:
                    raw = _get('/rest/v1/supply_observations', query)
                    break
                except Exception as e:
                    print(f'  page after id={last_id or "(start)"} failed (attempt {attempt+1}/5): {e}')
                    time.sleep(2 ** attempt)
            else:
                raise RuntimeError('5 consecutive page failures, aborting')

            rows = json.loads(raw.decode('utf-8'))
            if not rows:
                break
            for row in rows:
                f.write(json.dumps(row, separators=(',', ':')).encode('utf-8'))
                f.write(b'\n')
            total += len(rows)
            last_id = rows[-1]['id']

            if total % 20000 == 0 or len(rows) < PAGE:
                elapsed = time.time() - start
                rate = total / elapsed if elapsed > 0 else 0
                print(f'  {total:>9,} rows  ({rate:,.0f} rows/s, {elapsed:,.0f}s elapsed)')

            if len(rows) < PAGE:
                break

    elapsed = time.time() - start
    size_mb = out_path.stat().st_size / 1024 / 1024
    print(f'done: {total:,} rows, {size_mb:.1f} MB gzipped, {elapsed:,.0f}s')
    return total


def dump_download_entries(out_path: Path) -> int:
    raw = _get('/rest/v1/download_entries', {
        'select': '*',
        'source_table_link': 'eq.abastecimiento_microdatos',
    })
    rows = json.loads(raw.decode('utf-8'))
    out_path.write_text(json.dumps(rows, indent=2), encoding='utf-8')
    print(f'wrote {len(rows)} download_entries rows -> {out_path}')
    return len(rows)


def main() -> int:
    backups = ROOT / 'backups'
    backups.mkdir(exist_ok=True)
    ts = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    supply_path = backups / f'supply_observations_{ts}.jsonl.gz'
    entries_path = backups / f'abastecimiento_download_entries_{ts}.json'

    dump_download_entries(entries_path)
    dump_supply(supply_path)

    print('\nrestore (if needed):')
    print(f'  see scripts/restore_supply_observations.py {supply_path.name}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
