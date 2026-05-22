"""
Shared helpers for hand-picked dedup migrations (034, 038, ...).

Pulls the same machinery used by 034 but routes DB connections through
`backend.supabase_client.get_db_connection`, which understands the
direct -> txn-pooler -> session-pooler fallback configured in .env.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

from psycopg2.extras import RealDictCursor

# Make backend importable when this file is loaded as part of the migrations pkg
_BACKEND_PATH = Path(__file__).resolve().parent.parent
if str(_BACKEND_PATH) not in sys.path:
    sys.path.insert(0, str(_BACKEND_PATH))

from backend.supabase_client import get_db_connection  # noqa: E402


# Per-dim metadata for merge_pair()
# (alias_table, alias_fk, fact_tables[(table, fk)], child_dim_tables[(table, fk)])
DIM_INFO = {
    "dim_subcategory": (
        "alias_subcategory", "subcategory_id",
        [("price_observations", "subcategory_id")],
        [("dim_product", "subcategory_id")],
    ),
    "dim_department": (
        None, None,
        [("price_observations", "department_id"),
         ("insumo_prices_municipality", "department_id"),
         ("insumo_prices_department", "department_id")],
        [("dim_city", "department_id")],
    ),
    "dim_city": (
        "alias_city", "city_id",
        [("price_observations", "city_id"),
         ("supply_observations", "city_id"),
         ("insumo_prices_municipality", "city_id")],
        [("dim_market", "city_id")],
    ),
    "dim_market": (
        "alias_market", "market_id",
        [("price_observations", "market_id"),
         ("supply_observations", "market_id")],
        [],
    ),
    "dim_presentation": (
        "alias_presentation", "presentation_id",
        [("price_observations", "presentation_id")],
        [],
    ),
    "dim_units": (
        "alias_units", "units_id",
        [("price_observations", "units_id")],
        [],
    ),
    "dim_product": (
        "alias_product", "product_id",
        [("price_observations", "product_id"),
         ("supply_observations", "product_id")],
        [],
    ),
    "dim_insumo": (
        "alias_insumo", "insumo_id",
        [("insumo_prices_municipality", "insumo_id"),
         ("insumo_prices_department", "insumo_id")],
        [],
    ),
    "dim_casa_comercial": (
        "alias_casa_comercial", "casa_comercial_id",
        [("insumo_prices_department", "casa_comercial_id")],
        [],
    ),
}


def fresh():
    """Open a fresh DB connection using the fallback-aware client.

    We always request ``new_connection=True`` so that we don't reuse a stale
    cached connection across long-running merge passes, and we attach a
    ``RealDictCursor`` so ``cur.fetchone()['id']`` style access (used below)
    works.
    """
    conn = get_db_connection(new_connection=True)
    conn.autocommit = True
    return conn, conn.cursor(cursor_factory=RealDictCursor)


def find_id(c, table, name):
    c.execute(f"SELECT id FROM {table} WHERE canonical_name = %s", (name,))
    r = c.fetchone()
    return r["id"] if r else None


def table_exists(c, table_name: str) -> bool:
    c.execute(
        "SELECT 1 FROM information_schema.tables WHERE table_name = %s",
        (table_name,),
    )
    return c.fetchone() is not None


def column_exists(c, table_name: str, column_name: str) -> bool:
    c.execute(
        "SELECT 1 FROM information_schema.columns "
        "WHERE table_name = %s AND column_name = %s",
        (table_name, column_name),
    )
    return c.fetchone() is not None


def repoint_fact(conn, c, table, col, old_id, new_id):
    if not column_exists(c, table, col):
        return 0, conn, c
    total = 0
    retries = 0
    while True:
        try:
            c.execute(
                f"WITH b AS (SELECT id FROM {table} WHERE {col} = %s LIMIT 5000) "
                f"UPDATE {table} SET {col} = %s WHERE id IN (SELECT id FROM b)",
                (old_id, new_id),
            )
            n = c.rowcount
            if n == 0:
                break
            total += n
            retries = 0
        except Exception as e:
            msg = str(e)
            # Non-transient errors should not be retried
            if "does not exist" in msg or "undefined" in msg.lower():
                print(f"      [skip] {table}.{col}: {msg.splitlines()[0]}", flush=True)
                return total, conn, c
            retries += 1
            if retries > 5:
                print(f"      [give up] {table}.{col}: {msg.splitlines()[0]}", flush=True)
                return total, conn, c
            print(f"      [retry {retries}] {table}.{col}: {e}", flush=True)
            try:
                conn.close()
            except Exception:
                pass
            conn, c = fresh()
    return total, conn, c


def merge_pair(conn, c, dim, alias_tbl, alias_fk, fact_refs, child_refs,
               winner_name, loser_name, dry_run):
    winner_id = find_id(c, dim, winner_name)
    if not winner_id:
        return None, conn, c, "winner_missing"
    loser_id = find_id(c, dim, loser_name)
    if not loser_id:
        return None, conn, c, "loser_absent"
    if winner_id == loser_id:
        return None, conn, c, "same"

    if dry_run:
        return loser_id, conn, c, "would_merge"

    if alias_tbl and alias_fk:
        try:
            c.execute(
                f"DELETE FROM {alias_tbl} WHERE {alias_fk} = %s "
                f"AND raw_value IN (SELECT raw_value FROM {alias_tbl} WHERE {alias_fk} = %s)",
                (loser_id, winner_id),
            )
            c.execute(
                f"UPDATE {alias_tbl} SET {alias_fk} = %s WHERE {alias_fk} = %s",
                (winner_id, loser_id),
            )
        except Exception as e:
            print(f"      [retry alias] {e}", flush=True)
            try: conn.close()
            except: pass
            conn, c = fresh()

    fact_total = 0
    for ft, fc in fact_refs:
        if not table_exists(c, ft):
            continue
        n, conn, c = repoint_fact(conn, c, ft, fc, loser_id, winner_id)
        fact_total += n

    for ct, cc in child_refs:
        try:
            c.execute(
                f"UPDATE {ct} SET {cc} = %s WHERE {cc} = %s",
                (winner_id, loser_id),
            )
        except Exception as e:
            print(f"      [retry child {ct}] {e}", flush=True)
            try: conn.close()
            except: pass
            conn, c = fresh()

    if alias_tbl and alias_fk:
        try:
            c.execute(
                f"INSERT INTO {alias_tbl} (raw_value, {alias_fk}) VALUES (%s, %s) "
                f"ON CONFLICT (raw_value) DO NOTHING",
                (loser_name, winner_id),
            )
        except Exception as e:
            print(f"      [alias backfill warn] {e}", flush=True)
            try: conn.close()
            except: pass
            conn, c = fresh()

    try:
        if alias_tbl and alias_fk:
            c.execute(f"DELETE FROM {alias_tbl} WHERE {alias_fk} = %s", (loser_id,))
        c.execute(f"DELETE FROM {dim} WHERE id = %s", (loser_id,))
    except Exception as e:
        print(f"      [retry delete] {e}", flush=True)
        try: conn.close()
        except: pass
        conn, c = fresh()

    return fact_total, conn, c, "ok"


def run_table(conn, c, dim, merges, dry_run=False):
    alias_tbl, alias_fk, fact_refs, child_refs = DIM_INFO[dim]
    print(f"\n=== {dim} : {len(merges)} groups ===", flush=True)

    c.execute(f"SELECT COUNT(*) AS n FROM {dim}")
    before = c.fetchone()["n"]

    merged = skipped = missing_winner = 0
    for winner, losers in merges:
        if not find_id(c, dim, winner):
            promoted = False
            for ln in losers:
                lid = find_id(c, dim, ln)
                if lid:
                    if dry_run:
                        print(f"  [DRY] promote {ln} -> {winner}", flush=True)
                    else:
                        try:
                            c.execute(
                                f"UPDATE {dim} SET canonical_name = %s WHERE id = %s",
                                (winner, lid),
                            )
                            print(f"  promote: '{ln}' -> '{winner}'", flush=True)
                        except Exception as e:
                            print(f"  [warn] promote failed: {e}", flush=True)
                            try: conn.close()
                            except: pass
                            conn, c = fresh()
                    promoted = True
                    break
            if not promoted:
                missing_winner += 1
                continue
        for loser in losers:
            if loser == winner:
                continue
            n, conn, c, status = merge_pair(
                conn, c, dim, alias_tbl, alias_fk, fact_refs, child_refs,
                winner, loser, dry_run,
            )
            if status == "ok":
                merged += 1
                if n is not None and n > 0:
                    print(f"  '{loser}' -> '{winner}' ({n} fact rows)", flush=True)
                else:
                    print(f"  '{loser}' -> '{winner}'", flush=True)
            elif status == "would_merge":
                merged += 1
                print(f"  [DRY] '{loser}' -> '{winner}'", flush=True)
            else:
                skipped += 1

    c.execute(f"SELECT COUNT(*) AS n FROM {dim}")
    after = c.fetchone()["n"]
    print(f"  result: merged {merged}, skipped {skipped}, missing-winner {missing_winner}, "
          f"rows {before} -> {after}", flush=True)
    return conn, c
