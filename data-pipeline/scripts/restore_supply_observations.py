"""Restore supply_observations from a gzipped JSONL backup.

Usage:
    python scripts/restore_supply_observations.py <backup_file.jsonl.gz>

Inserts rows in chunks via COPY (re-uses the bulk loader the abastecimiento
ingest path uses). Use only when reprocessing failed and you need the prior
state back. Existing rows are not touched — caller is expected to TRUNCATE
supply_observations first if a clean restore is desired.
"""
import gzip
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from backend.supabase_client import get_db_connection

# Column order must match the backup field set. supply_observations columns
# excluding `created_at` (which has a default) — we restore it explicitly when
# present in the backup so `created_at` is preserved.
COLS = (
    'id', 'observation_date', 'city_id', 'market_id',
    'provenance_dept_code', 'provenance_muni_code',
    'provenance_dept_name', 'provenance_muni_name',
    'category_id', 'product_id', 'cpc_code',
    'quantity_kg', 'source_path', 'download_entry_id',
    'created_at',
)


def _csv_field(v) -> str:
    if v is None:
        return ''
    s = str(v)
    if any(ch in s for ch in (',', '"', '\n', '\r')):
        s = s.replace('"', '""')
        return f'"{s}"'
    return s


def main(path: Path) -> int:
    if not path.exists():
        print(f'backup not found: {path}', file=sys.stderr)
        return 1

    conn = get_db_connection(new_connection=True)
    conn.autocommit = False
    cur = conn.cursor()

    import io
    batch_size = 5000
    batch: list = []
    total = 0

    def flush():
        nonlocal batch, total
        if not batch:
            return
        buf = io.StringIO()
        for row in batch:
            buf.write(','.join(_csv_field(row.get(c)) for c in COLS) + '\n')
        buf.seek(0)
        cur.copy_expert(
            f"COPY supply_observations ({','.join(COLS)}) FROM STDIN WITH (FORMAT csv)",
            buf,
        )
        total += len(batch)
        print(f'  restored {total:,} rows')
        batch = []

    with gzip.open(path, 'rt', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            batch.append(json.loads(line))
            if len(batch) >= batch_size:
                flush()
                conn.commit()
    flush()
    conn.commit()
    cur.close()
    conn.close()
    print(f'done: {total:,} rows restored')
    return 0


if __name__ == '__main__':
    if len(sys.argv) != 2:
        print(__doc__, file=sys.stderr)
        sys.exit(2)
    sys.exit(main(Path(sys.argv[1])))
