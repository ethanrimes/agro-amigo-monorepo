"""
Fetch product and insumo images from free sources and upload to Supabase storage.

Sources (all free, no API key required):
  1. Wikimedia Commons API — broadest coverage, no rate limit for reads
  2. fruits-360 GitHub dataset — high-quality fruit/vegetable images (CC BY-SA 4.0)
  3. Openverse API — CC-licensed images (anonymous: 200/day)

Usage:
    python -m scripts.fetch_product_images [--dry-run] [--products-only] [--insumos-only]
"""

import os
import re
import sys
import json
import time
import hashlib
import argparse
import unicodedata
import urllib.request
import urllib.parse
import urllib.error
from pathlib import Path
from typing import Optional

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))


def safe_print(*args, **kwargs):
    """Print that handles encoding errors on Windows (cp1252 console)."""
    try:
        print(*args, **kwargs)
    except UnicodeEncodeError:
        text = ' '.join(str(a) for a in args)
        print(text.encode('ascii', errors='replace').decode('ascii'), **kwargs)

from backend.supabase_client import get_supabase_client, get_db_connection

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
IMAGE_BUCKET = "product-images"
PRODUCTS_PREFIX = "products"
INSUMOS_PREFIX = "insumos"
CATEGORIES_PREFIX = "categories"
SUBCATEGORIES_PREFIX = "subcategories"

# Rate limiting
WIKIMEDIA_DELAY = 0.1       # seconds between Wikimedia API calls
OPENVERSE_DELAY = 3.0       # seconds between Openverse calls (20/min limit)
GITHUB_API_DELAY = 0.5      # seconds between GitHub API calls

# Image settings
TARGET_WIDTH = 400           # px — good for mobile thumbnails
MAX_IMAGE_BYTES = 500_000    # 500 KB max per image

WIKIMEDIA_API = "https://commons.wikimedia.org/w/api.php"
OPENVERSE_API = "https://api.openverse.org/v1/images/"
FRUITS360_API = "https://api.github.com/repos/fruits-360/fruits-360-100x100/contents/Training"

# User agent required by Wikimedia
USER_AGENT = "AgroAmigo/1.0 (https://github.com/agroamigo; contact@agroamigo.co)"

# ---------------------------------------------------------------------------
# Utility helpers
# ---------------------------------------------------------------------------

def slugify(text: str) -> str:
    """Convert text to a URL/filename-safe slug."""
    # Normalize unicode
    text = unicodedata.normalize('NFD', text)
    text = ''.join(c for c in text if unicodedata.category(c) != 'Mn')
    text = text.lower().strip()
    text = re.sub(r'[^\w\s-]', '', text)
    text = re.sub(r'[\s_]+', '_', text)
    text = re.sub(r'-+', '-', text)
    return text.strip('_-')


def normalize_product_name(name: str) -> str:
    """
    Normalize a product name for visual deduplication.
    Strips OCR artifacts, asterisks, extra spaces, case differences.
    """
    # Remove asterisks and trailing markers
    name = re.sub(r'[*+]+$', '', name).strip()
    # Fix doubled OCR characters like "CCaarrnnee" -> "Carne"
    if len(name) > 10:
        deduped = []
        i = 0
        while i < len(name):
            if i + 1 < len(name) and name[i] == name[i+1]:
                # Check if entire word is doubled chars
                pass
            deduped.append(name[i])
            i += 1
        # Only apply if result is significantly shorter (OCR doubling)
        candidate = ''.join(deduped)
        if len(candidate) < len(name) * 0.7:
            name = candidate

    # Remove run-together words artifacts (e.g., "Papapardapastusa")
    # These are handled by matching against known products

    # Normalize unicode
    name = unicodedata.normalize('NFC', name)
    name = name.lower().strip()
    # Remove extra whitespace
    name = re.sub(r'\s+', ' ', name)
    return name


