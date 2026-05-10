"""
One-shot helper to dedupe dim_city rows that share the same divipola_code.

dim_city has multiple rows per municipality (e.g., 'Medell\xedn' and 'MEDELL\xcdN' both
mapped to divipola_code 05001). This blocks adding the unique index that the new
self-healing insumos parser depends on.

Strategy per duplicate group:
  - Pick the "best" row to keep:
      1) prefer rows that already have an alias_city pointing at them,
      2) otherwise prefer Title Case (mixed-case) over ALL CAPS,
      3) tiebreak by lowest id.
  - Repoint all FK references to the kept id (alias_city, price_observations,
    supply_observations, insumo_prices_municipality, dim_market).
  - Delete the loser rows.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

from dotenv import load_dotenv
import psycopg2
from psycopg2.extras import RealDictCursor

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

REFERENCING = [
    ("alias_city", "city_id"),
    ("dim_market", "city_id"),
    ("price_observations", "city_id"),
    ("supply_observations", "city_id"),
    ("insumo_prices_municipality", "city_id"),
]


def _is_titlecase(s: str) -> bool:
    return any(c.islower() for c in s) and any(c.isupper() for c in s)


def main() -> None:
    conn = psycopg2.connect(os.environ["SUPABASE_DB_URL"], cursor_factory=RealDictCursor)
    conn.autocommit = True
    with conn.cursor() as cur:
        cur.execute("SET statement_timeout = 900000")

    with conn.cursor() as cur:
        # First get codes that have dupes
        cur.execute(
            """
            SELECT divipola_code FROM dim_city
            WHERE divipola_code IS NOT NULL
            GROUP BY divipola_code
            HAVING count(*) > 1
            """
        )
        dup_codes = [r["divipola_code"] for r in cur.fetchall()]

    groups = []
    for code in dup_codes:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, canonical_name FROM dim_city WHERE divipola_code = %s ORDER BY id",
                (code,),
            )
            rows = cur.fetchall()
            groups.append({
                "divipola_code": code,
                "ids": [r["id"] for r in rows],
                "names": [r["canonical_name"] for r in rows],
            })
    print(f"groups with duplicates: {len(groups)}", flush=True)

    repointed = {tbl: 0 for tbl, _ in REFERENCING}
    deleted = 0

    for g in groups:
        ids = list(g["ids"])  # already UUID objects from psycopg2
        names = list(g["names"])

        # Determine which id has the most alias_city references
        alias_counts = {}
        for city_id in ids:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT count(*) AS n FROM alias_city WHERE city_id = %s",
                    (city_id,),
                )
                alias_counts[city_id] = cur.fetchone()["n"]

        # Score each candidate: more alias references > titlecase > smallest id
        def score(idx: int):
            return (
                alias_counts.get(ids[idx], 0),
                1 if _is_titlecase(names[idx]) else 0,
                -ord(names[idx][0]) if names[idx] else 0,
            )
        keep_idx = max(range(len(ids)), key=score)
        keep_id = ids[keep_idx]
        loser_ids = [ids[i] for i in range(len(ids)) if i != keep_idx]

        # Repoint FK references one loser at a time
        for loser in loser_ids:
            for tbl, col in REFERENCING:
                with conn.cursor() as cur:
                    cur.execute(
                        f"UPDATE {tbl} SET {col} = %s WHERE {col} = %s",
                        (keep_id, loser),
                    )
                    if cur.rowcount:
                        repointed[tbl] += cur.rowcount

            # Delete the loser (collapse any newly-duplicated alias rows first)
            with conn.cursor() as cur:
                cur.execute(
                    """
                    DELETE FROM alias_city ac
                    USING alias_city ac2
                    WHERE ac.city_id = ac2.city_id
                      AND ac.raw_value = ac2.raw_value
                      AND ac.ctid > ac2.ctid
                    """
                )
                cur.execute("DELETE FROM dim_city WHERE id = %s", (loser,))
                deleted += cur.rowcount

    print("repointed:", repointed)
    print("dim_city rows deleted:", deleted)


if __name__ == "__main__":
    main()
