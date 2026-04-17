#!/usr/bin/env python3
"""
Backfill CPC codes for insumos in mostly-CPC-coded subgrupos.

Strategy per CPC-less insumo:
  1. If its subgrupo uses exactly one CPC code -> assign that code.
  2. Otherwise, fuzzy-match its canonical_name against every CPC'd sibling
     in the same subgrupo (difflib ratio on lowercase names with formulation
     suffixes stripped). If best ratio >= THRESHOLD, adopt the matched
     sibling's CPC code.
  3. Otherwise, adopt the most common CPC code in the subgrupo (mode).

Only touches the 11 subgrupos that have a CPC-coded majority. Leaves
fully-CPC-less subgrupos (Material de propagacion, Arrendamiento de
tierras, Especies productivas, Empaques agropecuarios, Jornales) alone —
those are legitimately CPC-free services/land/animals.

Run:
    python migrations/028_backfill_cpc_codes.py --dry-run     # plan only
    python migrations/028_backfill_cpc_codes.py --apply       # write to DB
"""

from __future__ import annotations
import argparse
import re
import sys
from collections import Counter
from difflib import SequenceMatcher
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from backend.supabase_client import get_db_connection


TARGET_SUBGRUPOS = [
    'Alimentos balanceados, suplementos, coadyuvantes, adsorbentes, enzimas y aditivos',
    'Insecticidas, acaricidas y nematicidas',
    'Herbicidas',
    'Elementos agropecuarios',
    'Antibi\u00f3ticos, antimic\u00f3ticos y antiparasitarios',
    'Fertilizantes, enmiendas y acondicionadores de suelo',
    'Fungicidas',
    'Hormonales',
    'Vitaminas, sales y minerales',
    'Antis\u00e9pticos, desinfectantes e higiene',
    'Medicamentos',
]

# Formulation / pack-size suffixes to strip before name comparison.
# These add noise (e.g., "Regent 200 Sc" vs "Regent Sc 200") without
# changing which product we're talking about.
SUFFIX_PATTERNS = [
    r'\b\d+(\.\d+)?\s*(kg|gr?|g|ml|l|lt|cc|oz|lb)\b',   # pack sizes
    r'\b\d+\s*(sl|sc|ec|ew|wg|wp|cs|od|sp|gr|se|dp|fs|ls)\b',  # formul codes
    r'\b(sl|sc|ec|ew|wg|wp|cs|od|sp|gr|se|dp|fs|ls)\b',        # standalone
    r'\b\d+(%|\.\d+)?\b',                               # standalone numbers
]


def normalize(name: str) -> str:
    s = name.lower()
    for pat in SUFFIX_PATTERNS:
        s = re.sub(pat, ' ', s)
    s = re.sub(r'[^a-z0-9\s]', ' ', s)
    s = re.sub(r'\s+', ' ', s).strip()
    return s


def similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, a, b).ratio()


def plan_backfill(cur):
    # Pull all insumos in target subgrupos, split coded vs uncoded.
    cur.execute(
        '''
        SELECT i.id, i.canonical_name, i.cpc_id, s.canonical_name AS subgrupo
        FROM dim_insumo i
        JOIN dim_insumo_subgrupo s ON s.id = i.subgrupo_id
        WHERE s.canonical_name = ANY(%s)
        ''',
        (TARGET_SUBGRUPOS,),
    )
    rows = cur.fetchall()

    by_sub: dict[str, list] = {}
    for r in rows:
        by_sub.setdefault(r['subgrupo'], []).append(r)

    THRESHOLD = 0.55
    plan = []
    for subgrupo, items in by_sub.items():
        coded = [i for i in items if i['cpc_id']]
        uncoded = [i for i in items if not i['cpc_id']]
        if not coded or not uncoded:
            continue
        cpc_counts = Counter(i['cpc_id'] for i in coded)
        mode_cpc, _ = cpc_counts.most_common(1)[0]
        distinct = len(cpc_counts)

        # Pre-normalize coded names once.
        coded_norm = [(i, normalize(i['canonical_name'])) for i in coded]

        for u in uncoded:
            if distinct == 1:
                plan.append((u, subgrupo, mode_cpc, 'single-code', 1.0, None))
                continue
            u_norm = normalize(u['canonical_name'])
            best = (None, 0.0, None)
            for coded_item, c_norm in coded_norm:
                score = similarity(u_norm, c_norm)
                if score > best[1]:
                    best = (coded_item, score, c_norm)
            if best[0] and best[1] >= THRESHOLD:
                plan.append((u, subgrupo, best[0]['cpc_id'], 'name-match', best[1], best[0]['canonical_name']))
            else:
                plan.append((u, subgrupo, mode_cpc, 'subgrupo-mode', best[1], None))
    return plan


def print_plan(plan):
    by_strategy = Counter(p[3] for p in plan)
    print(f'Total candidates: {len(plan)}')
    print(f'  single-code   : {by_strategy["single-code"]}')
    print(f'  name-match    : {by_strategy["name-match"]}')
    print(f'  subgrupo-mode : {by_strategy["subgrupo-mode"]}')
    print()
    # Group by subgrupo for readable output
    by_sub: dict[str, list] = {}
    for p in plan:
        by_sub.setdefault(p[1], []).append(p)
    for subgrupo, items in by_sub.items():
        print(f'--- {subgrupo} ({len(items)}) ---')
        for u, _, cpc, strategy, score, match_name in items:
            extra = f' (score={score:.2f} vs "{match_name}")' if match_name else ''
            print(f'  {u["canonical_name"][:45]:45} -> CPC {cpc}  [{strategy}]{extra}')
        print()


def apply_plan(cur, plan):
    for u, _, cpc, _, _, _ in plan:
        cur.execute(
            'UPDATE dim_insumo SET cpc_id = %s WHERE id = %s AND cpc_id IS NULL',
            (cpc, u['id']),
        )
    # Also mark the migration as applied.
    cur.execute(
        'CREATE TABLE IF NOT EXISTS schema_migrations '
        '(id SERIAL PRIMARY KEY, name VARCHAR(255) UNIQUE NOT NULL, '
        'executed_at TIMESTAMP DEFAULT NOW())'
    )
    cur.execute(
        'INSERT INTO schema_migrations (name) VALUES (%s) '
        'ON CONFLICT (name) DO NOTHING',
        ('028_backfill_cpc_codes.py',),
    )


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--apply', action='store_true')
    ap.add_argument('--dry-run', action='store_true')
    args = ap.parse_args()
    if not args.apply and not args.dry_run:
        ap.error('pass --dry-run or --apply')

    conn = get_db_connection(new_connection=True)
    cur = conn.cursor()
    try:
        plan = plan_backfill(cur)
        print_plan(plan)
        if args.apply:
            apply_plan(cur, plan)
            conn.commit()
            print(f'APPLIED: updated {len(plan)} rows in dim_insumo.')
    finally:
        cur.close()
        conn.close()


if __name__ == '__main__':
    main()
