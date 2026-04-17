#!/usr/bin/env python3
"""
Migration 019: Consolidate duplicate canonical entities across dimension tables.

Problem: Multiple dim_* entries represent the same real-world entity due to
case variants, accent differences, PDF parsing artifacts (doubled characters),
missing spaces, and punctuation differences.

Approach:
1. Normalize names to find candidate groups
2. Score candidates to pick the best canonical name per group
3. Rewire all aliases and fact table references to the surviving entity
4. Delete duplicates

Run: python -m migrations.019_consolidate_duplicates [--dry-run]
"""

import os
import re
import sys
import unicodedata
from collections import defaultdict
from pathlib import Path

_parent = str(Path(__file__).parent.parent)
if _parent not in sys.path:
    sys.path.insert(0, _parent)

if sys.platform == 'win32':
    os.environ.setdefault('PYTHONIOENCODING', 'utf-8')
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    if hasattr(sys.stderr, 'reconfigure'):
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')

from backend.supabase_client import get_db_connection


# ============================================================
# NORMALIZATION
# ============================================================

def strip_accents(s):
    """Remove accent marks for comparison only."""
    nfkd = unicodedata.normalize('NFKD', s)
    return ''.join(c for c in nfkd if not unicodedata.combining(c))


def is_doubled(s):
    """Detect PDF-garbled doubled-character strings like 'AAhhuuyyaammíínn'."""
    if len(s) < 4:
        return False
    pairs = 0
    for i in range(0, len(s) - 1, 2):
        if s[i] == s[i + 1]:
            pairs += 1
    return pairs >= len(s) * 0.3


def undouble(s):
    """Reverse doubled characters: 'AAhhuuyyaa' -> 'Ahuya'."""
    result = []
    i = 0
    while i < len(s):
        result.append(s[i])
        if i + 1 < len(s) and s[i] == s[i + 1]:
            i += 2
        else:
            i += 1
    return ''.join(result)


def normalize_key(s):
    """
    Produce a comparison key for grouping duplicates.
    Strips accents, lowercases, removes punctuation, collapses whitespace.
    """
    if not s:
        return ''
    # Undouble if garbled
    if is_doubled(s):
        s = undouble(s)
    s = s.strip()
    s = strip_accents(s)
    s = s.lower()
    # Remove asterisks, stars, wildcards
    s = s.replace('*', '').replace('+', '')
    # Remove commas and periods
    s = s.replace(',', '').replace('.', '')
    # Remove parenthetical qualifiers like "(bogotana)" "(regional)" "(Nariño)"
    # but keep meaningful ones like "(sakata)" "(sobre)"
    # Actually, keep all parens for now -- they distinguish products
    # Collapse whitespace
    s = re.sub(r'\s+', ' ', s).strip()
    # Remove leading/trailing hyphens/slashes
    s = s.strip('-/ ')
    return s


# ============================================================
# SCORING -- pick the best canonical name from a group
# ============================================================