def extract_base_product(product_name: str, category: str) -> str:
    """
    Extract the base product type for image search.
    E.g., "Carne de cerdo, brazo con hueso" -> "carne de cerdo"
         "Huevo rojo AA" -> "huevo"
         "Papa parda pastusa" -> "papa"
    """
    name = normalize_product_name(product_name)

    # For meats, use the cut type
    if category == "Carnes":
        # "carne de cerdo, costilla" -> "carne de cerdo"
        if ',' in name:
            return name.split(',')[0].strip()
        # "pechuga de pollo" -> "pechuga de pollo" (specific enough)
        return name

    # For eggs, just use "huevo"
    if 'huevo' in name:
        return 'huevo'

    # For cheeses, use the specific cheese type
    if 'queso' in name:
        return name

    # For fish/seafood, use the fish name
    if category == "Pescados":
        # "tilapia roja entera congelada" -> "tilapia"
        # "salmón, filete congelado" -> "salmón"
        fish_name = name.split(',')[0].strip()
        # Remove state words
        for word in ['entero', 'entera', 'fresco', 'fresca', 'congelado', 'congelada',
                     'importado', 'importada', 'precocido', 'seco', 'seca']:
            fish_name = fish_name.replace(word, '').strip()
        return fish_name.strip()

    # For processed foods, use the product name as-is
    if category == "Procesados":
        return name

    # For grains, use base grain
    if 'frijol' in name or 'fríjol' in name:
        return 'frijol'
    if 'arroz' in name:
        return 'arroz'
    if 'maíz' in name or 'maiz' in name:
        return 'maiz'

    # For produce, remove regional qualifiers
    regional = ['bogotana', 'bogotano', 'pastusa', 'pastuso', 'valluna', 'valluno',
                'huilense', 'antiqueño', 'santandereano', 'regional', 'importada',
                'importado', 'nacional', 'ecuatoriano', 'llanero', 'llanera',
                'aquitania', 'berlín', 'tenerife', 'ocañera', 'peruana']
    parts = name.split()
    parts = [p for p in parts if p not in regional]
    return ' '.join(parts)


# ---------------------------------------------------------------------------
# Spanish-to-English product name mapping for image search
# ---------------------------------------------------------------------------

