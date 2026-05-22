#!/usr/bin/env python3
"""
Migration 038: Hand-picked dedup of canonical entities (post 2026-05-20 1-year rebuild).

This is the SAME pattern as migration 034, but reuses the shared helpers in
``migrations/_dedup_helpers.py`` (which routes through the direct->pooler
fallback in ``backend.supabase_client.get_db_connection``).

The merge lists below are *intentionally empty* until the canonical-entity
dump is reviewed. After ingestion + populate-dimensions completes, run:

    cd data-pipeline
    python scripts/dump_canonical_entities.py session-state/dedup-dump

Then populate the merge lists below with (winner, [losers]) tuples and run:

    python -m migrations.038_dedup_2026_05_20 --dry-run   # preview
    python -m migrations.038_dedup_2026_05_20             # apply

Rules:
  * Proper Spanish accents (Bogotá not Bogota)
  * Sentence case (Carne de cerdo not CARNE DE CERDO)
  * Comma decimals (1,5 Kg not 1.5 Kg)
  * Strip trailing * / +
  * Collapse "X (Department)" qualifiers when unique
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

if sys.platform == "win32":
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from ._dedup_helpers import fresh, run_table  # noqa: E402


# Each entry is (winner_canonical_name, [loser_canonical_names_to_merge_into_winner])
# Populated 2026-05-21 from PROPOSER + 2 independent VALIDATOR agents
# (see session-state/.../dedup-dump/PROPOSALS.tsv and VALIDATION_{A,B}.tsv).
SUBCATEGORY_MERGES: list[tuple[str, list[str]]] = []
PRESENTATION_MERGES: list[tuple[str, list[str]]] = []
UNITS_MERGES: list[tuple[str, list[str]]] = []
MARKET_MERGES: list[tuple[str, list[str]]] = []

CITY_MERGES: list[tuple[str, list[str]]] = [
    ("Armenia", ["ARMENIA"]),
    ("BELÉN", ["Belén"]),
    ("Florencia", ["FLORENCIA"]),
    ("MOSQUERA", ["Mosquera"]),
    ("PUERTO RICO", ["Puerto Rico"]),
    ("SABANALARGA", ["Sabanalarga"]),
    ("SALAMINA", ["Salamina"]),
    ("Santa Bárbara", ["SANTA BÁRBARA"]),
]

DEPARTMENT_MERGES: list[tuple[str, list[str]]] = [
    ("Arauca", ["ARAUCA"]),
    ("Bolívar", ["BOLÍVAR"]),
    ("Caquetá", ["CAQUETÁ"]),
    ("Casanare", ["CASANARE"]),
    ("Cundinamarca", ["CUNDINAMARCA"]),
    ("Magdalena", ["MAGDALENA"]),
    ("Norte de Santander", ["NORTE DE SANTANDER"]),
    ("Putumayo", ["PUTUMAYO"]),
    ("Quindío", ["QUINDÍO"]),
    ("Valle del Cauca", ["VALLE DEL CAUCA"]),
]

PRODUCT_MERGES: list[tuple[str, list[str]]] = [
    ("Aguacate *", ["Aguacate*"]),
    ("Aguacate Choquette", ["Aguacate choquette"]),
    ("Aguacate Hass", ["Aguacate hass"]),
    ("Arracacha", ["Arracacha*"]),
    ("Banano Urabá", ["Banano urabá"]),
    ("Fríjol verde", ["Fríjol verde*"]),
    ("Lechuga Batavia", ["Lechuga batavia"]),
    ("Limón Tahití", ["Limón tahití"]),
    ("Mandarina Arrayana", ["Mandarina arrayana"]),
    ("Mandarina Oneco", ["Mandarina oneco"]),
    ("Mango Tommy", ["Mango tommy"]),
    ("Mango Yulima", ["Mango yulima"]),
    ("Mora de castilla", ["Mora de Castilla"]),
    ("Papa Betina", ["Papa betina"]),
    ("Papa Morasurco", ["Papa morasurco"]),
    ("Papaya Maradol", ["Papaya maradol"]),
    ("Papaya Paulina", ["Papaya paulina"]),
    ("Tomate Riogrande", ["Tomate riogrande"]),
    ("Uva Isabela", ["Uva isabela"]),
    ("Yuca", ["Yuca*"]),
]

INSUMO_MERGES: list[tuple[str, list[str]]] = [
    ("Agua Destilada Estéril", ["Agua destilada estéril"]),
    ("Ametrina 80% Wg", ["Ametrina 80% WG"]),
    ("Creolina Concentrada", ["Creolina concentrada"]),
    ("Lidocaína", ["Lidocaina"]),
    ("Mezclas Guayacán: 31-8-8", ["Mezclas Guayacan: 31-8-8"]),
    ("Novaplant Fósforo", ["Novaplant Fosforo"]),
    ("Nitro Xtend + Mg 39-0-3 + 2(MgO) + 3S", ["Nitro Xtend + Mg 39-0-3 + 2(MgO) + 3s"]),
    ("Teprosyn NP+Zn", ["Teprosyn Np+Zn"]),
]

CASA_COMERCIAL_MERGES: list[tuple[str, list[str]]] = [
    ("SÁFER AGROBIOLOGICOS LTDA.", ["SAFER AGROBIOLOGICOS LTDA."]),
    ("QUÍMICOS Y FERTILIZANTES S.A.S.", ["QUIMICOS Y FERILIZANTES S.A.S."]),
]


def run(dry_run: bool = False) -> None:
    print("=" * 60, flush=True)
    print("Migration 038: 1-year rebuild dedup", flush=True)
    print("=" * 60, flush=True)
    if dry_run:
        print("MODE: DRY RUN", flush=True)

    conn, c = fresh()

    plan = [
        ("dim_subcategory", SUBCATEGORY_MERGES),
        ("dim_presentation", PRESENTATION_MERGES),
        ("dim_units", UNITS_MERGES),
        ("dim_market", MARKET_MERGES),
        ("dim_city", CITY_MERGES),
        ("dim_department", DEPARTMENT_MERGES),
        ("dim_product", PRODUCT_MERGES),
        ("dim_insumo", INSUMO_MERGES),
        ("dim_casa_comercial", CASA_COMERCIAL_MERGES),
    ]
    for dim, merges in plan:
        if not merges:
            print(f"\n=== {dim} : (no merges defined)", flush=True)
            continue
        conn, c = run_table(conn, c, dim, merges, dry_run=dry_run)

    print("\nDONE", flush=True)
    try:
        conn.close()
    except Exception:
        pass


if __name__ == "__main__":
    run(dry_run="--dry-run" in sys.argv)