def score_name(name):
    """
    Score a candidate name. Higher = better.
    Prefers: proper accents, title case, no garbage, no brand names.
    """
    score = 0

    # Penalize ALL CAPS heavily -- check proportion of uppercase letters
    alpha_chars = [c for c in name if c.isalpha()]
    if alpha_chars:
        upper_ratio = sum(1 for c in alpha_chars if c.isupper()) / len(alpha_chars)
        if upper_ratio > 0.6 and len(alpha_chars) > 5:
            score -= 50  # Mostly uppercase
        elif upper_ratio > 0.4 and len(alpha_chars) > 10:
            score -= 30  # Significantly uppercase

    # Penalize all lowercase
    if name == name.lower() and len(name) > 3:
        score -= 30

    # Penalize doubled/garbled characters
    if is_doubled(name):
        score -= 1000

    # Penalize concatenated words (no spaces where expected)
    if re.search(r'[a-z][A-Z]', name):
        score -= 20  # camelCase-like
    # Penalize missing spaces (lowercase run > 15 chars without space)
    if re.search(r'[a-záéíóúñ]{16,}', name.lower().replace(' ', '')):
        if ' ' not in name:
            score -= 30

    # Reward proper Spanish accents (lowercase accents preferred over uppercase)
    for ch in 'áéíóúñ':
        if ch in name:
            score += 8
    for ch in 'ÁÉÍÓÚÑ':
        if ch in name:
            score += 3

    # Reward sentence case (first char upper, rest mostly lower)
    if name[0].isupper() and not name.isupper():
        score += 15

    # Penalize brand-specific suffixes
    brand_words = ['quaker', 'incauca', 'bastilla', 'nieve', 'super arepa',
                   'corona', 'dagusto', 'frutiño', 'soberana', 'refisal',
                   'fruco', 'doria', 'día', '3 tacos']
    for bw in brand_words:
        if bw in name.lower():
            score -= 40

    # Penalize star/wildcard
    if '*' in name or '+' in name:
        score -= 15

    # Penalize abbreviations
    if 'Cab.' in name:
        score -= 20

    # Penalize consecutive uppercase runs (5+ chars) in mixed-case strings
    # This catches "Mercado municipal de ABEJORRAL" where only the city is caps
    if re.search(r'[A-ZÁÉÍÓÚÑ]{5,}', name) and not name.isupper():
        score -= 25

    # Reward reasonable length (not too short, not too long)
    if 5 < len(name) < 50:
        score += 5

    return score


def pick_canonical(names):
    """Pick the best canonical name from a group of duplicates."""
    scored = [(score_name(n), n) for n in names]
    scored.sort(key=lambda x: (-x[0], x[1]))
    return scored[0][1]


# ============================================================
# MANUAL OVERRIDES -- my judgment on specific merges
# ============================================================

