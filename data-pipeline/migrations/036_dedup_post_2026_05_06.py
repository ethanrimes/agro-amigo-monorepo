#!/usr/bin/env python3
"""
Migration 036: Auto-merge new canonical entities created during the
2026-05-06 pipeline run into their pre-existing duplicates.

Background: every populate-dimensions / process-abastecimiento run can produce
case/accent/spacing/punctuation variants of dim_* canonical names (driven by
ALL-CAPS DIVIPOLA names, source-PDF doubled glyphs, etc.). Migration 034
fixed a previous batch by hand. This migration handles the batch produced
by the 2026-05-06 run.

Strategy: load the diff output from /tmp/dedup-diff (or a path passed as
argument) and merge every NEW row into the EXISTING row in the same
normalized-key group. NEW+NEW groups (no existing canonical to merge into)
are skipped with a warning — they need a manual decision because we don't
know which variant should win.

Run:
    python -m migrations.036_dedup_post_2026_05_06 [--dry-run] [--diff-dir <path>]
"""
from __future__ import annotations

import argparse
import os
import re
import sys
import unicodedata
from collections import defaultdict
from pathlib import Path

import psycopg2
from psycopg2.extras import RealDictCursor
from dotenv import load_dotenv

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE.parent))
load_dotenv(_HERE.parent / ".env")

if sys.platform == "win32":
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

DB_URL = os.getenv("SUPABASE_DB_URL")


# ============================================================
# Reuse merge infrastructure from migration 034
# ============================================================

# Per-dim metadata: (dim_table, alias_table, alias_fk,
#                    [(fact_table, fk_col)],
#                    [(child_dim_table, fk_col)])
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
}


def fresh():
    conn = psycopg2.connect(DB_URL, cursor_factory=RealDictCursor)
    conn.autocommit = True
    c = conn.cursor()
    c.execute("SET statement_timeout = '180s'")
    return conn, c


def repoint_fact(conn, c, table, col, old_id, new_id):
    """Repoint a fact-table FK in 5k-row batches; reconnect on failure."""
    total = 0
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
        except Exception as e:
            print(f"      [retry] {table}.{col}: {e}", flush=True)
            try:
                conn.close()
            except Exception:
                pass
            conn, c = fresh()
    return total, conn, c


def merge_pair_by_id(conn, c, dim, alias_tbl, alias_fk, fact_refs, child_refs,
                     winner_id, loser_id, loser_name, dry_run):
    """Merge loser into winner by ID. Used when both winner and loser
    have already-known UUIDs (from the snapshot diff)."""
    if winner_id == loser_id:
        return None, conn, c, "same"
    if dry_run:
        return loser_id, conn, c, "would_merge"

    # 1. Repoint alias table (handle UNIQUE conflicts on raw_value)
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

    # 2. Repoint fact tables
    fact_total = 0
    for ft, fc in fact_refs:
        n, conn, c = repoint_fact(conn, c, ft, fc, loser_id, winner_id)
        fact_total += n

    # 3. Repoint child dim tables
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

    # 4. Add the loser's canonical_name as a raw_value alias on the winner
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

    # 5. Delete the loser dim row
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


# ============================================================
# Load snapshot diff and build merge plan
# ============================================================

def strip_accents(s: str) -> str:
    nfkd = unicodedata.normalize("NFKD", s)
    return "".join(c for c in nfkd if not unicodedata.combining(c))


def is_doubled(s: str) -> bool:
    if len(s) < 4:
        return False
    pairs = sum(1 for i in range(0, len(s) - 1, 2) if s[i] == s[i + 1])
    return pairs >= len(s) * 0.3


def undouble(s: str) -> str:
    out = []
    i = 0
    while i < len(s):
        out.append(s[i])
        if i + 1 < len(s) and s[i] == s[i + 1]:
            i += 2
        else:
            i += 1
    return "".join(out)


def norm_key(s: str) -> str:
    if not s:
        return ""
    if is_doubled(s):
        s = undouble(s)
    s = strip_accents(s.strip()).lower()
    s = re.sub(r"[^\w\s]", " ", s, flags=re.UNICODE)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def load_tsv(path: Path) -> list[dict]:
    rows = []
    if not path.exists():
        return rows
    with path.open(encoding="utf-8") as f:
        header = next(f).rstrip("\n").split("\t")
        for line in f:
            cols = line.rstrip("\n").split("\t")
            if len(cols) < 2:
                continue
            rows.append(dict(zip(header, cols)))
    return rows


