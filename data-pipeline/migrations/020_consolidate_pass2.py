#!/usr/bin/env python3
"""
Migration 020: Second-pass entity consolidation.

Handles cases the first pass missed:
- Doubled-character garbage from PDF parsing
- Concatenated words (missing spaces)
- Missing connector words ("Carne cerdo" vs "Carne de cerdo")
- Brand-specific variants
- Typos and truncations
"""

import os
import sys
import psycopg2
from psycopg2.extras import RealDictCursor
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / '.env')

if sys.platform == 'win32':
    os.environ.setdefault('PYTHONIOENCODING', 'utf-8')
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')

DB_URL = os.getenv('SUPABASE_DB_URL')

# ============================================================
# EXPLICIT MERGE MAPPINGS
# Format: canonical_name_to_merge_INTO -> [names_to_merge_FROM]
# ============================================================

PRODUCT_MERGES = {
    # --- Doubled-character garbage ---
    'Ahuyamín (Sakata)': ['AAhhuuyyaammíínn ((ssaakkaattaa))'],
    'Ajo importado': ['AAjjoo iimmppoorrttaaddoo'],
    'Arveja verde en vaina': ['AArrvveejjaa vveerrddee eenn vvaaiinnaa'],
    'Carne de res, bola de brazo': ['CCaarrnnee ddee rreess,, bboollaa ddee bbrraazzoo', 'Carne res bola de brazo'],
    'Carne de res, morrillo': ['CCaarrnnee ddee rreess,, mmoorrrriilllloo', 'Carne res morrillo'],
    'Cebolla Cabezona Blanca': ['CCeebboollllaa ccaabbeezzoonnaa bbllaannccaa', 'Cebolla cabezona b bogotana'],
    'Color (bolsita)': ['CCoolloorr ((bboollssiittaa))'],
    'Durazno nacional': ['DDuurraazznnoo nnaacciioonnaall'],
    'Lechuga Batavia': ['LLeecchhuuggaa BBaattaavviiaa'],
    'Limón común': ['LLiimmóónn ccoommúúnn'],
    'Papa superior': ['PPaappaa ssuuppeerriioorr'],
    'Papa única': ['PPaappaa úúnniiccaa', 'Papaúnica'],
    'Pepino cohombro': ['PPeeppiinnoo ccoohhoommbbrroo', 'Pepinocohombro'],
    'Toyo blanco, filete congelado': ['TTooyyoo bbllaannccoo,, ffiilleettee ccoonnggeellaaddoo'],
    'Uva verde': ['UUvvaa vveerrddee'],

    # --- Concatenated words ---
    'Aguacate común': ['Aguacatecomún'],
    'Aguacate Papelillo': ['Aguacatepapelillo', 'Aguacate papellilo'],
    'Azúcar morena': ['Azúcarmorena', 'Azúcar morena Incauca'],
    'Azúcar Sulfitada': ['Azúcarsulfitada'],
    'Bagre rayado entero congelado': ['Bagrerayadoentero congelado', 'Bagre rayado en pósta congelado'],
    'Banano Criollo': ['Bananocriollo'],
    'Basa, entero congelado importado': ['Basa,enterocongelado importado'],
    'Café molido': ['Cafémolido', 'Café molido la bastilla'],
    'Calamar anillos': ['Calamaranillos'],
    'Camarón tigre precocido Seco': ['Camaróntigre precocido seco'],
    'Camarón tití precocido seco': ['Camaróntitíprecocido seco'],
    'Cebolla junca Aquitania': ['Cebollajuncaaquitania', 'Cebolla junca aquitana'],
    'Fríjol cargamanto rojo': ['Fríjolcargamantorojo'],
    'Fríjol verde cargamanto': ['Fríjolverdecargamanto'],
    'Huevo rojo AA': ['Huevorojoaa'],
    'Melón cantalup': ['Melóncantalup'],
    'Papa criolla sucia': ['Papacriollasucia'],
    'Papa Parda Pastusa': ['Papapardapastusa'],
    'Pepino de rellenar': ['Pepinoderellenar'],
    'Plátano dominico hartón verde': ['Plátanodominico hartón verde'],
    'Plátano hartón verde': ['Plátanohartónverde'],
    'Rábano rojo': ['Rábanorojo'],
    'Tomate chonto regional': ['Tomatechontoregional'],
    'Uva red globe nacional': ['Uvaredglobenacional', 'Uva globe nacional'],
    'Yuca ICA': ['Yucaica'],
    'Yuca llanera': ['Yucallanera'],

    # --- "Carne cerdo" without "de" ---
    'Carne de cerdo, brazo sin hueso': ['Carne cerdo brazo sin hueso'],
    'Carne de cerdo, costilla': ['Carne cerdo costilla'],
    'Carne de cerdo en canal': ['Carne cerdo en canal'],
    'Carne de cerdo, espinazo': ['Carne cerdo espinazo'],
    'Carne de cerdo, lomo sin hueso': ['Carne cerdo lomo sin hueso'],
    'Carne de cerdo, pernil sin hueso': ['Carne cerdo pernil sin hueso'],
    'Carne de cerdo, tocino barriga': ['Carne cerdo tocino barriga'],
    'Carne de cerdo, tocino papada': ['Carne cerdo tocino papada'],

    # --- "Carne res" without "de" ---
    'Carne de res, bola de pierna': ['Carne res bola de pierna'],
    'Carne de res, centro de pierna': ['Carne res centro de pierna'],
    'Carne de res, costilla': ['Carne res costilla'],
    'Carne de res, falda': ['Carne res falda'],
    'Carne de res, lomo fino': ['Carne res lomo fino'],
    'Carne de res, muchacho': ['Carne res muchacho'],
    'Carne de res, paletero': ['Carne res paletero'],
    'Carne de res, pecho': ['Carne res pecho'],
    'Carne de res, punta de anca': ['Carne res punta de anca'],
    'Carne de res, sobrebarriga': ['Carne res sobrebarriga'],

    # --- Brand-specific variants -> generic ---
    'Avena en hojuelas': ['Avena en hojuelas Quaker'],
    'Avena Molida': ['Avena en molida Quaker'],
    'Chocolate dulce': ['Chocolate dulce corona'],
    'Galletas saladas': ['Galletas saladas 3 tacos', 'Galletas saladas taco día'],
    'Harina de trigo': ['Harina de trigo la nieve'],
    'Harina precocida de maíz': ['Harina precocida de maíz super arepa'],
    'Jugo instantáneo (sobre)': ['Jugo instantáneo (sobre) frutiño'],
    'Lomitos de atún en lata': ['Lomitos de atún en lata soberana'],
    'Margarina': ['Margarina Dagusto'],
    'Mayonesa Doy Pack': ['Mayonesa doy pack fruco'],
    'Panela cuadrada morena': ['Panela cuadrada morena Villetana'],
    'Pastas alimenticias': ['Pastas alimenticias doria', 'Pasta alimenticias'],
    'Sal Yodada': ['Sal yodada refisal'],
    'Salsa de Tomate Doy Pack': ['Salsa de tomate doy pack fruco'],
    'Sardinas en lata': ['Sardinas en lata soberana'],

    # --- Other typos/truncations/merges ---
    'Ahuyama (Sakata)': ['Ahuyama (sakata)'],  # Will merge with doubled too
    'Papaya Maradol': ['Papaya marad'],
    'Plátano dominico hartón maduro': ['Plátano dom.hart.mad.'],
    'Plátano dominico hartón verde': ['Plátano dom.hart.verd.'],
    'Uva red globe': ['Uva red globel / Combinada'],
    'Maracuyá antioqueño': ['Maracuyá antioqueña'],
    'Piernas de pollo': ['Pierna de pollo'],
    'Panela redonda morena': ['Panela morena redonda'],
    'Aceite girasol': ['Aceite de Girasol', 'Aceite Girasol'],
    'Plátano hartón verde Eje Cafetero': ['Plátano hartón Eje Cafetero'],
    'Zanahoria': ['Zanahorias'],
}