# For products: groups where normalization alone isn't enough.
# Format: normalized_key -> canonical_name to use
PRODUCT_NAME_OVERRIDES = {
    # Meat cuts -- prefer comma-separated SIPSA convention
    'carne de cerdo brazo con hueso': 'Carne de cerdo, brazo con hueso',
    'carne de cerdo brazo sin hueso': 'Carne de cerdo, brazo sin hueso',
    'carne de cerdo cabeza de lomo': 'Carne de cerdo, cabeza de lomo',
    'carne de cerdo costilla': 'Carne de cerdo, costilla',
    'carne de cerdo espinazo': 'Carne de cerdo, espinazo',
    'carne de cerdo lomo con hueso': 'Carne de cerdo, lomo con hueso',
    'carne de cerdo lomo sin hueso': 'Carne de cerdo, lomo sin hueso',
    'carne de cerdo pernil con hueso': 'Carne de cerdo, pernil con hueso',
    'carne de cerdo pernil sin hueso': 'Carne de cerdo, pernil sin hueso',
    'carne de cerdo tocineta plancha': 'Carne de cerdo, tocineta plancha',
    'carne de cerdo tocino barriga': 'Carne de cerdo, tocino barriga',
    'carne de cerdo tocino papada': 'Carne de cerdo, tocino papada',
    'carne de cerdo brazo costilla': 'Carne de cerdo, brazo costilla',
    'carne de cerdo costilla con hueso': 'Carne de cerdo, costilla con hueso',
    'carne de cerdo en canal': 'Carne de cerdo en canal',
    'carne de res bola de brazo': 'Carne de res, bola de brazo',
    'carne de res bola de pierna': 'Carne de res, bola de pierna',
    'carne de res bolade brazo': 'Carne de res, bola de brazo',
    'carne de res bolade pierna': 'Carne de res, bola de pierna',
    'carne de res bota': 'Carne de res, bota',
    'carne de res cadera': 'Carne de res, cadera',
    'carne de res centro de pierna': 'Carne de res, centro de pierna',
    'carne de res chatas': 'Carne de res, chatas',
    'carne de res cogote': 'Carne de res, cogote',
    'carne de res costilla': 'Carne de res, costilla',
    'carne de res de cadera': 'Carne de res, cadera',
    'carne de res en canal': 'Carne de res en canal',
    'carne de res falda': 'Carne de res, falda',
    'carne de res lomo de brazo': 'Carne de res, lomo de brazo',
    'carne de res lomo fino': 'Carne de res, lomo fino',
    'carne de res molida murillo': 'Carne de res molida, murillo',
    'carne de res molida murillo': 'Carne de res molida, murillo',
    'carne de res morrillo': 'Carne de res, morrillo',
    'carne de res muchacho': 'Carne de res, muchacho',
    'carne de res murillo': 'Carne de res, murillo',
    'carne de res paletero': 'Carne de res, paletero',
    'carne de res pecho': 'Carne de res, pecho',
    'carne de res punta de anca': 'Carne de res, punta de anca',
    'carne de res sobrebarriga': 'Carne de res, sobrebarriga',
    # Egg grades
    'huevo blanco a': 'Huevo blanco A',
    'huevo blanco aa': 'Huevo blanco AA',
    'huevo blanco b': 'Huevo blanco B',
    'huevo blanco extra': 'Huevo blanco extra',
    'huevo rojo a': 'Huevo rojo A',
    'huevo rojo aa': 'Huevo rojo AA',
    'huevo rojo b': 'Huevo rojo B',
    'huevo rojo extra': 'Huevo rojo extra',
    'huevo a': 'Huevo A',
    'huevo aa': 'Huevo AA',
    'huevo b': 'Huevo B',
    'huevo extra': 'Huevo extra',
    # Specific product fixes
    'ahuyama (sakata)': 'Ahuyama (Sakata)',
    'ahuyamin (sakata)': 'Ahuyamín (Sakata)',
    'ahuyamin ( sakata)': 'Ahuyamín (Sakata)',
    'fecula de maiz': 'Fécula de maíz',
    'basa entero congelado importado': 'Basa, entero congelado importado',
    'basa filete congelado importado': 'Basa, filete congelado importado',
    'cebolla cab blanca': 'Cebolla cabezona blanca',
    'cebolla cab roja': 'Cebolla cabezona roja',
    'cebolla cebezona roja': 'Cebolla cabezona roja',
    'cebolla cabezona b bogotana': 'Cebolla cabezona blanca bogotana',
    'cebolla cabezona bogotana': 'Cebolla cabezona blanca bogotana',
    'beranjena': 'Berenjena',
    'berenjena': 'Berenjena',
    'tanjelo': 'Tangelo',
    'tangelo': 'Tangelo',
    'cebolla cab blanca': 'Cebolla cabezona blanca',
    'cebolla cab roja': 'Cebolla cabezona roja',
    'papa nwgra': 'Papa negra',
    'papa negr': 'Papa negra',
    'papa r - 12 negra': 'Papa R-12 negra',
    'papa r12 negra': 'Papa R-12 negra',
    'papa r-12': 'Papa R-12',
    'papa ruby': 'Papa rubí',
    'papa rubi': 'Papa rubí',
    'frijol saragoza': 'Fríjol Zaragoza',
    'frijol zaragoza': 'Fríjol Zaragoza',
    'frijol nina calima': 'Fríjol nima calima',
    'frijol verde cargamento': 'Fríjol verde cargamanto',
    'frijol verde en vaina': 'Fríjol verde en vaina',
    'limon tahiti': 'Limón Tahití',
    'limon tahiti': 'Limón Tahití',
    'limon thaiti': 'Limón Tahití',
    'limon thaiti': 'Limón Tahití',
    'limon comun': 'Limón común',
    'limon comun cienaga': 'Limón común ciénaga',
    'limon comun de cienaga': 'Limón común ciénaga',
    'limon mandarino': 'Limón mandarino',
    'maracuya antioqueña': 'Maracuyá antioqueño',
    'maracuya antioquena': 'Maracuyá antioqueño',
    'melon': 'Melón',
    'melon cantalup': 'Melón cantalup',
    'chocolo mazorca': 'Chócolo mazorca',
    'platano harton verde': 'Plátano hartón verde',
    'platano harton maduro': 'Plátano hartón maduro',
    'platano domincio harton maduro': 'Plátano dominico hartón maduro',
    'platano domincio harton verde': 'Plátano dominico hartón verde',
    'platano dominico harton maduro': 'Plátano dominico hartón maduro',
    'platano dominico harton verde': 'Plátano dominico hartón verde',
    'platano dominico hartonmaduro': 'Plátano dominico hartón maduro',
    'platano harton eje cafetero': 'Plátano hartón eje cafetero',
    'platano harton llanero': 'Plátano hartón llanero',
    'mora de castilla': 'Mora de Castilla',
    'mango tommy': 'Mango Tommy',
    'guanabana': 'Guanábana',
    'maracuya': 'Maracuyá',
    'mandarina onecco': 'Mandarina Oneco',
    'mandarina oneco': 'Mandarina Oneco',
    'mandarino oneco': 'Mandarina Oneco',
    'naranja valencia yo sweet': 'Naranja Valencia y/o Sweet',
    'uva red globe': 'Uva red globe',
    'uva red glob': 'Uva red globe',
    'uva red globel  combinada': 'Uva red globe',
    'uva red globel nacional': 'Uva red globe nacional',
    'uva globe nacional': 'Uva red globe nacional',
    'uva isabel': 'Uva isabela',
    'uva importada roja': 'Uva roja importada',
    'uva verde nacional': 'Uva verde',
    'pasta alimenticias': 'Pastas alimenticias',
    'pierna de pollo': 'Piernas de pollo',
    'pollo entero congelado sin visceras': 'Pollo entero congelado sin vísceras',
    'pollo entero fresco sin viscera': 'Pollo entero fresco sin vísceras',
    'pollo entero fresco sin visceras': 'Pollo entero fresco sin vísceras',
    'bagre rayado en posta congelado': 'Bagre rayado en postas congelado',
    'mojarra lora entera seco': 'Mojarra lora entera fresca',
    'jugo instantaneo': 'Jugo instantáneo (sobre)',
    'jugo instantaneo (sobre)': 'Jugo instantáneo (sobre)',
    'cafe instantaneo': 'Café instantáneo',
    'harina precocida de maiz': 'Harina precocida de maíz',
    'maiz amarillo trillado': 'Maíz amarillo trillado',
    'maiz blanco trillado': 'Maíz blanco trillado',
    'm aiz blanco trillado': 'Maíz blanco trillado',
    'panela morena redonda': 'Panela redonda morena',
    'uchuva con cascara': 'Uchuva con cáscara',
    'name criollo': 'Ñame criollo',
    'name diamante': 'Ñame diamante',
    'name espino': 'Ñame espino',
    # Category-level entries that leaked into products
    'granos y cereales': None,  # Delete -- not a product
    'huevos y lacteos': None,   # Delete -- not a product
    'procesados': None,         # Delete -- not a product
    'pescados': None,           # Delete -- not a product
    'otras frutas': None,       # Delete -- not a product (it's a subcategory)
}

