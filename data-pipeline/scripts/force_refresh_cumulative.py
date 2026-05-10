"""
One-shot helper to force-refresh cumulative SIPSA files that are updated
in-place at static URLs (insumos mun/dep, rice current year, abastecimiento current year).

Strategy per file:
  1. Delete child rows from destination table where download_entry_id = X
  2. Delete the download_entry row
  3. Delete local file copy (for insumos/abastecimiento)
  4. Delete storage object (for rice)

Then the caller re-runs `scrape-* --current` to download a fresh copy and
`process-*` to ingest it.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

from dotenv import load_dotenv
import psycopg2

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE.parent))
load_dotenv(_HERE.parent / ".env")

from backend.supabase_client import get_supabase_client  # noqa: E402

# (download_link, destination_table, storage_kind)
TARGETS = [
    ("https://www.dane.gov.co/files/operaciones/SIPSA/anex-SIPSArroz-SerieHistoricaPrecio-2026.xlsx",
     "processed_prices", "supabase"),
    ("https://www.dane.gov.co/files/operaciones/SIPSA/anex-SIPSAInsumos-SeriesHistoricasMun-2021-2026.xlsx",
     "insumo_prices_municipality", "local"),
    ("https://www.dane.gov.co/files/operaciones/SIPSA/anex-SIPSAInsumos-SeriesHistoricasDep-2018-2026.xlsx",
     "insumo_prices_department", "local"),
    ("https://www.dane.gov.co/files/operaciones/SIPSA/anex-Microdato-abastecimiento-2026.xlsx",
     "supply_observations", "local"),
]


def main() -> None:
    sb = get_supabase_client()
    conn = psycopg2.connect(os.environ["SUPABASE_DB_URL"])
    conn.autocommit = True
    with conn.cursor() as cur:
        cur.execute("SET statement_timeout = '600s'")
    conn.autocommit = False

    for url, dest_table, kind in TARGETS:
        filename = url.rsplit("/", 1)[-1]
        print(f"\n=== {filename} ===")
        existing = sb.table("download_entries").select("id, storage_path").eq("download_link", url).execute().data
        if not existing:
            print("  no entry, nothing to do")
            continue
        entry = existing[0]
        eid = entry["id"]
        storage_path = entry["storage_path"]
        print(f"  entry_id={eid}")
        print(f"  storage_path={storage_path}")

        def batch_delete(table_name: str) -> int:
            total = 0
            while True:
                with conn.cursor() as cur:
                    cur.execute(
                        f"DELETE FROM {table_name} WHERE id IN ("
                        f"  SELECT id FROM {table_name} WHERE download_entry_id = %s LIMIT 50000"
                        f")",
                        (eid,),
                    )
                    n = cur.rowcount
                conn.commit()
                total += n
                print(f"    {table_name}: batch deleted {n} (running total {total})", flush=True)
                if n == 0:
                    return total

        if dest_table == "processed_prices":
            n = batch_delete("price_observations")
            print(f"  deleted {n} rows from price_observations")
        n = batch_delete(dest_table)
        print(f"  deleted {n} rows from {dest_table}")

        with conn.cursor() as cur:
            cur.execute("DELETE FROM download_entries WHERE id = %s", (eid,))
        conn.commit()
        print("  deleted download_entry row")

        if kind == "local" and storage_path and storage_path.startswith("local:"):
            local_path = Path(storage_path[len("local:"):])
            if local_path.exists():
                local_path.unlink()
                print(f"  deleted local file: {local_path}")
        elif kind == "supabase" and storage_path:
            try:
                bucket, _, key = storage_path.partition("/")
                # storage_path format: 'rice/<filename>'  -> bucket 'rice', key '<filename>'
                # but our buckets in this repo use 'sipsa-data' with prefixes; check actual bucket
                # Fall back: try common buckets used by other scrapers
                from backend.storage import StorageClient
                sc = StorageClient()
                # StorageClient.delete_file takes a storage_path relative to default bucket
                sc.delete_file(storage_path)
                print(f"  deleted storage object: {storage_path}")
            except Exception as e:
                print(f"  WARN: could not delete storage object {storage_path}: {e}")

    conn.close()
    print("\nDone. Re-run scrape-* --current and process-* to ingest fresh data.")


if __name__ == "__main__":
    main()
