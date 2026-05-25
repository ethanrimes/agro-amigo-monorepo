#!/usr/bin/env python3
"""One-off: merge the junk 'panela' market into 'Mercado municipal de San Gil'.

Background:
'panela' is a product-name leak that ended up in dim_market under the
SAN GIL city. Migration 023 already had this exact merge in its list,
but the row reappeared since then. The general
``merge_mercado_municipal_to_named.py`` cleanup correctly skipped this
city because its only "named" market is junk, so it requires the
opposite-direction merge: panela -> Mercado municipal de San Gil.

After this script SAN GIL has a single market ('Mercado municipal de San
Gil') with all observations consolidated. If a real named wholesale
market later appears, run ``merge_mercado_municipal_to_named.py`` again
to promote it.

Dry-run: python scripts/fix_sangil_panela.py --dry-run
Live:    python scripts/fix_sangil_panela.py
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

from migrations._dedup_helpers import DIM_INFO, fresh, merge_pair  # noqa: E402

WINNER = "Mercado municipal de San Gil"
LOSER = "panela"


def main(dry_run: bool) -> int:
    print("=" * 60, flush=True)
    print(f"SAN GIL fix: '{LOSER}' -> '{WINNER}'", flush=True)
    print("=" * 60, flush=True)
    if dry_run:
        print("MODE: DRY RUN", flush=True)

    conn, c = fresh()
    alias_tbl, alias_fk, fact_refs, child_refs = DIM_INFO["dim_market"]
    n, conn, c, status = merge_pair(
        conn, c, "dim_market", alias_tbl, alias_fk, fact_refs, child_refs,
        winner_name=WINNER, loser_name=LOSER, dry_run=dry_run,
    )
    if status == "ok":
        print(f"  '{LOSER}' -> '{WINNER}' ({n} fact rows)", flush=True)
    elif status == "would_merge":
        print(f"  [DRY] '{LOSER}' -> '{WINNER}'", flush=True)
    elif status == "loser_absent":
        print(f"  no-op: '{LOSER}' not present", flush=True)
    elif status == "winner_missing":
        print(f"  ERROR: winner '{WINNER}' not found", flush=True)
        conn.close()
        return 1
    else:
        print(f"  status: {status}", flush=True)
    conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main(dry_run="--dry-run" in sys.argv))