# For cities: normalize to proper form
CITY_NAME_OVERRIDES = {
    'bogota': 'Bogotá, D.C.',
    'bogota dc': 'Bogotá, D.C.',
    'ipiales (narino)': 'Ipiales',
    'penol (antioquia)': 'Peñol',
    'rionegro (antioquia)': 'Rionegro',
    'tulua (valle del cauca)': 'Tuluá',
    'san vicente del chucuri': 'San Vicente de Chucurí',
    'san jose de cucuta': 'San José de Cúcuta',
    'don matias': 'Donmatías',
    'nunchia': 'Nunchía',
    'cuaspud': 'Cuaspud Carlosama',
    'cuaspud carlosama': 'Cuaspud Carlosama',
}

# Subcategory overrides
SUBCATEGORY_NAME_OVERRIDES = {
    'lacteos': 'Lácteos',
    'otros tuberculos': 'Otros tubérculos',
}


# ============================================================
# MERGE ENGINE
# ============================================================

def find_groups(entities):
    """
    Group entities by normalized key.
    Returns: {norm_key: [(id, canonical_name), ...]}
    Only groups with >1 member (actual duplicates).
    """
    groups = defaultdict(list)
    for ent in entities:
        key = normalize_key(ent['canonical_name'])
        if key:
            groups[key].append((ent['id'], ent['canonical_name']))

    # Return only groups with duplicates
    return {k: v for k, v in groups.items() if len(v) > 1}