PRODUCT_SEARCH_TERMS = {
    # Fruits
    'aguacate': 'avocado',
    'aguacate hass': 'hass avocado',
    'aguacate choquette': 'choquette avocado',
    'arándano': 'blueberry',
    'badea': 'giant granadilla badea fruit',
    'banano': 'banana',
    'banano bocadillo': 'finger banana',
    'banano criollo': 'banana plantain',
    'banano urabá': 'banana',
    'borojó': 'borojo fruit',
    'breva': 'fig fruit breva',
    'ciruela roja': 'red plum',
    'ciruela importada': 'plum fruit',
    'coco': 'coconut',
    'curuba': 'curuba banana passionfruit',
    'durazno': 'peach fruit',
    'durazno importado': 'peach fruit',
    'durazno nacional': 'peach fruit',
    'feijoa': 'feijoa fruit',
    'fresa': 'strawberry',
    'granadilla': 'granadilla sweet passionfruit',
    'guanábana': 'soursop guanabana',
    'guayaba': 'guava',
    'guayaba agria': 'sour guava',
    'guayaba pera': 'pear guava',
    'guayaba manzana': 'apple guava',
    'gulupa': 'purple passionfruit gulupa',
    'higo': 'fig fruit',
    'kiwi': 'kiwi fruit',
    'limón': 'lime lemon',
    'limón común': 'lime citrus',
    'limón tahití': 'persian lime tahiti',
    'limón mandarino': 'mandarin lime',
    'lulo': 'lulo naranjilla fruit',
    'mandarina': 'mandarin tangerine',
    'mandarina arrayana': 'mandarin tangerine',
    'mandarina oneco': 'mandarin tangerine',
    'mango': 'mango fruit',
    'mango tommy': 'tommy atkins mango',
    'mango de azúcar': 'honey mango',
    'mango reina': 'mango fruit',
    'mango yulima': 'mango fruit',
    'mango común': 'mango fruit',
    'mango manzano': 'apple mango',
    'manzana': 'apple fruit',
    'manzana roja importada': 'red apple',
    'manzana verde importada': 'green apple granny smith',
    'manzana royal gala importada': 'royal gala apple',
    'manzana nacional': 'apple fruit',
    'maracuyá': 'passion fruit maracuya',
    'melón': 'melon cantaloupe',
    'melón cantalup': 'cantaloupe melon',
    'mora': 'blackberry andean',
    'mora de castilla': 'andean blackberry mora castilla',
    'naranja': 'orange fruit',
    'naranja valencia': 'valencia orange',
    'naranja sweet': 'navel orange',
    'papaya': 'papaya fruit',
    'papaya maradol': 'maradol papaya',
    'papaya hawaiana': 'hawaiian papaya',
    'patilla': 'watermelon',
    'pera importada': 'pear fruit',
    'pera nacional': 'pear fruit',
    'piña': 'pineapple',
    'piña gold': 'golden pineapple',
    'pitahaya': 'dragon fruit pitahaya',
    'tangelo': 'tangelo citrus',
    'tomate de árbol': 'tamarillo tree tomato',
    'uchuva': 'cape gooseberry physalis',
    'uva': 'grape',
    'uva isabela': 'isabella grape',
    'uva red globe': 'red globe grape',
    'uva roja': 'red grape',
    'uva verde': 'green grape',
    'zapote': 'sapote mamey zapote fruit',

    # Vegetables
    'acelga': 'chard swiss chard',
    'ahuyama': 'pumpkin squash ahuyama',
    'ají topito dulce': 'sweet pepper aji dulce',
    'ajo': 'garlic',
    'apio': 'celery',
    'arveja verde en vaina': 'green peas in pod',
    'berenjena': 'eggplant aubergine',
    'brócoli': 'broccoli',
    'calabacín': 'zucchini courgette',
    'calabaza': 'squash pumpkin',
    'cebolla cabezona blanca': 'white onion',
    'cebolla cabezona roja': 'red onion',
    'cebolla junca': 'green onion scallion',
    'cebolla puerro': 'leek',
    'cebollín chino': 'chives',
    'chócolo mazorca': 'corn cob maize',
    'cidra': 'chayote squash',
    'cilantro': 'cilantro coriander',
    'coles': 'cabbage kale',
    'coliflor': 'cauliflower',
    'espinaca': 'spinach',
    'fríjol verde en vaina': 'green beans',
    'frijol verde': 'green beans',
    'haba verde': 'fava bean broad bean',
    'habichuela': 'green bean string bean',
    'habichuela larga': 'long green bean',
    'lechuga batavia': 'batavia lettuce',
    'lechuga crespa': 'curly lettuce',
    'pepino cohombro': 'cucumber',
    'pepino de rellenar': 'stuffing cucumber',
    'perejil': 'parsley',
    'pimentón': 'bell pepper',
    'pimentón verde': 'green bell pepper',
    'rábano rojo': 'red radish',
    'remolacha': 'beetroot beet',
    'repollo blanco': 'white cabbage',
    'repollo morado': 'red cabbage purple cabbage',
    'repollo verde': 'green cabbage',
    'tomate chonto': 'tomato chonto colombian',
    'tomate larga vida': 'tomato long life',
    'tomate riñón': 'beefsteak tomato',
    'tomate riogrande': 'roma tomato rio grande',
    'zanahoria': 'carrot',

    # Tubers, roots, plantains
    'arracacha': 'arracacha white carrot',
    'arracacha amarilla': 'arracacha yellow',
    'arracacha blanca': 'arracacha white',
    'ñame': 'yam tropical',
    'ñame criollo': 'yam tropical',
    'ñame diamante': 'yam diamond',
    'ñame espino': 'yam thorny',
    'jengibre': 'ginger root',
    'papa': 'potato',
    'papa criolla': 'papa criolla yellow potato colombian',
    'papa parda pastusa': 'potato brown pastusa',
    'papa capira': 'potato capira',
    'papa betina': 'potato',
    'papa nevada': 'potato white',
    'papa rubí': 'red potato ruby',
    'papa sabanera': 'potato colombian',
    'papa suprema': 'potato',
    'papa única': 'potato',
    'papa r-12': 'potato dark',
    'ulluco': 'ulluco tuber papalisa',
    'plátano': 'plantain',
    'plátano hartón verde': 'green plantain',
    'plátano hartón maduro': 'ripe plantain yellow',
    'plátano dominico hartón': 'dominico plantain',
    'plátano comino': 'baby plantain',
    'plátano guineo': 'guineo banana plantain',
    'yuca': 'cassava yuca root',

    # Grains and cereals
    'arroz': 'rice grain',
    'arroz blanco': 'white rice',
    'arroz excelso': 'white rice premium',
    'cuchuco de cebada': 'barley cuchuco',
    'cuchuco de maíz': 'corn cuchuco hominy',
    'maíz amarillo': 'yellow corn maize',
    'maíz blanco': 'white corn maize',
    'maíz pira': 'popcorn corn',
    'fríjol': 'dried beans',
    'fríjol cargamanto': 'cargamanto beans colombian',
    'fríjol calima': 'calima beans',
    'fríjol bolón': 'bolon beans',
    'garbanzo': 'chickpea garbanzo',
    'lenteja': 'lentil',
    'arveja seca': 'dried peas split peas',

    # Meats
    'carne de cerdo': 'pork meat cuts',
    'carne de res': 'beef meat cuts',
    'pollo': 'chicken raw',
    'pechuga de pollo': 'chicken breast',
    'muslos de pollo': 'chicken thigh',
    'piernas de pollo': 'chicken leg',
    'alas de pollo': 'chicken wings',
    'menudencias de pollo': 'chicken giblets',
    'pollo entero': 'whole chicken',
    'rabadillas de pollo': 'chicken back',
    'pierna pernil': 'chicken leg quarter',

    # Fish/seafood
    'tilapia': 'tilapia fish',
    'trucha': 'trout fish',
    'salmón': 'salmon fillet',
    'bagre': 'catfish',
    'mojarra': 'mojarra tilapia fish',
    'bocachico': 'bocachico fish colombian',
    'cachama': 'cachama pacu fish',
    'pargo rojo': 'red snapper',
    'sierra': 'king mackerel sierra fish',
    'corvina': 'corvina sea bass',
    'merluza': 'hake merluza fish',
    'róbalo': 'snook robalo fish',
    'basa': 'pangasius basa fish',
    'blanquillo': 'tilefish blanquillo',
    'nicuro': 'nicuro catfish colombian',
    'capaz magdalena': 'capaz fish magdalena river',
    'camarón': 'shrimp prawn',
    'langostino': 'langoustine prawn',
    'calamar': 'squid calamari',
    'almejas': 'clams shellfish',
    'toyo blanco': 'shark white toyo',

    # Dairy & eggs
    'huevo': 'eggs chicken eggs',
    'leche en polvo': 'powdered milk',
    'leche cruda': 'raw milk',
    'queso campesino': 'queso campesino colombian cheese',
    'queso costeño': 'queso costeño colombian coast cheese',
    'queso doble crema': 'double cream cheese colombian',
    'queso cuajada': 'cuajada fresh cheese',
    'queso caqueté': 'caqueta cheese colombian',

    # Processed foods
    'aceite de palma': 'palm oil bottle',
    'aceite girasol': 'sunflower oil bottle',
    'aceite soya': 'soybean oil bottle',
    'aceite vegetal mezcla': 'vegetable oil bottle',
    'manteca': 'lard cooking fat',
    'margarina': 'margarine butter',
    'azúcar morena': 'brown sugar',
    'azúcar refinada': 'white sugar refined',
    'azúcar sulfitada': 'raw sugar',
    'panela': 'panela unrefined cane sugar block',
    'panela cuadrada': 'panela square block',
    'panela redonda': 'panela round block',
    'panela pulverizada': 'panela powder',
    'café molido': 'ground coffee',
    'café instantáneo': 'instant coffee',
    'chocolate amargo': 'dark chocolate bar',
    'chocolate dulce': 'sweet chocolate bar',
    'chocolate instantáneo': 'chocolate powder cocoa',
    'avena en hojuelas': 'rolled oats oatmeal',
    'avena molida': 'ground oats',
    'harina de trigo': 'wheat flour',
    'harina precocida de maíz': 'precooked corn flour arepa',
    'fécula de maíz': 'cornstarch',
    'sal yodada': 'iodized salt',
    'galletas saladas': 'saltine crackers',
    'galletas dulces': 'sweet cookies',
    'pastas alimenticias': 'pasta spaghetti',
    'sardinas en lata': 'canned sardines',
    'lomitos de atún en lata': 'canned tuna',
    'arveja enlatada': 'canned peas',
    'fríjol enlatado': 'canned beans',
    'maíz enlatado': 'canned corn',
    'bocadillo veleño': 'bocadillo guava paste veleño',
    'gelatina': 'gelatin dessert',
    'vinagre': 'vinegar bottle',
    'salsa de tomate': 'ketchup tomato sauce',
    'mayonesa': 'mayonnaise',
    'mostaza': 'mustard',
    'jugo de frutas': 'fruit juice box',
    'jugo instantáneo': 'instant juice powder',
    'sopa de pollo': 'chicken soup box',
    'color': 'annatto coloring achiote',
}