def fresh():
    conn = psycopg2.connect(DB_URL, cursor_factory=RealDictCursor)
    conn.autocommit = True
    c = conn.cursor()
    c.execute('SET statement_timeout = %s', ('120s',))
    return conn, c


def merge_product(conn, c, surviving_name, dup_names):
    """Merge duplicate products into the surviving one."""
    # Find surviving entity
    c.execute('SELECT id FROM dim_product WHERE canonical_name = %s', (surviving_name,))
    row = c.fetchone()
    if not row:
        c.execute('SELECT id, canonical_name FROM dim_product WHERE canonical_name ILIKE %s', (surviving_name,))
        row = c.fetchone()
        if not row:
            print(f'  SKIP {surviving_name}: not found', flush=True)
            return 0, conn, c
        surviving_name = row['canonical_name']
    surviving_id = row['id']

    total_merged = 0
    for dup_name in dup_names:
        c.execute('SELECT id FROM dim_product WHERE canonical_name = %s', (dup_name,))
        dup_row = c.fetchone()
        if not dup_row:
            continue  # Already merged or doesn't exist

        dup_id = dup_row['id']

        # Rewire aliases (handle conflicts)
        c.execute('''DELETE FROM alias_product WHERE product_id = %s
                     AND raw_value IN (SELECT raw_value FROM alias_product WHERE product_id = %s)''',
                  (dup_id, surviving_id))
        c.execute('UPDATE alias_product SET product_id = %s WHERE product_id = %s',
                  (surviving_id, dup_id))

        # Rewire fact tables in batches
        for table in ['price_observations', 'supply_observations']:
            while True:
                try:
                    c.execute(f'''WITH b AS (SELECT id FROM {table} WHERE product_id = %s LIMIT 2000)
                                 UPDATE {table} SET product_id = %s WHERE id IN (SELECT id FROM b)''',
                              (dup_id, surviving_id))
                    if c.rowcount == 0:
                        break
                except Exception as e:
                    print(f'    err rewiring {table}: {e}', flush=True)
                    try: conn.close()
                    except: pass
                    conn, c = fresh()
                    break

        # Delete duplicate
        try:
            c.execute('DELETE FROM alias_product WHERE product_id = %s', (dup_id,))
            c.execute('DELETE FROM dim_product WHERE id = %s', (dup_id,))
            total_merged += 1
        except Exception as e:
            print(f'    err deleting {dup_name}: {e}', flush=True)
            try: conn.close()
            except: pass
            conn, c = fresh()

    return total_merged, conn, c


def run(dry_run=False):
    print("=" * 60)
    print("Migration 020: Second-pass entity consolidation")
    print("=" * 60, flush=True)

    conn, c = fresh()

    c.execute('SELECT COUNT(*) FROM dim_product')
    before = c.fetchone()['count']
    print(f'Products before: {before}', flush=True)

    total = 0
    for surviving_name, dup_names in PRODUCT_MERGES.items():
        if dry_run:
            for dn in dup_names:
                c.execute('SELECT id FROM dim_product WHERE canonical_name = %s', (dn,))
                if c.fetchone():
                    print(f'  MERGE {dn} -> {surviving_name}', flush=True)
                    total += 1
        else:
            merged, conn, c = merge_product(conn, c, surviving_name, dup_names)
            if merged > 0:
                print(f'  {surviving_name}: merged {merged} duplicates', flush=True)
            total += merged

    c.execute('SELECT COUNT(*) FROM dim_product')
    after = c.fetchone()['count']
    print(f'\nProducts after: {after} (removed {before - after})', flush=True)
    conn.close()
    print('DONE', flush=True)


if __name__ == '__main__':
    dry_run = '--dry-run' in sys.argv
    run(dry_run=dry_run)