def find_groups_with_overrides(entities, overrides):
    """
    Like find_groups but also merges entries that map to the same override target.
    """
    groups = defaultdict(list)
    override_targets = {}  # override canonical -> norm_key to merge into

    for ent in entities:
        key = normalize_key(ent['canonical_name'])
        if not key:
            continue

        # Check if this key has an override
        if key in overrides:
            target = overrides[key]
            if target is None:
                # Mark for deletion (no merge, just delete)
                groups[f'__delete__{key}'].append((ent['id'], ent['canonical_name']))
                continue
            # Use the override target's norm key as the group key
            target_key = normalize_key(target)
            groups[target_key].append((ent['id'], ent['canonical_name']))
        else:
            groups[key].append((ent['id'], ent['canonical_name']))

    return {k: v for k, v in groups.items() if len(v) > 1 or k.startswith('__delete__')}


def determine_surviving(group_members, overrides, norm_key):
    """
    For a group of duplicates, determine which entity survives and what name it gets.
    Returns: (surviving_id, proper_name, ids_to_delete)
    """
    if norm_key in overrides and overrides[norm_key] is not None:
        proper_name = overrides[norm_key]
    else:
        names = [m[1] for m in group_members]
        proper_name = pick_canonical(names)

    # The surviving entity is the one whose current name is closest to proper_name,
    # or the first one if none match
    surviving_id = group_members[0][0]
    for mid, mname in group_members:
        if mname == proper_name:
            surviving_id = mid
            break

    ids_to_delete = [mid for mid, _ in group_members if mid != surviving_id]
    return surviving_id, proper_name, ids_to_delete


# ============================================================
# TABLE-SPECIFIC MERGE FUNCTIONS
# ============================================================