def build_plan(before_dir: Path, after_dir: Path, dim: str):
    """Return list of (winner_id, winner_name, loser_id, loser_name, group_size)
    for the given dim_* table.

    Strategy: group both before-existing and after-only rows by norm_key.
    For each group with at least one EXISTING (i.e., present in before),
    pick the existing row with the highest cnt_total as the winner; merge all
    NEW rows in the same group into it.

    Skipped groups (returned as `unresolved`):
      * NEW + NEW only (no EXISTING anchor) — needs human pick.
    """
    before = load_tsv(before_dir / f"{dim}.tsv")
    after = load_tsv(after_dir / f"{dim}.tsv")

    before_ids = {r["id"] for r in before}
    after_by_id = {r["id"]: r for r in after}

    # Group all after-rows by norm_key
    by_key = defaultdict(list)
    for r in after:
        k = norm_key(r["canonical_name"])
        if not k:
            continue
        by_key[k].append(r)

    plan: list[tuple] = []
    unresolved: list[tuple] = []
    for k, members in by_key.items():
        existing = [m for m in members if m["id"] in before_ids]
        new = [m for m in members if m["id"] not in before_ids]
        if not new:
            continue
        if not existing:
            # NEW + NEW only
            unresolved.append((k, new))
            continue

        # Winner = existing with highest cnt_total
        def total(m):
            try:
                return int(m.get("cnt_total", "0") or "0")
            except ValueError:
                return 0
        winner = max(existing, key=total)

        for n in new:
            plan.append((winner["id"], winner["canonical_name"],
                         n["id"], n["canonical_name"], len(members)))

    return plan, unresolved


def run_table(conn, c, dim: str, plan: list[tuple], unresolved: list[tuple],
              dry_run: bool):
    info = DIM_INFO.get(dim)
    if info is None:
        # dim_category, dim_insumo_grupo, dim_insumo_subgrupo, dim_casa_comercial
        # were not in DIM_INFO from migration 034; we don't auto-merge them.
        if plan or unresolved:
            print(f"\n=== {dim} : skipped (no DIM_INFO) ===", flush=True)
        return conn, c, 0, 0
    alias_tbl, alias_fk, fact_refs, child_refs = info

    print(f"\n=== {dim} : {len(plan)} merges, {len(unresolved)} unresolved ===",
          flush=True)
    c.execute(f"SELECT COUNT(*) AS n FROM {dim}")
    before_count = c.fetchone()["n"]

    merged = 0
    skipped = 0
    fact_total = 0
    for (winner_id, winner_name, loser_id, loser_name, group_size) in plan:
        n, conn, c, status = merge_pair_by_id(
            conn, c, dim, alias_tbl, alias_fk, fact_refs, child_refs,
            winner_id, loser_id, loser_name, dry_run,
        )
        if status == "ok":
            merged += 1
            if n is not None:
                fact_total += n
            print(f"  '{loser_name}' -> '{winner_name}'"
                  + (f"  ({n} fact rows)" if n else ""), flush=True)
        elif status == "would_merge":
            merged += 1
            print(f"  [DRY] '{loser_name}' -> '{winner_name}'", flush=True)
        else:
            skipped += 1

    if unresolved:
        print(f"\n  --- {dim}: unresolved NEW+NEW groups (need manual pick): ---", flush=True)
        for k, members in unresolved:
            names = ", ".join(repr(m["canonical_name"]) for m in members)
            print(f"    key={k!r}: {names}", flush=True)

    c.execute(f"SELECT COUNT(*) AS n FROM {dim}")
    after_count = c.fetchone()["n"]
    print(f"  result: merged {merged}, skipped {skipped}, "
          f"rows {before_count} -> {after_count}, fact rows touched {fact_total}",
          flush=True)
    return conn, c, merged, skipped


def main():
    import tempfile
    default_before = str(Path(tempfile.gettempdir()) / "dedup-before")
    default_after = str(Path(tempfile.gettempdir()) / "dedup-after")
    p = argparse.ArgumentParser()
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--diff-before", default=default_before)
    p.add_argument("--diff-after", default=default_after)
    args = p.parse_args()

    before_dir = Path(args.diff_before)
    after_dir = Path(args.diff_after)

    print("=" * 60, flush=True)
    print("Migration 036: Auto-dedup canonical entities (post 2026-05-06 run)", flush=True)
    print("=" * 60, flush=True)
    print(f"  Before snapshot: {before_dir}", flush=True)
    print(f"  After snapshot:  {after_dir}", flush=True)
    if args.dry_run:
        print("  MODE: DRY RUN", flush=True)

    if not (before_dir / "dim_city.tsv").exists():
        print(f"ERROR: snapshots missing in {before_dir}. "
              "Run scripts/dump_canonical_entities.py first.", flush=True)
        return 1

    conn, c = fresh()

    # Order matters: merge child dims before parents.
    # dim_city is a parent of dim_market (city_id). Merge it AFTER dim_market
    # so we don't try to delete a city that still has a fallback "Mercado
    # municipal de X" attached. But the merge code does repoint child dim
    # FKs, so order is mostly cosmetic. For safety, do simple dims first.
    ORDER = [
        "dim_subcategory",
        "dim_presentation",
        "dim_units",
        "dim_product",
        "dim_insumo",
        "dim_market",       # before dim_city (its parent)
        "dim_city",
        "dim_department",
    ]

    grand_merged = 0
    grand_skipped = 0
    for dim in ORDER:
        plan, unresolved = build_plan(before_dir, after_dir, dim)
        if not plan and not unresolved:
            continue
        conn, c, merged, skipped = run_table(conn, c, dim, plan, unresolved,
                                              args.dry_run)
        grand_merged += merged
        grand_skipped += skipped

    print("\n" + "=" * 60, flush=True)
    print(f"DONE: merged {grand_merged}, skipped {grand_skipped}", flush=True)
    print("=" * 60, flush=True)
    conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
