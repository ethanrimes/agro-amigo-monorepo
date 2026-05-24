"""Reset abastecimiento ingestion so process-abastecimiento re-runs.

Needed after dimension_resolver._resolve_market gained the dim_market fallback —
existing supply_observations rows were all bucketed into "Mercado municipal de <city>"
because alias_market was empty and the old resolver returned None on miss.

Run order:
    python scripts/reprocess_abastecimiento.py
    python -m cli.main process-abastecimiento

Add --dry-run to see counts without touching anything.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.supabase_client import get_db_connection


def main(dry_run: bool) -> int:
    conn = get_db_connection(new_connection=True)
    cur = conn.cursor()

    cur.execute(
        "SELECT COUNT(*) AS n FROM download_entries "
        "WHERE source_table_link = 'abastecimiento_microdatos' "
        "AND processed_status = TRUE"
    )
    entry_count = cur.fetchone()['n']

    cur.execute(
        "SELECT COUNT(*) AS n FROM supply_observations so "
        "JOIN download_entries de ON de.id = so.download_entry_id "
        "WHERE de.source_table_link = 'abastecimiento_microdatos'"
    )
    row_count = cur.fetchone()['n']

    print(f"abastecimiento download_entries to reset: {entry_count}")
    print(f"supply_observations rows to delete:       {row_count}")

    if dry_run:
        print("[dry-run] no changes made")
        cur.close()
        conn.close()
        return 0

    cur.execute(
        "DELETE FROM supply_observations WHERE download_entry_id IN ("
        "SELECT id FROM download_entries "
        "WHERE source_table_link = 'abastecimiento_microdatos')"
    )
    print(f"deleted {cur.rowcount} supply_observations rows")

    cur.execute(
        "UPDATE download_entries SET processed_status = FALSE "
        "WHERE source_table_link = 'abastecimiento_microdatos'"
    )
    print(f"reset {cur.rowcount} download_entries to processed_status=FALSE")

    conn.commit()
    cur.close()
    conn.close()
    print("\nNext: python -m cli.main process-abastecimiento")
    return 0


if __name__ == '__main__':
    sys.exit(main(dry_run='--dry-run' in sys.argv))