def merge_table(conn, cursor, dim_table, alias_table, alias_fk_col,
                fact_tables_and_cols, child_tables_and_cols,
                entities, overrides, dry_run=False):
    """
    Generic merge function using batched updates for reliability.

    Commits after each batch of fact table updates to avoid statement timeouts.
    """
    print(f"\n{'='*60}")
    print(f"  Merging {dim_table} ({len(entities)} entities)")
    print(f"{'='*60}")

    groups = find_groups_with_overrides(entities, overrides)
    if not groups:
        print(f"  No duplicates found.")
        return 0

    # Phase 1: Collect all merge decisions
    merge_map = []       # (old_id, new_id) pairs for bulk UPDATE
    renames = []         # (entity_id, new_name) for canonical name fixes
    delete_ids = []      # IDs to delete (orphans)
    all_dup_ids = set()  # All IDs being merged away

    total_merged = 0
    total_deleted = 0

    for norm_key, members in sorted(groups.items()):
        if norm_key.startswith('__delete__'):
            for mid, mname in members:
                print(f"  DELETE orphan: {mname}")
                delete_ids.append(mid)
                total_deleted += 1
            continue

        surviving_id, proper_name, ids_to_delete = determine_surviving(
            members, overrides, norm_key)

        if not ids_to_delete:
            current_name = [m[1] for m in members if m[0] == surviving_id][0]
            if current_name != proper_name:
                print(f"  RENAME: {current_name} -> {proper_name}")
                renames.append((surviving_id, proper_name))
            continue

        dup_names = [m[1] for m in members if m[0] != surviving_id]
        print(f"  MERGE {len(members)} -> {proper_name}")
        for dn in dup_names:
            print(f"    - {dn}")

        for dup_id in ids_to_delete:
            merge_map.append((dup_id, surviving_id))
            all_dup_ids.add(dup_id)

        renames.append((surviving_id, proper_name))
        total_merged += len(ids_to_delete)

    if dry_run:
        print(f"  Result: {total_merged} would merge, {total_deleted} would delete")
        return total_merged + total_deleted

    # Phase 2: Execute individual UPDATEs with batched commits

    # 2b. Rewire alias table
    if merge_map:
        print(f"  Rewiring {alias_table} ({len(merge_map)} mappings)...")
        for old_id, new_id in merge_map:
            # Delete conflicting aliases first
            cursor.execute(
                f"""DELETE FROM {alias_table}
                    WHERE {alias_fk_col} = %s
                    AND raw_value IN (
                        SELECT raw_value FROM {alias_table} WHERE {alias_fk_col} = %s
                    )""",
                (old_id, new_id))
            cursor.execute(
                f"UPDATE {alias_table} SET {alias_fk_col} = %s WHERE {alias_fk_col} = %s",
                (new_id, old_id))
        conn.commit()
        print(f"    Done")

    # 2c. Rewire fact tables -- commit per mapping + reconnect every 50 to avoid connection kills
    for ft, fc in fact_tables_and_cols:
        if merge_map:
            print(f"  Rewiring {ft}.{fc} ({len(merge_map)} mappings)...", flush=True)
            total_updated = 0
            for i, (old_id, new_id) in enumerate(merge_map):
                cursor.execute(
                    f"UPDATE {ft} SET {fc} = %s WHERE {fc} = %s",
                    (new_id, old_id))
                total_updated += cursor.rowcount
                conn.commit()
                if (i + 1) % 20 == 0:
                    print(f"    ...{i+1}/{len(merge_map)} ({total_updated} rows)", flush=True)
                # Reconnect every 10 mappings to avoid Supabase killing the connection
                if (i + 1) % 10 == 0:
                    try:
                        cursor.close()
                        conn.close()
                    except Exception:
                        pass
                    conn = get_db_connection(new_connection=True)
                    cursor = conn.cursor()
                    cursor.execute("SET statement_timeout = '300s'")
            print(f"    {total_updated} rows updated", flush=True)

    # 2d. Rewire child dimension tables
    for ct, cc in child_tables_and_cols:
        if merge_map:
            print(f"  Rewiring {ct}.{cc}...")
            for old_id, new_id in merge_map:
                cursor.execute(
                    f"UPDATE {ct} SET {cc} = %s WHERE {cc} = %s",
                    (new_id, old_id))
            conn.commit()

    # 2e. Rename surviving entities
    print(f"  Renaming {len(renames)} entities...")
    for eid, new_name in renames:
        cursor.execute(
            f"UPDATE {dim_table} SET canonical_name = %s WHERE id = %s",
            (new_name, eid))
    conn.commit()

    # 2f. Delete duplicates and orphans
    all_delete = list(all_dup_ids) + delete_ids
    if all_delete:
        print(f"  Deleting {len(all_delete)} duplicate/orphan entities...")
        batch_size = 50
        for i in range(0, len(all_delete), batch_size):
            batch = all_delete[i:i + batch_size]
            placeholders = ','.join(['%s'] * len(batch))
            cursor.execute(
                f"DELETE FROM {alias_table} WHERE {alias_fk_col} IN ({placeholders})",
                batch)
            cursor.execute(
                f"DELETE FROM {dim_table} WHERE id IN ({placeholders})",
                batch)
            conn.commit()

    # Cleanup
    cursor.execute("DROP TABLE IF EXISTS _merge_map")
    conn.commit()

    print(f"  Result: {total_merged} merged, {total_deleted} deleted")
    return total_merged + total_deleted


# ============================================================
# MAIN
# ============================================================

def fresh_connection():
    """Get a fresh DB connection with appropriate timeout."""
    conn = get_db_connection(new_connection=True)
    cursor = conn.cursor()
    cursor.execute("SET statement_timeout = '300s'")
    return conn, cursor


