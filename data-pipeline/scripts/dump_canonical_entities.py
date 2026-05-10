"""
Read-only dump of every dim_* table's canonical_name list, one file per table,
plus per-entity row counts in the fact tables. Output is plain text so a human
(or me, here) can scan it.

Usage:
    python scripts/dump_canonical_entities.py /tmp/dedup
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.supabase_client import get_db_connection


# (dim table, id column, alias table, alias-fk column, fact-table refs as [(table, fk_col)])
DIM_SPECS = [
    ("dim_category", "id", "alias_category", "category_id",
        [("price_observations", "category_id"),
         ("supply_observations", "category_id"),
         ("dim_subcategory", "category_id")]),
    ("dim_subcategory", "id", "alias_subcategory", "subcategory_id",
        [("price_observations", "subcategory_id"),
         ("dim_product", "subcategory_id")]),
    ("dim_product", "id", "alias_product", "product_id",
        [("price_observations", "product_id"),
         ("supply_observations", "product_id")]),
    ("dim_presentation", "id", "alias_presentation", "presentation_id",
        [("price_observations", "presentation_id")]),
    ("dim_units", "id", "alias_units", "units_id",
        [("price_observations", "units_id")]),
    ("dim_department", "id", None, None,
        [("price_observations", "department_id"),
         ("dim_city", "department_id"),
         ("insumo_prices_municipality", "department_id"),
         ("insumo_prices_department", "department_id")]),
    ("dim_city", "id", "alias_city", "city_id",
        [("price_observations", "city_id"),
         ("supply_observations", "city_id"),
         ("dim_market", "city_id"),
         ("insumo_prices_municipality", "city_id")]),
    ("dim_market", "id", "alias_market", "market_id",
        [("price_observations", "market_id"),
         ("supply_observations", "market_id")]),
    ("dim_insumo", "id", "alias_insumo", "insumo_id",
        [("insumo_prices_municipality", "insumo_id"),
         ("insumo_prices_department", "insumo_id")]),
    ("dim_insumo_grupo", "id", "alias_insumo_grupo", "grupo_id",
        [("insumo_prices_municipality", "grupo_id"),
         ("insumo_prices_department", "grupo_id"),
         ("dim_insumo", "grupo_id"),
         ("dim_insumo_subgrupo", "grupo_id")]),
    ("dim_insumo_subgrupo", "id", "alias_insumo_subgrupo", "subgrupo_id",
        [("insumo_prices_municipality", "subgrupo_id"),
         ("insumo_prices_department", "subgrupo_id"),
         ("dim_insumo", "subgrupo_id")]),
    ("dim_casa_comercial", "id", "alias_casa_comercial", "casa_comercial_id",
        [("insumo_prices_department", "casa_comercial_id")]),
]


def main(out_dir: str) -> int:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)

    conn = get_db_connection(new_connection=True)
    cur = conn.cursor()
    cur.execute("SET statement_timeout = '60s'")

    summary = []
    for dim, id_col, alias_tbl, alias_fk, facts in DIM_SPECS:
        # Pass 1: just pull canonical names — fast, indexed, won't time out
        sql = f"SELECT d.{id_col} AS id, d.canonical_name FROM {dim} d ORDER BY d.canonical_name"
        try:
            cur.execute(sql)
            rows = cur.fetchall()
        except Exception as e:
            print(f"[WARN] {dim}: {e}", flush=True)
            conn.rollback()
            continue

        # Pass 2: GROUP BY counts per fact table (uses indexes on FK columns)
        counts = {ft: {} for ft, _ in facts}
        for ft, fc in facts:
            try:
                cur.execute(f"SELECT {fc} AS k, COUNT(*) AS n FROM {ft} GROUP BY {fc}")
                for r in cur.fetchall():
                    if r["k"] is not None:
                        counts[ft][r["k"]] = r["n"]
            except Exception as e:
                print(f"[WARN] {dim}.{ft}.{fc} count: {e}", flush=True)
                conn.rollback()

        path = out / f"{dim}.tsv"
        with path.open("w", encoding="utf-8") as f:
            cols = ["id", "canonical_name"] + [f"cnt_{ft}" for ft, _ in facts] + ["cnt_total"]
            f.write("\t".join(cols) + "\n")
            for r in rows:
                vals = [str(r["id"]), r["canonical_name"]]
                tot = 0
                for ft, _ in facts:
                    n = counts[ft].get(r["id"], 0)
                    vals.append(str(n))
                    tot += n
                vals.append(str(tot))
                f.write("\t".join(vals) + "\n")
        summary.append((dim, len(rows), str(path)))
        print(f"  {dim}: {len(rows)} rows -> {path}", flush=True)

    cur.close()
    conn.close()

    print("\nSummary:")
    for dim, n, p in summary:
        print(f"  {dim}: {n} canonical rows", flush=True)
    return 0


if __name__ == "__main__":
    out = sys.argv[1] if len(sys.argv) > 1 else "/tmp/dedup"
    sys.exit(main(out))