# Insumo subgrupo search terms
INSUMO_SEARCH_TERMS = {
    'arrendamiento de tierras': 'agricultural farmland colombia',
    'elementos agropecuarios': 'farm equipment tools agriculture',
    'empaques agropecuarios': 'agricultural packaging sacks bags',
    'especies productivas': 'livestock cattle poultry farm animals',
    'jornales': 'farm worker agricultural labor',
    'material de propagación': 'plant seedlings seeds nursery',
    'bioinsumos': 'bioinsumos organic fertilizer',
    'coadyuvantes, molusquicidas, reguladores fisiológicos y otros': 'agricultural adjuvant spray',
    'fertilizantes, enmiendas y acondicionadores de suelo': 'fertilizer bags agriculture',
    'fungicidas': 'fungicide agricultural spray',
    'herbicidas': 'herbicide weed killer agriculture',
    'insecticidas, acaricidas y nematicidas': 'insecticide agricultural pest control',
    'alimentos balanceados, suplementos, coadyuvantes, adsorbentes, enzimas y aditivos': 'animal feed livestock supplement',
    'antibióticos, antimicóticos y antiparasitarios': 'veterinary medicine antibiotic',
    'antisépticos, desinfectantes e higiene': 'livestock disinfectant veterinary hygiene',
    'hormonales': 'veterinary hormones livestock',
    'insecticidas, plaguicidas y repelentes': 'livestock insect repellent spray',
    'medicamentos': 'veterinary medicine livestock',
    'vitaminas, sales y minerales': 'mineral salt block livestock vitamin',
}


