#!/usr/bin/env python3
"""
Migration 037: Manual follow-up to migration 036.

The auto-merge in 036 handled cases where a new canonical entity normalized
to the same key as a pre-existing canonical. This migration handles the
NEW+NEW unresolved cases — new canonical names that *also* duplicate an
existing canonical, but the normalized-key matcher missed because of:

  * Disambiguator parentheticals: 'Ipiales (Nariño)' vs 'Ipiales'
  * Different glyphs: 'Bogotà' (grave) vs 'Bogotá' (acute, then ', D.C.' suffix)
  * Spelling typos: 'Chibolo' vs 'Chivolo'
  * Word concatenation in OCR: 'Bananocriollo' vs 'Banano criollo'
  * Doubled-glyph OCR with embedded space breaking is_doubled():
    'CCaarrnnee ddee rreess,, mmoorrrriilllloo' vs 'Carne de res, morrillo'

Each entry is hand-picked from the 2026-05-06 dedup-diff and verified
against the after-snapshot.

Run:
    python -m migrations.037_dedup_manual_2026_05_06 [--dry-run]
"""
from __future__ import annotations

import argparse
import os
import sys
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
}


# ============================================================
# Hand-picked merges (winner_canonical, [loser_canonicals])
# ============================================================

CITY_MERGES = [
    ("Bogotá, D.C.", ["Bogotà"]),
    ("Chivolo", ["Chibolo"]),
    ("Cuaspud Carlosama", ["Cuaspud", "Cuaspúd", "CUASPÚD"]),
    ("Donmatías", ["Don Matias"]),
    ("Ipiales", ["Ipiales (Nariño)"]),
    ("Peñol", ["Peñol (Antioquia)"]),
    ("Rionegro", ["Rionegro (Antioquia)"]),
    ("San Vicente De Chucurí", ["San Vicente Del Chucuri"]),
    ("Tuluá", ["Tuluá (Valle del Cauca)"]),
]

MARKET_MERGES = [
    ("Mercado municipal de Bogotá, D.C.", ["Mercado municipal de Bogotà"]),
    ("Mercado municipal de Cuaspud Carlosama",
        ["Mercado municipal de Cuaspud", "Mercado municipal de CUASPUD CARLOSAMA"]),
    ("Mercado municipal de Donmatías", ["Mercado municipal de Don Matias"]),
    ("Mercado municipal de Ipiales", ["Mercado municipal de Ipiales (Nariño)"]),
    ("Mercado municipal de Peñol", ["Mercado municipal de Peñol (Antioquia)"]),
    ("Mercado municipal de Rionegro", ["Mercado municipal de Rionegro (Antioquia)"]),
    ("Mercado municipal de San Vicente De Chucurí",
        ["Mercado municipal de San Vicente de Chucurí",
         "Mercado municipal de San Vicente Del Chucuri"]),
    ("Mercado municipal de Tuluá",
        ["Mercado municipal de Tulua",
         "Mercado municipal de Tuluá (Valle del Cauca)"]),
]

# OCR-doubled glyphs with embedded spaces that broke is_doubled().
# Verified by inspection: each loser is a doubled-char copy of the winner.
PRODUCT_MERGES = [
    ("Ahuyamín (Sakata)", ["AAhhuuyyaammíínn ((ssaakkaattaa))"]),
    ("Ajo importado", ["AAjjoo iimmppoorrttaaddoo"]),
    ("Arveja verde en vaina", ["AArrvveejjaa vveerrddee eenn vvaaiinnaa"]),
    ("Carne de res, bola de brazo", ["CCaarrnnee ddee rreess,, bboollaa ddee bbrraazzoo"]),
    ("Carne de res, morrillo", ["CCaarrnnee ddee rreess,, mmoorrrriilllloo"]),
    ("Cebolla cabezona blanca", ["CCeebboollllaa ccaabbeezzoonnaa bbllaannccaa"]),
    ("Durazno nacional", ["DDuurraazznnoo nnaacciioonnaall"]),
    ("Lechuga Batavia", ["LLeecchhuuggaa BBaattaavviiaa"]),
    ("Limón común", ["LLiimmóónn ccoommúúnn"]),
    ("Papa superior", ["PPaappaa ssuuppeerriioorr"]),
    ("Papa única", ["PPaappaa úúnniiccaa"]),
    ("Pepino cohombro", ["PPeeppiinnoo ccoohhoommbbrroo"]),
    ("Toyo blanco, filete congelado", ["TTooyyoo bbllaannccoo,, ffiilleettee ccoonnggeellaaddoo"]),
    ("Uva verde", ["UUvvaa vveerrddee"]),
    # Word-concatenation OCR errors
    ("Aguacate común", ["Aguacatecomún"]),
    ("Aguacate Papelillo", ["Aguacatepapelillo"]),
    ("Banano criollo", ["Bananocriollo"]),
    ("Café molido", ["Cafémolido"]),
    ("Pepino cohombro", ["Pepinocohombro"]),
    ("Pepino de rellenar", ["Pepinoderellenar"]),
    ("Plátano hartón verde", ["Plátanohartónverde"]),
    ("Tomate Chonto regional", ["Tomatechontoregional"]),
    ("Uva red globel nacional", ["Uvaredglobenacional"]),
    ("Azúcar morena", ["Azúcarmorena"]),
    ("Azúcar Sulfitada", ["Azúcarsulfitada"]),
    ("Papa Parda Pastusa", ["Papapardapastusa"]),
    # Differing word order / casing
    ("Aceite girasol", ["Aceite de Girasol"]),
    # Typo
    ("Berenjena", ["Beranjena"]),
]

