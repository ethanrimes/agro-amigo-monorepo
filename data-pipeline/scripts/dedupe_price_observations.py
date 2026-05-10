"""
One-shot helper to remove duplicate price_observations rows.

The bug: populate-dimensions does INSERT...SELECT into price_observations without
ON CONFLICT, so every run appends a fresh copy of all observations. Until that's
fixed (UNIQUE constraint + ON CONFLICT), this script cleans up the duplicates.

Strategy:
  - Walk processed_price_id values in chunks
  - For each chunk, keep the lowest id per processed_price_id, delete the rest
  - Reconnect on transient connection drops
"""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path

from dotenv import load_dotenv
import psycopg2

load_dotenv(Path(__file__).resolve().parent.parent / ".env")


def newconn():
    c = psycopg2.connect(os.environ["SUPABASE_DB_URL"])
    c.autocommit = True
    with c.cursor() as cur:
        cur.execute("SET statement_timeout = '900s'")
    return c


def main() -> None:
    conn = newconn()
    with conn.cursor() as cur:
        cur.execute("SELECT count(*), count(DISTINCT processed_price_id) FROM price_observations")
        total, distinct = cur.fetchone()
    print(f"start: {total} rows, {distinct} distinct, dupes={total - distinct}", flush=True)

    # Build a persistent staging table of IDs to delete (NOT a TEMP table — pgBouncer
    # transaction-mode pooling drops session state between queries).
    print("building staging table dedupe_targets...", flush=True)
    with conn.cursor() as cur:
        cur.execute("DROP TABLE IF EXISTS dedupe_targets")
        cur.execute(
            """
            CREATE UNLOGGED TABLE dedupe_targets AS
            SELECT id FROM (
                SELECT id, row_number() OVER (
                    PARTITION BY processed_price_id ORDER BY created_at, id
                ) AS rn
                FROM price_observations
            ) sub
            WHERE rn > 1
            """
        )
        cur.execute("CREATE INDEX dedupe_targets_id_idx ON dedupe_targets(id)")
        cur.execute("SELECT count(*) FROM dedupe_targets")
        n_targets = cur.fetchone()[0]
    print(f"  staged {n_targets} duplicate ids", flush=True)

    batch = 30000
    deleted_total = 0
    fail_count = 0
    while True:
        try:
            with conn.cursor() as cur:
                cur.execute(
                    f"""
                    WITH del AS (
                        DELETE FROM dedupe_targets
                        WHERE id IN (SELECT id FROM dedupe_targets LIMIT {batch})
                        RETURNING id
                    )
                    DELETE FROM price_observations po USING del WHERE po.id = del.id
                    """
                )
                n = cur.rowcount
            deleted_total += n
            print(f"  deleted {n} (running total {deleted_total})", flush=True)
            if n == 0:
                break
            fail_count = 0
        except (psycopg2.OperationalError, psycopg2.InterfaceError) as e:
            fail_count += 1
            print(f"  conn error: {e!s} reconnecting (attempt {fail_count})", flush=True)
            if fail_count > 6:
                raise
            time.sleep(5 * fail_count)
            try:
                conn.close()
            except Exception:
                pass
            conn = newconn()

    with conn.cursor() as cur:
        cur.execute("DROP TABLE IF EXISTS dedupe_targets")
        cur.execute("SELECT count(*), count(DISTINCT processed_price_id) FROM price_observations")
        print("done:", cur.fetchone())


if __name__ == "__main__":
    main()