# ---------------------------------------------------------------------------
# Image source: Wikimedia Commons
# ---------------------------------------------------------------------------

def search_wikimedia(query: str, limit: int = 3) -> list[dict]:
    """Search Wikimedia Commons for images. Returns list of {title, url, thumb}."""
    params = {
        'action': 'query',
        'generator': 'search',
        'gsrsearch': f'filetype:bitmap {query}',
        'gsrnamespace': '6',  # File namespace
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
        safe_print(f"  [wikimedia] Search error for '{query}': {e}")
        return []

    results = []
    pages = data.get('query', {}).get('pages', {})
    for page in pages.values():
        info = page.get('imageinfo', [{}])[0]
        mime = info.get('mime', '')
        if not mime.startswith('image/'):
            continue
        # Prefer the thumbnail URL at target width
        thumb = info.get('thumburl', info.get('url', ''))
        original = info.get('url', '')
        results.append({
            'title': page.get('title', ''),
            'thumb': thumb,
            'url': original,
            'width': info.get('thumbwidth', info.get('width', 0)),
            'height': info.get('thumbheight', info.get('height', 0)),
            'size': info.get('size', 0),
        })

    return results


def download_image(url: str) -> Optional[bytes]:
    """Download an image from URL, return bytes or None."""
    req = urllib.request.Request(url, headers={'User-Agent': USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = resp.read()
            if len(data) > MAX_IMAGE_BYTES:
                # Try thumbnail instead — but we already requested thumb
                pass
            return data
    except Exception as e:
        safe_print(f"  [download] Error: {e}")
        return None


# ---------------------------------------------------------------------------
# Image source: Openverse
# ---------------------------------------------------------------------------

def search_openverse(query: str, limit: int = 1) -> list[dict]:
    """Search Openverse for CC-licensed images."""
    params = {
        'q': query,
        'page_size': str(limit),
        'license_type': 'commercial',  # commercially usable
    }
    url = f"{OPENVERSE_API}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers={'User-Agent': USER_AGENT})

    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read())
    except Exception as e:
        safe_print(f"  [openverse] Search error for '{query}': {e}")
        return []

    results = []
    for item in data.get('results', []):
        thumb = item.get('thumbnail', item.get('url', ''))
        results.append({
            'title': item.get('title', ''),
            'thumb': thumb,
            'url': item.get('url', ''),
            'source': item.get('source', ''),
            'license': item.get('license', ''),
            'creator': item.get('creator', ''),
        })
    return results


# ---------------------------------------------------------------------------
# Image source: fruits-360 (GitHub)
# ---------------------------------------------------------------------------

# Mapping from Spanish product names to fruits-360 folder names
FRUITS360_MAPPING = {
    'aguacate': 'Avocado',
    'arándano': 'Blueberry',
    'banano': 'Banana',
    'cereza': 'Cherry',
    'ciruela': 'Plum',
    'coco': 'Cocos',
    'durazno': 'Peach',
    'fresa': 'Strawberry',
    'granadilla': 'Granadilla',
    'guayaba': 'Guava',
    'higo': 'Fig',
    'kiwi': 'Kiwi',
    'limón': 'Lemon',
    'limón tahití': 'Limes',
    'mandarina': 'Mandarine',
    'mango': 'Mango',
    'manzana roja': 'Apple Red',
    'manzana verde': 'Apple Granny Smith',
    'manzana royal gala': 'Apple Red',
    'maracuyá': 'Maracuja',
    'melón cantalup': 'Cantaloupe',
    'mora': 'Mulberry',
    'naranja': 'Orange',
    'papaya': 'Papaya',
    'patilla': 'Watermelon',
    'pera': 'Pear',
    'piña': 'Pineapple',
    'pitahaya': 'Pitahaya Red',
    'tangelo': 'Tangelo',
    'tomate': 'Tomato',
    'uchuva': 'Physalis',
    'uva roja': 'Grape Pink',
    'uva verde': 'Grape White',
    'uva isabela': 'Grape Blue',
}

_fruits360_folders: Optional[list] = None

def get_fruits360_folders() -> list[str]:
    """Get list of available folders in fruits-360 Training directory."""
    global _fruits360_folders
    if _fruits360_folders is not None:
        return _fruits360_folders

    req = urllib.request.Request(FRUITS360_API, headers={
        'User-Agent': USER_AGENT,
        'Accept': 'application/vnd.github.v3+json',
    })
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read())
        _fruits360_folders = [item['name'] for item in data if item['type'] == 'dir']
    except Exception as e:
        safe_print(f"  [fruits360] Error loading folders: {e}")
        _fruits360_folders = []

    return _fruits360_folders


def get_fruits360_image(product_key: str) -> Optional[bytes]:
    """Try to get an image from fruits-360 for the given product."""
    folder_name = None

    # Check direct mapping
    for spanish, english in FRUITS360_MAPPING.items():
        if spanish in product_key:
            folder_name = english
            break

    if not folder_name:
        return None

    # Find matching folder (case-insensitive partial match)
    folders = get_fruits360_folders()
    matches = [f for f in folders if folder_name.lower() in f.lower()]
    if not matches:
        return None

    # Use the first match, get first image
    target_folder = matches[0]
    api_url = f"{FRUITS360_API}/{urllib.parse.quote(target_folder)}"
    req = urllib.request.Request(api_url, headers={
        'User-Agent': USER_AGENT,
        'Accept': 'application/vnd.github.v3+json',
    })

    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            files = json.loads(resp.read())
        # Get first jpg file
        jpg_files = [f for f in files if f['name'].endswith('.jpg')]
        if not jpg_files:
            return None

        # Download using the download_url
        image_url = jpg_files[0].get('download_url')
        if image_url:
            time.sleep(GITHUB_API_DELAY)
            return download_image(image_url)
    except Exception as e:
        safe_print(f"  [fruits360] Error for {target_folder}: {e}")

    return None


# ---------------------------------------------------------------------------
# Supabase storage operations
# ---------------------------------------------------------------------------

def ensure_bucket_exists(client):
    """Create the product-images bucket if it doesn't exist, make it public."""
    try:
        client.storage.get_bucket(IMAGE_BUCKET)
        safe_print(f"Bucket '{IMAGE_BUCKET}' already exists.")
    except Exception:
        try:
            client.storage.create_bucket(IMAGE_BUCKET, options={"public": True})
            safe_print(f"Created public bucket '{IMAGE_BUCKET}'.")
        except Exception as e:
            if "already exists" not in str(e).lower():
                raise
            safe_print(f"Bucket '{IMAGE_BUCKET}' already exists (caught on create).")


def upload_to_supabase(client, image_data: bytes, storage_path: str) -> bool:
    """Upload image bytes to Supabase storage. Returns True if successful."""
    try:
        client.storage.from_(IMAGE_BUCKET).upload(
            storage_path,
            image_data,
            {"content-type": "image/jpeg"}
        )
        return True
    except Exception as e:
        error_str = str(e).lower()
        if 'duplicate' in error_str or 'already exists' in error_str or '409' in error_str:
            return True  # Already uploaded
        safe_print(f"  [upload] Error: {e}")
        return False


def image_exists(client, storage_path: str) -> bool:
    """Check if an image already exists in storage."""
    try:
        directory = str(Path(storage_path).parent)
        filename = Path(storage_path).name
        files = client.storage.from_(IMAGE_BUCKET).list(directory)
        return any(f.get('name') == filename for f in files)
    except Exception:
        return False


def get_public_url(supabase_url: str, storage_path: str) -> str:
    """Construct the public URL for a storage object."""
    return f"{supabase_url}/storage/v1/object/public/{IMAGE_BUCKET}/{storage_path}"


# ---------------------------------------------------------------------------
# Main orchestration
# ---------------------------------------------------------------------------

def find_image_for_product(product_key: str, search_term: str) -> Optional[bytes]:
    """
    Try multiple sources to find an image for a product.
    Returns image bytes or None.
    """
    # 1. Try fruits-360 first (best quality for produce)
    safe_print(f"  Trying fruits-360...")
    img = get_fruits360_image(product_key)
    if img:
        safe_print(f"  Found in fruits-360!")
        return img
    time.sleep(GITHUB_API_DELAY)

    # 2. Try Wikimedia Commons
    safe_print(f"  Trying Wikimedia Commons for '{search_term}'...")
    time.sleep(WIKIMEDIA_DELAY)
    results = search_wikimedia(search_term)
    for r in results:
        img = download_image(r['thumb'])
        if img:
            safe_print(f"  Found on Wikimedia: {r['title']}")
            return img

    # 3. Try Openverse (rate limited)
    safe_print(f"  Trying Openverse for '{search_term}'...")
    time.sleep(OPENVERSE_DELAY)
    results = search_openverse(search_term)
    for r in results:
        img = download_image(r['thumb'])
        if img:
            safe_print(f"  Found on Openverse: {r['title']} (license: {r['license']})")
            return img

    return None


def get_unique_products(conn) -> list[dict]:
    """
    Get deduplicated list of products that need images.
    Returns list of {key, search_term, category, subcategory, products}.
    """
    cur = conn.cursor()
    cur.execute("""
        SELECT DISTINCT
            p.canonical_name,
            sc.canonical_name as subcategory,
            c.canonical_name as category
        FROM dim_product p
        JOIN dim_subcategory sc ON p.subcategory_id = sc.id
        JOIN dim_category c ON sc.category_id = c.id
        WHERE sc.canonical_name NOT LIKE 'General%%'
        ORDER BY c.canonical_name, sc.canonical_name, p.canonical_name
    """)
    rows = cur.fetchall()

    # Group by base product
    groups = {}
    for row in rows:
        base = extract_base_product(row['canonical_name'], row['category'])
        key = slugify(base)
        if not key or len(key) < 2:
            continue
        if key not in groups:
            groups[key] = {
                'key': key,
                'base_name': base,
                'category': row['category'],
                'subcategory': row['subcategory'],
                'products': [],
            }
        groups[key]['products'].append(row['canonical_name'])

    # Add search terms
    for g in groups.values():
        base = g['base_name']
        # Look up in our mapping
        search_term = None
        for spanish, english in PRODUCT_SEARCH_TERMS.items():
            if base == spanish or base.startswith(spanish):
                search_term = english
                break
        if not search_term:
            # Try partial match
            for spanish, english in PRODUCT_SEARCH_TERMS.items():
                if spanish in base:
                    search_term = english
                    break
        if not search_term:
            # Fall back to the base name itself
            search_term = base
        g['search_term'] = search_term

    return list(groups.values())


def get_insumo_subgrupos(conn) -> list[dict]:
    """Get list of insumo subgrupos that need images."""
    cur = conn.cursor()
    cur.execute("""
        SELECT DISTINCT
            g.canonical_name as grupo,
            sg.canonical_name as subgrupo
        FROM dim_insumo_subgrupo sg
        JOIN dim_insumo_grupo g ON sg.grupo_id = g.id
        ORDER BY g.canonical_name, sg.canonical_name
    """)
    rows = cur.fetchall()

    result = []
    for row in rows:
        subgrupo = row['subgrupo']
        key = slugify(subgrupo)
        search_term = INSUMO_SEARCH_TERMS.get(subgrupo.lower(), subgrupo)
        result.append({
            'key': key,
            'subgrupo': subgrupo,
            'grupo': row['grupo'],
            'search_term': search_term,
        })
    return result


def process_products(client, conn, dry_run: bool = False):
    """Fetch and upload images for all products."""
    products = get_unique_products(conn)
    safe_print(f"\n{'='*60}")
    safe_print(f"Processing {len(products)} unique product image groups")
    safe_print(f"{'='*60}\n")

    stats = {'found': 0, 'skipped': 0, 'failed': 0}
    manifest = {}

    for i, product in enumerate(products):
        key = product['key']
        storage_path = f"{PRODUCTS_PREFIX}/{key}.jpg"

        safe_print(f"[{i+1}/{len(products)}] {product['base_name']} ({key})")
        safe_print(f"  Category: {product['category']} > {product['subcategory']}")
        safe_print(f"  Covers {len(product['products'])} product variants")
        safe_print(f"  Search: {product['search_term']}")

        # Check if already uploaded
        if not dry_run and image_exists(client, storage_path):
            safe_print(f"  Already uploaded, skipping.")
            stats['skipped'] += 1
            manifest[key] = storage_path
            continue

        if dry_run:
            safe_print(f"  [DRY RUN] Would search and upload to {storage_path}")
            stats['skipped'] += 1
            continue

        img_data = find_image_for_product(product['key'], product['search_term'])
        if img_data:
            if upload_to_supabase(client, img_data, storage_path):
                safe_print(f"  Uploaded to {storage_path} ({len(img_data)} bytes)")
                stats['found'] += 1
                manifest[key] = storage_path
            else:
                stats['failed'] += 1
        else:
            safe_print(f"  No image found!")
            stats['failed'] += 1

        safe_print()

    return stats, manifest


def process_insumos(client, conn, dry_run: bool = False):
    """Fetch and upload images for insumo subgrupos."""
    subgrupos = get_insumo_subgrupos(conn)
    safe_print(f"\n{'='*60}")
    safe_print(f"Processing {len(subgrupos)} insumo subgrupos")
    safe_print(f"{'='*60}\n")

    stats = {'found': 0, 'skipped': 0, 'failed': 0}
    manifest = {}

    for i, sg in enumerate(subgrupos):
        key = sg['key']
        storage_path = f"{INSUMOS_PREFIX}/{key}.jpg"

        safe_print(f"[{i+1}/{len(subgrupos)}] {sg['subgrupo']}")
        safe_print(f"  Grupo: {sg['grupo']}")
        safe_print(f"  Search: {sg['search_term']}")

        if not dry_run and image_exists(client, storage_path):
            safe_print(f"  Already uploaded, skipping.")
            stats['skipped'] += 1
            manifest[key] = storage_path
            continue

        if dry_run:
            safe_print(f"  [DRY RUN] Would search and upload to {storage_path}")
            stats['skipped'] += 1
            continue

        # For insumos, skip fruits-360, go straight to Wikimedia/Openverse
        safe_print(f"  Trying Wikimedia Commons...")
        time.sleep(WIKIMEDIA_DELAY)
        img_data = None
        results = search_wikimedia(sg['search_term'])
        for r in results:
            img_data = download_image(r['thumb'])
            if img_data:
                safe_print(f"  Found on Wikimedia: {r['title']}")
                break

        if not img_data:
            safe_print(f"  Trying Openverse...")
            time.sleep(OPENVERSE_DELAY)
            results = search_openverse(sg['search_term'])
            for r in results:
                img_data = download_image(r['thumb'])
                if img_data:
                    safe_print(f"  Found on Openverse: {r['title']}")
                    break

        if img_data:
            if upload_to_supabase(client, img_data, storage_path):
                safe_print(f"  Uploaded to {storage_path} ({len(img_data)} bytes)")
                stats['found'] += 1
                manifest[key] = storage_path
            else:
                stats['failed'] += 1
        else:
            safe_print(f"  No image found!")
            stats['failed'] += 1

        safe_print()

    return stats, manifest


def save_manifest(product_manifest: dict, insumo_manifest: dict, supabase_url: str):
    """Save a JSON manifest mapping product/insumo keys to public URLs."""
    manifest = {
        'generated': time.strftime('%Y-%m-%dT%H:%M:%SZ'),
        'bucket': IMAGE_BUCKET,
        'base_url': f"{supabase_url}/storage/v1/object/public/{IMAGE_BUCKET}",
        'products': {},
        'insumos': {},
    }

    base = manifest['base_url']
    for key, path in product_manifest.items():
        manifest['products'][key] = f"{base}/{path}"
    for key, path in insumo_manifest.items():
        manifest['insumos'][key] = f"{base}/{path}"

    manifest_path = Path(__file__).parent.parent / "exports" / "image_manifest.json"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    with open(manifest_path, 'w', encoding='utf-8') as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)
    safe_print(f"\nManifest saved to {manifest_path}")
    return manifest


