"""
Fill image gaps for individual products and insumos.

For products: uploads an image for every individual product slug that's missing.
For insumos: uploads an image for every individual insumo slug using subgrupo-level
             images or targeted searches.

Usage:
    python -u -m scripts.fill_image_gaps [--products-only] [--insumos-only] [--dry-run]
"""

import os
import re
import sys
import json
import time
import argparse
import unicodedata
import urllib.request
import urllib.parse
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.supabase_client import get_supabase_client, get_db_connection


def safe_print(*args, **kwargs):
    try:
        print(*args, **kwargs, flush=True)
    except UnicodeEncodeError:
        text = ' '.join(str(a) for a in args)
        print(text.encode('ascii', errors='replace').decode('ascii'), **kwargs, flush=True)


IMAGE_BUCKET = "product-images"
WIKIMEDIA_API = "https://commons.wikimedia.org/w/api.php"
USER_AGENT = "AgroAmigo/1.0 (https://github.com/agroamigo; contact@agroamigo.co)"
TARGET_WIDTH = 400


def slugify(text: str) -> str:
    text = unicodedata.normalize('NFD', text)
    text = ''.join(c for c in text if unicodedata.category(c) != 'Mn')
    text = text.lower().strip()
    text = re.sub(r'[^\w\s-]', '', text)
    text = re.sub(r'[\s_]+', '_', text)
    text = re.sub(r'-+', '-', text)
    return text.strip('_-')


# -----------------------------------------------------------------------
# Wikimedia search
# -----------------------------------------------------------------------

def search_wikimedia(query: str, limit: int = 3) -> list[dict]:
    params = {
        'action': 'query',
        'generator': 'search',
        'gsrsearch': f'filetype:bitmap {query}',
        'gsrnamespace': '6',
        'gsrlimit': str(limit),
        'prop': 'imageinfo',
        'iiprop': 'url|size|mime',
        'iiurlwidth': str(TARGET_WIDTH),
        'format': 'json',
    }
    url = f"{WIKIMEDIA_API}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers={'User-Agent': USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read())
    except Exception as e:
        return []
    results = []
    for page in data.get('query', {}).get('pages', {}).values():
        info = page.get('imageinfo', [{}])[0]
        if not info.get('mime', '').startswith('image/'):
            continue
        results.append({
            'title': page.get('title', ''),
            'thumb': info.get('thumburl', info.get('url', '')),
            'url': info.get('url', ''),
        })
    return results


