#!/usr/bin/env python3
"""
Migration 035: Clean up residue from migration 034.

After re-running the candidate finder against post-034 data, three tables had
leftover dups:
  - dim_units: 13 (mostly "N Kg" vs "N KG" pairs I missed)
  - dim_market: 1 (case variants of "Plaza de Mercado del Barrio Bolívar")
  - dim_product: 1 (one doubled-char variant where my merge list had a typo)

This is the cleanup pass.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

# Reuse merge_pair / DIM_INFO from 034
spec = __import__("034_dedup_canonical_entities")  # type: ignore


UNITS_RESIDUE = [
    ("12,5 Kilogramo", ["1122,,55 KKiillooggrraammoo", "1122,,55 kkiillooggrraammoo"]),
    ("12 Unidad 1000 c", ["12 unidad 1000 c", "12 unidad-1000 c"]),
    ("19 Kg", ["19 KG"]),
    ("20 Kilos", ["20 KILOS"]),
    ("22 Kg", ["22 KG"]),
    ("23 Kg", ["23 KG"]),
    ("24 Kg", ["24 KG"]),
    ("24 Unidad 325 G", ["24 Unidad 325 g"]),
    ("25 Kg", ["25 KG"]),
    ("25 Kilo", ["25 KILO"]),
    ("45 Kg", ["45 KG"]),
    ("70 Kg", ["70 KG"]),
    ("9 Kg", ["9 KG"]),
]

MARKET_RESIDUE = [
    ("Plaza de Mercado del Barrio Bolívar",
     ["Plaza de mercado del barrio Bolívar",
      "Plaza de mercado del Barrio Bolívar"]),
]

PRODUCT_RESIDUE = [
    # The actual leftover canonical has doubled ñ AND doubled ó.
    # My 034 list had a single ñ which didn't match.
    ("Tomate riñón valluno", ["TToommaattee rriiññóónn vvaalllluunnoo"]),
]


def run(dry_run=False):
    print("=" * 60, flush=True)
    print("Migration 035: Dedup residue cleanup", flush=True)
    print("=" * 60, flush=True)
    if dry_run:
        print("MODE: DRY RUN", flush=True)

    conn, c = spec.fresh()
    plan = [
        ("dim_units", UNITS_RESIDUE),
        ("dim_market", MARKET_RESIDUE),
        ("dim_product", PRODUCT_RESIDUE),
    ]
    for dim, merges in plan:
        conn, c = spec.run_table(conn, c, dim, merges, dry_run=dry_run)
    print("\nDONE", flush=True)
    conn.close()


if __name__ == "__main__":
    dry_run = "--dry-run" in sys.argv
    run(dry_run=dry_run)