# Doubled-glyph presentation/units variants
PRESENTATION_MERGES = [
    # Existed unresolved with no auto match. 'AROBA' is missing accent + r → typo of Arroba.
    ("Arroba", ["AROBA"]),
    ("Caja de icopor", ["Caja icopor"]),
    ("Caja de madera", ["Caja madera", "Caja Madera"]),
    ("Caja de cartón", ["Cajadecartón"]),
    ("Canastilla", ["Canastila"]),
    ("Kilogramo", ["Killogramo", "KILO"]),
    ("Atado/Manojo", ["Atado/manoj o", "Atado/Manoj o"]),
]

UNITS_MERGES = [
    # OCR doubled-with-space variants that didn't undouble
    ("11 Kilogramo", ["11 KKiillooggrraammoo"]),
    ("100 Kilogramo", ["1100 kkiillooggrraammoo", "1100 KKiillooggrraammoo"]),
    ("12,5 Kilogramo", ["1122,,55 kkiillooggrraammoo", "1122,,55 KKiillooggrraammoo"]),
    # Spacing/casing variants
    ("1 Kilogramo", ["1kilo", "1Kilogramo", "1KILOGRAMO", "1 kilo", "1 Kilo",
                     "1 kilogramos", "1 Kilos"]),
    ("10 Kilogramo", ["10Kilogramo", "10KILOGRAMO", "10 kilo"]),
    ("10 Kilogramos", ["10 kilos", "10 Kilos", "10 KILOS"]),
    ("11 Kilogramo", ["11kilogramo", "11 Kg", "11 KG"]),
    ("12 Kilogramo", ["12 KG", "12 kilogramos", "12kilogramo"]),
    ("12 Kilos", ["12 kilos", "12 KILOS"]),
    ("12 Unidad 180 GR", ["12 Unidad 180 g"]),
    ("12 Unidad 200 GR", ["12 Unidad 200 G"]),
    ("12 Unidad 250 GR", ["12 Unidad- 250 g", "12 Unidad-250 g"]),
    ("12 Unidades de 1000 CC", ["12 unidades de 1000 cc", "12 Unidades de 1000 cc"]),
    ("12,5 Kilogramo", ["12,5KILOGRAMO", "12.5Kilogramo"]),
    ("1 Kilogramo", ["1 kg", "1 Kg", "1 KG"]),
    ("10 Kilogramo", ["10 kg", "10 Kg", "10 KG"]),
    ("50 Kilogramo", ["50Kilogramo", "50KILOGRAMO"]),
    ("2,5 Kilogramos", ["2,5 kilogramos"]),
    ("1 Unidad de 50 GR", ["1 unidad de 50 g"]),
]


# ============================================================
# Merge engine (copy of merge_pair from migration 034)
# ============================================================

def fresh():
    conn = psycopg2.connect(DB_URL, cursor_factory=RealDictCursor)
    conn.autocommit = True
    c = conn.cursor()
    c.execute("SET statement_timeout = '180s'")
    return conn, c


def find_id(c, table, name):
    c.execute(f"SELECT id FROM {table} WHERE canonical_name = %s", (name,))
    r = c.fetchone()
    return r["id"] if r else None


def repoint_fact(conn, c, table, col, old_id, new_id):
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


def run_table(conn, c, dim, merges, dry_run):
    info = DIM_INFO.get(dim)
    if info is None:
        return conn, c, 0, 0
    alias_tbl, alias_fk, fact_refs, child_refs = info

    print(f"\n=== {dim} : {len(merges)} groups ===", flush=True)
    c.execute(f"SELECT COUNT(*) AS n FROM {dim}")
    before = c.fetchone()["n"]

    merged = skipped = 0
    for winner, losers in merges:
        if not find_id(c, dim, winner):
            print(f"  [skip] winner missing: {winner!r}", flush=True)
            continue
        for loser in losers:
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
            elif status == "loser_absent":
                pass  # already merged or never existed
            else:
                skipped += 1
                print(f"  [skip {status}] '{loser}' -> '{winner}'", flush=True)

    c.execute(f"SELECT COUNT(*) AS n FROM {dim}")
    after = c.fetchone()["n"]
    print(f"  result: merged {merged}, skipped {skipped}, rows {before} -> {after}",
          flush=True)
    return conn, c, merged, skipped


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args()

    print("=" * 60, flush=True)
    print("Migration 037: Manual NEW+NEW dedup (post 2026-05-06 run)", flush=True)
    print("=" * 60, flush=True)
    if args.dry_run:
        print("MODE: DRY RUN", flush=True)

    conn, c = fresh()

    plan = [
        ("dim_product", PRODUCT_MERGES),
        ("dim_presentation", PRESENTATION_MERGES),
        ("dim_units", UNITS_MERGES),
        ("dim_market", MARKET_MERGES),
        ("dim_city", CITY_MERGES),
    ]
    grand_merged = 0
    grand_skipped = 0
    for dim, merges in plan:
        conn, c, m, s = run_table(conn, c, dim, merges, args.dry_run)
        grand_merged += m
        grand_skipped += s

    print("\n" + "=" * 60, flush=True)
    print(f"DONE: merged {grand_merged}, skipped {grand_skipped}", flush=True)
    print("=" * 60, flush=True)
    conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