def main():
    parser = argparse.ArgumentParser(description='Fetch product/insumo images')
    parser.add_argument('--dry-run', action='store_true', help='Preview without downloading/uploading')
    parser.add_argument('--products-only', action='store_true', help='Only process products')
    parser.add_argument('--insumos-only', action='store_true', help='Only process insumos')
    args = parser.parse_args()

    # Initialize clients
    safe_print("Connecting to Supabase...")
    client = get_supabase_client()
    conn = get_db_connection()
    supabase_url = os.getenv("SUPABASE_URL")

    if not args.dry_run:
        ensure_bucket_exists(client)

    product_manifest = {}
    insumo_manifest = {}

    try:
        if not args.insumos_only:
            p_stats, product_manifest = process_products(client, conn, args.dry_run)
            safe_print(f"\nProducts: {p_stats['found']} found, {p_stats['skipped']} skipped, {p_stats['failed']} failed")

        if not args.products_only:
            i_stats, insumo_manifest = process_insumos(client, conn, args.dry_run)
            safe_print(f"\nInsumos: {i_stats['found']} found, {i_stats['skipped']} skipped, {i_stats['failed']} failed")

        if not args.dry_run:
            save_manifest(product_manifest, insumo_manifest, supabase_url)

    finally:
        conn.close()

    safe_print("\nDone!")


if __name__ == '__main__':
    main()