def download_image(url: str) -> Optional[bytes]:
    req = urllib.request.Request(url, headers={'User-Agent': USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.read()
    except Exception:
        return None


def fetch_wikimedia_image(query: str) -> Optional[bytes]:
    time.sleep(0.15)
    for r in search_wikimedia(query):
        img = download_image(r['thumb'])
        if img:
            return img
    return None


# -----------------------------------------------------------------------
# Supabase helpers
# -----------------------------------------------------------------------

def get_uploaded_set(client, prefix: str) -> set[str]:
    """Get set of uploaded slugs under a prefix."""
    uploaded = set()
    files = client.storage.from_(IMAGE_BUCKET).list(prefix, {'limit': 5000})
    for f in files:
        name = f.get('name', '')
        if name.endswith('.jpg'):
            uploaded.add(name[:-4])
    return uploaded


def upload_image(client, image_data: bytes, storage_path: str) -> bool:
    try:
        client.storage.from_(IMAGE_BUCKET).upload(
            storage_path, image_data, {"content-type": "image/jpeg"}
        )
        return True
    except Exception as e:
        if any(x in str(e).lower() for x in ['duplicate', 'already exists', '409']):
            return True
        safe_print(f"    Upload error: {e}")
        return False


def download_existing(client, storage_path: str) -> Optional[bytes]:
    """Download an existing image from the bucket."""
    try:
        return client.storage.from_(IMAGE_BUCKET).download(storage_path)
    except Exception:
        return None


# -----------------------------------------------------------------------
# Product search term mapping — specific cuts, varieties, preparations
# -----------------------------------------------------------------------

SPECIFIC_PRODUCT_TERMS = {
    # Pork cuts
    'carne_de_cerdo_brazo_con_hueso': 'pork shoulder bone in',
    'carne_de_cerdo_brazo_sin_hueso': 'pork shoulder boneless',
    'carne_de_cerdo_cabeza_de_lomo': 'pork loin head',
    'carne_de_cerdo_costilla': 'pork ribs spare ribs',
    'carne_de_cerdo_espinazo': 'pork spine backbone',
    'carne_de_cerdo_lomo_con_hueso': 'pork loin bone in',
    'carne_de_cerdo_lomo_sin_hueso': 'pork tenderloin boneless',
    'carne_de_cerdo_pernil_con_hueso': 'pork leg ham bone in',
    'carne_de_cerdo_pernil_sin_hueso': 'pork leg ham boneless',
    'carne_de_cerdo_tocineta_plancha': 'bacon sliced pork',
    'carne_de_cerdo_tocino_barriga': 'pork belly',
    'carne_de_cerdo_tocino_papada': 'pork jowl',

    # Beef cuts
    'carne_de_res_bola_de_brazo': 'beef shoulder clod',
    'carne_de_res_bola_de_pierna': 'beef round roast',
    'carne_de_res_bota': 'beef shank',
    'carne_de_res_cadera': 'beef rump roast',
    'carne_de_res_centro_de_pierna': 'beef eye round',
    'carne_de_res_chatas': 'beef flank steak flat',
    'carne_de_res_cogote': 'beef neck',
    'carne_de_res_costilla': 'beef ribs short ribs',
    'carne_de_res_falda': 'beef flank steak',
    'carne_de_res_lomo_de_brazo': 'beef chuck roast',
    'carne_de_res_lomo_fino': 'beef tenderloin filet',
    'carne_de_res_morrillo': 'beef hump',
    'carne_de_res_muchacho': 'beef eye round steak',
    'carne_de_res_murillo': 'beef shin',
    'carne_de_res_paletero': 'beef blade steak',
    'carne_de_res_pecho': 'beef brisket',
    'carne_de_res_punta_de_anca': 'beef sirloin cap picanha',
    'carne_de_res_sobrebarriga': 'beef flank sobrebarriga colombian',
    'carne_de_res_molida': 'ground beef minced',
    'carne_de_res_en_canal': 'beef carcass wholesale',

    # Chicken
    'alas_de_pollo_con_costillar': 'chicken wings with back',
    'alas_de_pollo_sin_costillar': 'chicken wings',
    'muslos_de_pollo_con_rabadilla': 'chicken thigh with back',
    'muslos_de_pollo_sin_rabadilla': 'chicken thighs',
    'pierna_pernil_con_rabadilla': 'chicken leg quarter',
    'pierna_pernil_sin_rabadilla': 'chicken drumstick',
    'pollo_entero_congelado_sin_visceras': 'whole frozen chicken',
    'pollo_entero_fresco_sin_visceras': 'whole raw chicken',

    # Fish specific
    'bagre_rayado_entero_congelado': 'striped catfish whole',
    'bagre_rayado_entero_fresco': 'striped catfish fresh',
    'bagre_rayado_en_postas_congelado': 'catfish steak fillet',
    'basa_entero_congelado_importado': 'pangasius basa whole fish',
    'basa_filete_congelado_importado': 'basa fish fillet',
    'blanquillo_entero_fresco': 'tilefish whole',
    'bocachico_criollo_fresco': 'bocachico prochilodus fish',
    'bocachico_importado_congelado': 'bocachico frozen fish',
    'cachama_de_cultivo_fresca': 'cachama pacu fish fresh',
    'calamar_blanco_entero': 'whole squid calamari',
    'camaron_tigre_precocido_seco': 'tiger shrimp dried',
    'camaron_titi_precocido_seco': 'small dried shrimp',
    'capaz_magdalena_fresco': 'pimelodus river catfish colombian',
    'corvina_filete_congelado': 'corvina sea bass fillet',
    'langostino_u12': 'large prawn langoustine',
    'langostino_16-20': 'prawn shrimp medium',
    'merluza_filete': 'hake fillet merluza',
    'mojarra_lora_entera_congelada': 'mojarra tilapia frozen',
    'mojarra_lora_entera_fresca': 'mojarra tilapia fresh',
    'nicuro_fresco': 'nicuro catfish',
    'palmitos_de_mar': 'surimi seafood stick',
    'pargo_rojo_entero_congelado': 'red snapper frozen whole',
    'pargo_rojo_entero_fresco': 'red snapper fresh whole',
    'pargo_rojo_platero': 'red snapper small',
    'pescado_cabezas': 'fish head',
    'robalo_filete_congelado': 'snook fish fillet',
    'salmon_filete_congelado': 'salmon fillet frozen',
    'sierra_entera_congelada': 'king mackerel sierra fish',
    'tilapia_roja_entera_congelada': 'red tilapia frozen',
    'tilapia_roja_entera_fresca': 'red tilapia fresh',
    'tilapia_filete_congelado': 'tilapia fillet frozen',
    'tilapia_lomitos': 'tilapia loin fillet',
    'toyo_blanco_filete_congelado': 'shark fillet toyo',
    'trucha_en_corte_mariposa': 'butterfly trout fillet',
    'trucha_entera_fresca': 'fresh whole trout',
    'cazuela_de_mariscos_paquete': 'seafood chowder mix',

    # Eggs — all map to same image
    'huevo_blanco_a': 'white eggs',
    'huevo_blanco_aa': 'white eggs',
    'huevo_blanco_b': 'white eggs',
    'huevo_blanco_extra': 'white eggs large',
    'huevo_rojo_a': 'brown eggs',
    'huevo_rojo_aa': 'brown eggs',
    'huevo_rojo_b': 'brown eggs',
    'huevo_rojo_extra': 'brown eggs large',
    'huevorojoaa': 'brown eggs',

    # Rice varieties
    'arroz_blanco_importado': 'white rice imported',
    'arroz_de_primera': 'premium white rice',
    'arroz_de_segunda': 'white rice standard',
    'arroz_excelso': 'colombian rice excelso',
    'arroz_sopa_cristal': 'broken rice soup',

    # Corn varieties
    'maiz_amarillo_cascara': 'yellow corn dried',
    'maiz_amarillo_cascara_importado': 'yellow corn imported',
    'maiz_amarillo_trillado': 'yellow corn shelled',
    'maiz_blanco_cascara': 'white corn dried',
    'maiz_blanco_retrillado': 'white corn hulled',
    'maiz_blanco_trillado': 'white corn shelled',
    'maiz_pira': 'popcorn kernels',
    'cuchuco_de_cebada': 'pearl barley',
    'cuchuco_de_maiz': 'hominy corn',

    # Beans
    'frijol_bolon': 'bolon beans large',
    'frijol_cabeza_negra_importado': 'black eyed peas',
    'frijol_cabeza_negra': 'black eyed peas',
    'frijol_calima': 'calima red beans',
    'frijol_cargamanto_blanco': 'white kidney beans large',
    'frijol_cargamanto_rojo': 'red kidney beans',
    'frijol_nima_calima': 'nima calima beans',
    'frijol_palomito_importado': 'navy beans white',
    'frijol_radical': 'radical beans red',
    'frijol_uribe_rosado': 'pink beans cranberry',
    'frijol_zaragoza': 'zaragoza beans red',
    'frijolcargamantorojo': 'red kidney beans',
    'garbanzo_importado': 'chickpea garbanzo',
    'lenteja_importada': 'lentils dried',
    'arveja_amarilla_seca_importada': 'yellow split peas dried',
    'arveja_verde_seca_importada': 'green split peas dried',

    # Vegetables specific
    'arveja_verde_en_vaina_pastusa': 'green peas in pod',
    'frijol_verde_bolo': 'green beans bolo',
    'frijol_verde_cargamanto': 'green cargamanto beans fresh',
    'frijol_verde_en_vaina': 'green beans in pod',
    'frijolverdecargamanto': 'green beans fresh',
    'haba_verde': 'fava beans broad beans green',
    'cebolla_cabezona_blanca': 'white onion',
    'cebolla_cabezona_roja': 'red onion purple',
    'cebolla_junca': 'green onion scallion',
    'cebolla_puerro': 'leek vegetable',
    'cebollin_chino': 'chives herb',
    'cebollajuncaaquitania': 'green onion scallion',
    'ahuyamin_sakata': 'pumpkin squash kabocha',
    'aji_topito_dulce': 'sweet pepper aji dulce',
    'ajo_importado': 'garlic bulb imported',
    'calabacin': 'zucchini courgette',
    'calabaza': 'pumpkin squash',
    'chocolo_mazorca': 'corn on the cob',
    'cidra': 'chayote squash',
    'pepino_de_rellenar': 'stuffing cucumber large',
    'pepinocohombro': 'cucumber',
    'pepinoderellenar': 'stuffing cucumber',
    'pimenton_verde': 'green bell pepper',
    'rabano_rojo': 'red radish',
    'rabanorojo': 'red radish',
    'remolacha': 'beetroot beet',
    'remolacha_regional': 'beetroot beet',
    'repollo_blanco': 'white cabbage',
    'repollo_morado': 'red cabbage purple',
    'repollo_verde': 'green cabbage',
    'tomate_chonto': 'tomato chonto colombian',
    'tomate_chonto_regional': 'tomato chonto',
    'tomate_larga_vida': 'long life tomato',
    'tomate_rinon': 'beefsteak tomato',
    'tomate_rinon_valluno': 'beefsteak tomato',
    'tomate_riogrande': 'roma tomato',
    'tomate_riogrande_bumangues': 'roma tomato',
    'tomatechontoregional': 'tomato chonto',
    'zanahoria_larga_vida': 'carrot fresh',

    # Tubers
    'arracacha_amarilla': 'arracacha yellow root',
    'arracacha_blanca': 'arracacha white root',
    'name_criollo': 'yam tropical tuber',
    'name_diamante': 'yam diamond tuber',
    'name_espino': 'yam thorny tuber',
    'ulluco': 'ulluco tuber papalisa',
    'papa_betina': 'potato betina',
    'papa_capira': 'potato round',
    'papa_criolla_limpia': 'papa criolla yellow potato cleaned',
    'papa_criolla_sucia': 'papa criolla yellow potato',
    'papa_ica-huila': 'potato colombian',
    'papa_morasurco': 'potato purple dark',
    'papa_nevada': 'potato white nevada',
    'papa_parda': 'potato brown',
    'papa_purace': 'potato colombian',
    'papa_r-12_negra': 'dark potato',
    'papa_r-12_roja': 'red potato',
    'papa_rubi': 'red potato ruby',
    'papa_sabanera': 'potato colombian',
    'papa_san_felix': 'potato',
    'papa_superior': 'potato white',
    'papa_suprema': 'potato large',
    'papa_tocarrena': 'potato colombian',
    'papa_unica': 'potato round',
    'papacriollasucia': 'papa criolla yellow potato',
    'papapardapastusa': 'potato brown',
    'papaunica': 'potato round',
    'platano_comino': 'baby plantain small',
    'platano_dominico_harton_maduro': 'ripe plantain dominico',
    'platano_dominico_harton_verde': 'green plantain dominico',
    'platano_dominico_hartonmaduro': 'ripe plantain dominico',
    'platano_dominico_verde': 'green plantain dominico',
    'platano_harton_maduro': 'ripe plantain yellow',
    'platano_harton_verde_eje_cafetero': 'green plantain',
    'platanodominico_harton_verde': 'green plantain',
    'platanohartonverde': 'green plantain',
    'yuca_chirosa': 'cassava yuca root',
    'yuca_criolla': 'cassava yuca',
    'yuca_ica': 'cassava yuca',
    'yuca_llanera': 'cassava root',
    'yucaica': 'cassava yuca',
    'yucallanera': 'cassava root',

    # Dairy
    'leche_en_polvo': 'powdered milk',
    'queso_campesino': 'queso campesino colombian fresh cheese',
    'queso_caqueta': 'caqueta cheese colombian',
    'queso_costeno': 'queso costeno colombian coast cheese',
    'queso_cuajada': 'cuajada fresh curd cheese',
    'queso_doble_crema': 'double cream cheese colombian',

    # Processed
    'aceite_de_palma': 'palm oil bottle',
    'aceite_girasol': 'sunflower oil bottle',
    'aceite_soya': 'soybean oil bottle',
    'aceite_vegetal_mezcla': 'vegetable oil bottle',
    'manteca': 'lard cooking fat',
    'margarina': 'margarine tub',
    'azucar_morena': 'brown sugar raw',
    'azucar_refinada': 'white sugar refined',
    'azucar_sulfitada': 'raw sugar unrefined',
    'azucarmorena': 'brown sugar',
    'azucarsulfitada': 'raw sugar',
    'panela_cuadrada_blanca': 'panela white square block',
    'panela_cuadrada_morena': 'panela brown square block',
    'panela_en_pastilla': 'panela tablet small',
    'panela_pulverizada': 'panela powder',
    'panela_redonda_blanca': 'panela white round block',
    'panela_redonda_morena': 'panela brown round block',
    'cafe_molido': 'ground coffee bag',
    'cafe_instantaneo': 'instant coffee jar',
    'cafemolido': 'ground coffee',
    'chocolate_amargo': 'dark chocolate bar',
    'chocolate_dulce': 'chocolate bar milk',
    'chocolate_instantaneo': 'cocoa powder chocolate',
    'avena_en_hojuelas': 'rolled oats oatmeal',
    'avena_molida': 'ground oats flour',
    'harina_de_trigo': 'wheat flour bag',
    'harina_precocida_de_maiz': 'precooked corn flour arepa',
    'fecula_de_maiz': 'cornstarch box',
    'sal_yodada': 'iodized salt container',
    'galletas_saladas': 'saltine crackers',
    'galletas_dulces_redondas_con_crema': 'cream filled cookies',
    'pastas_alimenticias': 'pasta spaghetti box',
    'sardinas_en_lata': 'canned sardines tin',
    'lomitos_de_atun_en_lata': 'canned tuna',
    'arveja_enlatada': 'canned green peas',
    'frijol_enlatado': 'canned beans',
    'maiz_enlatado': 'canned corn',
    'bocadillo_veleno': 'bocadillo guava paste candy',
    'gelatina': 'gelatin dessert jello',
    'vinagre': 'vinegar bottle',
    'salsa_de_tomate_doy_pack': 'ketchup tomato sauce packet',
    'mayonesa_doy_pack': 'mayonnaise packet',
    'mostaza_doy_pack': 'mustard condiment',
    'jugo_de_frutas': 'fruit juice box',
    'jugo_instantaneo_sobre': 'instant juice powder sachet',
    'sopa_de_pollo_caja': 'chicken soup box packet',
    'color_bolsita': 'annatto color achiote powder',
}

# Insumo subgrupo search terms — improved for the 5 that failed
INSUMO_SUBGRUPO_SEARCH = {
    'bioinsumos': 'organic agriculture biofertilizer compost',
    'antisepticos_desinfectantes_e_higiene': 'farm disinfectant cleaning product',
    'hormonales': 'veterinary syringe hormone injection',
    'insecticidas_plaguicidas_y_repelentes': 'insect repellent spray bottle farm',
    'vitaminas_sales_y_minerales': 'animal salt lick mineral block cattle',
}


def get_all_products(conn) -> list[dict]:
    """Get every individual product with its category info."""
    cur = conn.cursor()
    cur.execute("""
        SELECT DISTINCT p.canonical_name, sc.canonical_name as sub, c.canonical_name as cat
        FROM dim_product p
        JOIN dim_subcategory sc ON p.subcategory_id = sc.id
        JOIN dim_category c ON sc.category_id = c.id
        WHERE sc.canonical_name NOT LIKE 'General%%'
        ORDER BY c.canonical_name, sc.canonical_name, p.canonical_name
    """)
    rows = cur.fetchall()
    result = []
    for r in rows:
        slug = slugify(r['canonical_name'])
        if slug and len(slug) >= 2:
            result.append({
                'slug': slug,
                'name': r['canonical_name'],
                'subcategory': r['sub'],
                'category': r['cat'],
            })
    return result


def get_all_insumos(conn) -> list[dict]:
    """Get every individual insumo with subgrupo info."""
    cur = conn.cursor()
    cur.execute("""
        SELECT DISTINCT i.canonical_name,
               sg.canonical_name as subgrupo,
               g.canonical_name as grupo
        FROM dim_insumo i
        LEFT JOIN dim_insumo_subgrupo sg ON i.subgrupo_id = sg.id
        LEFT JOIN dim_insumo_grupo g ON sg.grupo_id = g.id
        ORDER BY g.canonical_name, sg.canonical_name, i.canonical_name
    """)
    rows = cur.fetchall()
    result = []
    for r in rows:
        slug = slugify(r['canonical_name'])
        if slug and len(slug) >= 2:
            result.append({
                'slug': slug,
                'name': r['canonical_name'],
                'subgrupo': r['subgrupo'] or '',
                'grupo': r['grupo'] or '',
                'subgrupo_slug': slugify(r['subgrupo'] or ''),
            })
    return result


def determine_search_term(product: dict) -> str:
    """Build a search term for a product based on its slug and category."""
    slug = product['slug']

    # Check explicit mapping first
    if slug in SPECIFIC_PRODUCT_TERMS:
        return SPECIFIC_PRODUCT_TERMS[slug]

    # Try partial matching on slug prefixes
    for key, term in SPECIFIC_PRODUCT_TERMS.items():
        if slug.startswith(key) or key.startswith(slug):
            return term

    # Generic fallback by category
    cat = product['category']
    name = product['name'].lower()
    if cat == 'Carnes':
        if 'cerdo' in name:
            return 'pork meat raw'
        if 'res' in name:
            return 'beef meat raw'
        if 'pollo' in name:
            return 'chicken raw'
        return 'meat raw'
    if cat == 'Pescados':
        return 'fish fillet seafood'
    if cat == 'Frutas':
        return name + ' fruit'
    if cat == 'Verduras y hortalizas':
        return name + ' vegetable'

    return name


def process_missing_products(client, conn, dry_run=False):
    """Find and upload images for every individual product that's missing."""
    products = get_all_products(conn)
    uploaded = get_uploaded_set(client, 'products')

    missing = [p for p in products if p['slug'] not in uploaded]
    safe_print(f"\n{'='*60}")
    safe_print(f"Products: {len(products)} total, {len(uploaded)} uploaded, {len(missing)} missing")
    safe_print(f"{'='*60}\n")

    if not missing:
        safe_print("All products have images!")
        return {'found': 0, 'reused': 0, 'failed': 0}

    # Pre-cache: for products that are variants of an existing base image,
    # download the base image once and reuse it
    base_image_cache = {}
    stats = {'found': 0, 'reused': 0, 'failed': 0}

    for i, product in enumerate(missing):
        slug = product['slug']
        storage_path = f"products/{slug}.jpg"
        safe_print(f"[{i+1}/{len(missing)}] {product['name']} ({slug})")
        safe_print(f"  {product['category']} > {product['subcategory']}")

        if dry_run:
            term = determine_search_term(product)
            safe_print(f"  [DRY RUN] Would search: {term}")
            continue

        # Strategy 1: Check if we have a base product image we can reuse
        # e.g., carne_de_cerdo_costilla -> try carne_de_cerdo
        reused = False
        base_candidates = []
        parts = slug.split('_')
        for length in range(len(parts)-1, 1, -1):
            candidate = '_'.join(parts[:length])
            if candidate in uploaded or candidate in base_image_cache:
                base_candidates.append(candidate)
                break

        for candidate in base_candidates:
            if candidate in base_image_cache:
                img_data = base_image_cache[candidate]
            else:
                img_data = download_existing(client, f"products/{candidate}.jpg")
                if img_data:
                    base_image_cache[candidate] = img_data

            if img_data:
                if upload_image(client, img_data, storage_path):
                    safe_print(f"  Reused from {candidate}.jpg")
                    stats['reused'] += 1
                    reused = True
                break

        if reused:
            continue

        # Strategy 2: Search for a specific image
        search_term = determine_search_term(product)
        safe_print(f"  Searching: {search_term}")
        img_data = fetch_wikimedia_image(search_term)

        if img_data:
            if upload_image(client, img_data, storage_path):
                safe_print(f"  Uploaded ({len(img_data)} bytes)")
                stats['found'] += 1
                base_image_cache[slug] = img_data
            else:
                stats['failed'] += 1
        else:
            # Strategy 3: Fall back to a more generic search
            generic = product['category'].lower()
            safe_print(f"  Fallback search: {generic}")
            img_data = fetch_wikimedia_image(generic + ' food')
            if img_data:
                if upload_image(client, img_data, storage_path):
                    safe_print(f"  Uploaded fallback ({len(img_data)} bytes)")
                    stats['found'] += 1
                else:
                    stats['failed'] += 1
            else:
                safe_print(f"  FAILED - no image found")
                stats['failed'] += 1

    safe_print(f"\nProduct results: {stats['found']} new, {stats['reused']} reused, {stats['failed']} failed")
    return stats


def process_missing_insumos(client, conn, dry_run=False):
    """Upload images for every individual insumo."""
    insumos = get_all_insumos(conn)
    uploaded = get_uploaded_set(client, 'insumos')

    missing = [ins for ins in insumos if ins['slug'] not in uploaded]
    safe_print(f"\n{'='*60}")
    safe_print(f"Insumos: {len(insumos)} total, {len(uploaded)} uploaded, {len(missing)} missing")
    safe_print(f"{'='*60}\n")

    if not missing:
        safe_print("All insumos have images!")
        return {'found': 0, 'reused': 0, 'failed': 0}

    # First, fill in the 5 missing subgrupo-level images
    subgrupo_uploaded = get_uploaded_set(client, 'insumos')
    for sg_slug, search_term in INSUMO_SUBGRUPO_SEARCH.items():
        if sg_slug not in subgrupo_uploaded:
            safe_print(f"Filling subgrupo gap: {sg_slug}")
            if not dry_run:
                img = fetch_wikimedia_image(search_term)
                if img:
                    upload_image(client, img, f"insumos/{sg_slug}.jpg")
                    safe_print(f"  Uploaded subgrupo image")
                else:
                    safe_print(f"  Still no image for {sg_slug}")

    # Pre-download all subgrupo images to cache
    safe_print("\nCaching subgrupo images...")
    subgrupo_cache = {}
    subgrupo_uploaded = get_uploaded_set(client, 'insumos')
    for sg_slug in subgrupo_uploaded:
        img = download_existing(client, f"insumos/{sg_slug}.jpg")
        if img:
            subgrupo_cache[sg_slug] = img
    safe_print(f"Cached {len(subgrupo_cache)} subgrupo images")

    # Now upload individual insumo images by reusing their subgrupo image
    stats = {'found': 0, 'reused': 0, 'failed': 0}
    # Re-check what's uploaded after subgrupo fill
    uploaded = get_uploaded_set(client, 'insumos')
    missing = [ins for ins in insumos if ins['slug'] not in uploaded]

    safe_print(f"\nUploading {len(missing)} individual insumo images...")

    for i, insumo in enumerate(missing):
        slug = insumo['slug']
        sg_slug = insumo['subgrupo_slug']
        storage_path = f"insumos/{slug}.jpg"

        if (i + 1) % 100 == 0:
            safe_print(f"  Progress: {i+1}/{len(missing)}")

        if dry_run:
            continue

        # Reuse subgrupo image
        if sg_slug in subgrupo_cache:
            if upload_image(client, subgrupo_cache[sg_slug], storage_path):
                stats['reused'] += 1
            else:
                stats['failed'] += 1
        else:
            # No subgrupo image — try a generic search based on grupo
            grupo = insumo['grupo'].lower()
            if grupo not in subgrupo_cache:
                # Search once for this grupo
                search = 'agriculture ' + grupo
                img = fetch_wikimedia_image(search)
                if img:
                    subgrupo_cache[grupo] = img
                else:
                    subgrupo_cache[grupo] = None

            if subgrupo_cache.get(grupo):
                if upload_image(client, subgrupo_cache[grupo], storage_path):
                    stats['reused'] += 1
                else:
                    stats['failed'] += 1
            else:
                stats['failed'] += 1

    safe_print(f"\nInsumo results: {stats['found']} new, {stats['reused']} reused, {stats['failed']} failed")
    return stats


def main():
    parser = argparse.ArgumentParser(description='Fill image gaps for individual products/insumos')
    parser.add_argument('--dry-run', action='store_true')
    parser.add_argument('--products-only', action='store_true')
    parser.add_argument('--insumos-only', action='store_true')
    args = parser.parse_args()

    safe_print("Connecting to Supabase...")
    client = get_supabase_client()
    conn = get_db_connection()

    try:
        if not args.insumos_only:
            process_missing_products(client, conn, args.dry_run)

        # Reconnect in case of timeout
        try:
            conn.cursor().execute("SELECT 1")
        except Exception:
            safe_print("Reconnecting to database...")
            conn = get_db_connection(new_connection=True)

        if not args.products_only:
            process_missing_insumos(client, conn, args.dry_run)
    finally:
        conn.close()

    safe_print("\nDone!")


if __name__ == '__main__':
    main()