def run(dry_run=False):

    print("=" * 60)
    print("Migration 019: Consolidate Duplicate Entities")
    print("=" * 60, flush=True)
    if dry_run:
        print("MODE: DRY RUN (no changes will be committed)")

    # --- Fetch all entities (use one connection for reads) ---
    conn, cursor = fresh_connection()
    tables_data = {}
    for table in ['dim_category', 'dim_subcategory', 'dim_product',
                   'dim_department', 'dim_city', 'dim_market',
                   'dim_presentation', 'dim_units']:
        cursor.execute(f"SELECT id, canonical_name FROM {table} ORDER BY canonical_name")
        tables_data[table] = [dict(r) for r in cursor.fetchall()]
        print(f"  {table}: {len(tables_data[table])} entities")
    cursor.close()
    conn.close()

    # --- Process each table with a FRESH connection to avoid Supabase killing long connections ---

    all_merges = [
        ('dim_units', 'alias_units', 'units_id',
         [('price_observations', 'units_id')], [], {}),
        ('dim_presentation', 'alias_presentation', 'presentation_id',
         [('price_observations', 'presentation_id')], [], {}),
        ('dim_subcategory', 'alias_subcategory', 'subcategory_id',
         [('price_observations', 'subcategory_id')], [('dim_product', 'subcategory_id')],
         SUBCATEGORY_NAME_OVERRIDES),
        ('dim_product', 'alias_product', 'product_id',
         [('price_observations', 'product_id'), ('supply_observations', 'product_id')], [],
         PRODUCT_NAME_OVERRIDES),
        # dim_department: clean, skip
        ('dim_city', 'alias_city', 'city_id',
         [('price_observations', 'city_id'), ('supply_observations', 'city_id')],
         [('dim_market', 'city_id')], CITY_NAME_OVERRIDES),
        ('dim_market', 'alias_market', 'market_id',
         [('price_observations', 'market_id'), ('supply_observations', 'market_id')], [], {}),
    ]

    # Support --resume TABLE to skip already-completed tables
    resume_from = None
    for i, arg in enumerate(sys.argv):
        if arg == '--resume' and i + 1 < len(sys.argv):
            resume_from = sys.argv[i + 1]

    merges = all_merges
    if resume_from:
        idx = next((i for i, m in enumerate(all_merges) if m[0] == resume_from), 0)
        merges = all_merges[idx:]
        print(f"  Resuming from {resume_from} (skipping {idx} tables)", flush=True)

    for dim_table, alias_table, fk_col, fact_refs, child_refs, overrides in merges:
        conn, cursor = fresh_connection()
        try:
            merge_table(conn, cursor, dim_table, alias_table, fk_col,
                        fact_refs, child_refs,
                        tables_data[dim_table], overrides, dry_run)
        except Exception as e:
            print(f"  ERROR merging {dim_table}: {e}", flush=True)
            import traceback
            traceback.print_exc()
            try:
                conn.rollback()
            except Exception:
                pass
        finally:
            try:
                cursor.close()
                conn.close()
            except Exception:
                pass

    print("\nAll table merges complete.", flush=True)

    # --- Final counts ---
    print("\n--- Final Entity Counts ---")
    for table in ['dim_category', 'dim_subcategory', 'dim_product',
                   'dim_department', 'dim_city', 'dim_market',
                   'dim_presentation', 'dim_units']:
        cursor.execute(f"SELECT COUNT(*) FROM {table}")
        count = cursor.fetchone()['count']
        print(f"  {table}: {count}")

    cursor.close()
    conn.close()


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='Consolidate duplicate dimension entities')
    parser.add_argument('--dry-run', action='store_true',
                        help='Preview changes without committing')
    parser.add_argument('--resume', type=str, default=None,
                        help='Resume from a specific table (e.g. dim_product)')
    args = parser.parse_args()
    run(dry_run=args.dry_run)
