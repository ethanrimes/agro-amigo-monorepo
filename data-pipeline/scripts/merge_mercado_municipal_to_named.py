#!/usr/bin/env python3
"""
Merge generic "Mercado municipal de X" markets into the named wholesale
market in the same city, then delete the generic ones.

For every dim_city that has BOTH at least one "Mercado municipal de %"
market AND at least one named (non-"Mercado municipal de %") market, we
pick the named market with the most price_observations + supply_observations
as the winner and merge every "Mercado municipal de %" market in that
city into it.

Cities with only "Mercado municipal de %" markets are skipped (no merge
target). Cities with only named markets are skipped (nothing to merge).

Also unconditionally merges 'CMA' -> 'Central Mayorista de Antioquia' at
the start, in case SIPSA re-emits the abbreviation.

Dry-run: python scripts/merge_mercado_municipal_to_named.py --dry-run
Live:    python scripts/merge_mercado_municipal_to_named.py
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / ".env")

if sys.platform == "win32":
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from migrations._dedup_helpers import (  # noqa: E402
    DIM_INFO,
    fresh,
    merge_pair,
)

MUNI_PREFIX = "mercado municipal de "  # case-folded comparison


def merge_cma(conn, c, dry_run: bool):
    alias_tbl, alias_fk, fact_refs, child_refs = DIM_INFO["dim_market"]
    n, conn, c, status = merge_pair(
        conn, c, "dim_market", alias_tbl, alias_fk, fact_refs, child_refs,
        winner_name="Central Mayorista de Antioquia",
        loser_name="CMA",
        dry_run=dry_run,
    )
    if status == "ok":
        print(f"  CMA -> Central Mayorista de Antioquia ({n} fact rows)", flush=True)
    elif status == "would_merge":
        print("  [DRY] CMA -> Central Mayorista de Antioquia", flush=True)
    else:
        print(f"  CMA: {status}", flush=True)
    return conn, c


def discover_city_groups(c) -> list[dict]:
    """Return one group per city that has both kinds of markets, with
    winner pre-chosen (named market with the most observations)."""
    c.execute(
        """
        WITH market_counts AS (
            SELECT
                m.id,
                m.canonical_name,
                m.city_id,
                COALESCE((SELECT COUNT(*) FROM price_observations WHERE market_id = m.id), 0)
              + COALESCE((SELECT COUNT(*) FROM supply_observations WHERE market_id = m.id), 0)
                AS n_obs
            FROM dim_market m
        )
        SELECT mc.id::text AS id,
               mc.canonical_name,
               mc.city_id::text AS city_id,
               mc.n_obs,
               ct.canonical_name AS city_name
        FROM market_counts mc
        JOIN dim_city ct ON ct.id = mc.city_id
        ORDER BY mc.city_id, mc.n_obs DESC, mc.canonical_name
        """
    )
    by_city: dict[str, dict] = {}
    for r in c.fetchall():
        bucket = by_city.setdefault(
            r["city_id"],
            {"city_name": r["city_name"], "mun": [], "named": []},
        )
        if r["canonical_name"].lower().startswith(MUNI_PREFIX):
            bucket["mun"].append(r)
        else:
            bucket["named"].append(r)

    groups = []
    for cid, info in by_city.items():
        if not (info["mun"] and info["named"]):
            continue
        # named[] is already ordered DESC by n_obs (then canonical_name asc)
        winner = info["named"][0]
        # Sanity: the "named" market must dominate the largest mercado_municipal
        # in the same city. Otherwise the named candidate is almost certainly
        # a junk entry (product/dept name leaked into the market column) and
        # the right answer is to leave the data alone and surface a warning.
        biggest_muni = max(info["mun"], key=lambda r: r["n_obs"])
        if winner["n_obs"] < biggest_muni["n_obs"]:
            print(
                f"\n[{info['city_name']}] SKIP: winner candidate "
                f"'{winner['canonical_name']}' has {winner['n_obs']:,} obs but "
                f"'{biggest_muni['canonical_name']}' has {biggest_muni['n_obs']:,} obs — "
                f"named market is likely junk, manual review required.",
                flush=True,
            )
            continue
        groups.append(
            {
                "city_id": cid,
                "city_name": info["city_name"],
                "winner": winner,
                "losers": info["mun"],
            }
        )
    # Stable ordering for log readability.
    groups.sort(key=lambda g: g["city_name"])
    return groups


def main(dry_run: bool) -> int:
    print("=" * 60, flush=True)
    print("Merge 'Mercado municipal de X' -> named markets", flush=True)
    print("=" * 60, flush=True)
    if dry_run:
        print("MODE: DRY RUN", flush=True)

    conn, c = fresh()

    print("\n--- CMA dedup ---", flush=True)
    conn, c = merge_cma(conn, c, dry_run)

    print("\n--- Discovering per-city groups ---", flush=True)
    groups = discover_city_groups(c)
    print(f"Cities with both kinds of markets: {len(groups)}", flush=True)
    if not groups:
        conn.close()
        return 0

    alias_tbl, alias_fk, fact_refs, child_refs = DIM_INFO["dim_market"]
    merged = skipped = 0
    for g in groups:
        winner = g["winner"]
        print(
            f"\n[{g['city_name']}] winner = '{winner['canonical_name']}' "
            f"({winner['n_obs']:,} obs)",
            flush=True,
        )
        for loser in g["losers"]:
            n, conn, c, status = merge_pair(
                conn, c, "dim_market", alias_tbl, alias_fk, fact_refs, child_refs,
                winner_name=winner["canonical_name"],
                loser_name=loser["canonical_name"],
                dry_run=dry_run,
            )
            if status == "ok":
                merged += 1
                print(
                    f"  '{loser['canonical_name']}' "
                    f"({loser['n_obs']:,} obs) -> '{winner['canonical_name']}' "
                    f"({n} fact rows)",
                    flush=True,
                )
            elif status == "would_merge":
                merged += 1
                print(
                    f"  [DRY] '{loser['canonical_name']}' "
                    f"({loser['n_obs']:,} obs) -> '{winner['canonical_name']}'",
                    flush=True,
                )
            else:
                skipped += 1
                print(f"  SKIP '{loser['canonical_name']}': {status}", flush=True)

    print(f"\nMerged: {merged}  Skipped: {skipped}", flush=True)
    c.execute("SELECT COUNT(*) AS n FROM dim_market")
    print(f"remaining dim_market rows: {c.fetchone()['n']}", flush=True)
    conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main(dry_run="--dry-run" in sys.argv))
