"""
Populate image_attributions table by re-searching the same sources that
were used to fetch each product/insumo image.

For each uploaded image, re-queries Wikimedia Commons / Openverse / fruits-360
using the same search terms from fetch_product_images.py, and records the
source URL, license, author, and image title.

Usage:
    python -u -m scripts.populate_attributions [--products-only] [--insumos-only]
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


WIKIMEDIA_API = "https://commons.wikimedia.org/w/api.php"
OPENVERSE_API = "https://api.openverse.org/v1/images/"
USER_AGENT = "AgroAmigo/1.0 (https://github.com/agroamigo; contact@agroamigo.co)"
IMAGE_BUCKET = "product-images"


def slugify(text: str) -> str:
    text = unicodedata.normalize('NFD', text)
    text = ''.join(c for c in text if unicodedata.category(c) != 'Mn')
    text = text.lower().strip()
    text = re.sub(r'[^\w\s-]', '', text)
    text = re.sub(r'[\s_]+', '_', text)
    text = re.sub(r'-+', '-', text)
    return text.strip('_-')


# -----------------------------------------------------------------------
# Import the search term mappings from the fetch scripts
# -----------------------------------------------------------------------

from scripts.fetch_product_images import (
    PRODUCT_SEARCH_TERMS,
    INSUMO_SEARCH_TERMS,
    FRUITS360_MAPPING,
)

from scripts.fill_image_gaps import (
    SPECIFIC_PRODUCT_TERMS,
    INSUMO_SUBGRUPO_SEARCH,
)


# -----------------------------------------------------------------------
# Wikimedia: search and return full metadata (not just the image bytes)
# -----------------------------------------------------------------------

def search_wikimedia_metadata(query: str, limit: int = 3) -> list[dict]:
    """Search Wikimedia Commons and return full attribution metadata."""
    params = {
        'action': 'query',
        'generator': 'search',
        'gsrsearch': f'filetype:bitmap {query}',
        'gsrnamespace': '6',
        'gsrlimit': str(limit),
        'prop': 'imageinfo',
        'iiprop': 'url|size|mime|extmetadata',
        'iiurlwidth': '400',
        'format': 'json',
    }
    url = f"{WIKIMEDIA_API}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers={'User-Agent': USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read())
    except Exception:
        return []

    results = []
    for page in data.get('query', {}).get('pages', {}).values():
        info = page.get('imageinfo', [{}])[0]
        if not info.get('mime', '').startswith('image/'):
            continue

        ext = info.get('extmetadata', {})
        title = page.get('title', '').replace('File:', '')
        page_id = page.get('pageid', '')

        # Extract license
        license_short = ext.get('LicenseShortName', {}).get('value', 'Unknown')
        license_url_val = ext.get('LicenseUrl', {}).get('value', '')

        # Extract author
        author = ext.get('Artist', {}).get('value', '')
        # Strip HTML tags from author
        author = re.sub(r'<[^>]+>', '', author).strip()
        if not author:
            author = ext.get('Credit', {}).get('value', 'Unknown')
            author = re.sub(r'<[^>]+>', '', author).strip()

        results.append({
            'source_name': 'wikimedia',
            'source_url': f'https://commons.wikimedia.org/wiki/File:{urllib.parse.quote(title)}',
            'source_image_url': info.get('url', ''),
            'license': license_short,
            'license_url': license_url_val,
            'author': author[:500] if author else 'Unknown',
            'image_title': title,
        })

    return results


def search_openverse_metadata(query: str, limit: int = 1) -> list[dict]:
    """Search Openverse and return full attribution metadata."""
    params = {
        'q': query,
        'page_size': str(limit),
        'license_type': 'commercial',
    }
    url = f"{OPENVERSE_API}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers={'User-Agent': USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read())
    except Exception:
        return []

    results = []
    for item in data.get('results', []):
        license_name = item.get('license', 'Unknown')
        license_version = item.get('license_version', '')
        if license_version:
            license_name = f'{license_name} {license_version}'.upper()

        results.append({
            'source_name': 'openverse',
            'source_url': item.get('foreign_landing_url', item.get('detail_url', '')),
            'source_image_url': item.get('url', ''),
            'license': license_name,
            'license_url': item.get('license_url', ''),
            'author': (item.get('creator', '') or 'Unknown')[:500],
            'image_title': item.get('title', ''),
        })

    return results


def fruits360_attribution(product_key: str) -> Optional[dict]:
    """Check if a product maps to fruits-360 and return attribution."""
    folder_name = None
    for spanish, english in FRUITS360_MAPPING.items():
        if spanish in product_key:
            folder_name = english
            break
    if not folder_name:
        return None

    return {
        'source_name': 'fruits360',
        'source_url': f'https://github.com/fruits-360/fruits-360-100x100/tree/main/Training/{urllib.parse.quote(folder_name)}',
        'source_image_url': f'https://github.com/fruits-360/fruits-360-100x100/tree/main/Training/{urllib.parse.quote(folder_name)}',
        'license': 'CC BY-SA 4.0',
        'license_url': 'https://creativecommons.org/licenses/by-sa/4.0/',
        'author': 'Horea Muresan, Mihai Oltean',
        'image_title': f'{folder_name} (fruits-360 dataset)',
    }


# -----------------------------------------------------------------------
# Determine what search was used for a given product
# -----------------------------------------------------------------------

def get_product_search_term(slug: str, product_name: str, category: str) -> str:
    """Reconstruct the search term that was used for a product."""
    # Check fill_image_gaps specific terms first
    if slug in SPECIFIC_PRODUCT_TERMS:
        return SPECIFIC_PRODUCT_TERMS[slug]

    # Check original fetch_product_images terms
    name_lower = product_name.lower().strip()
    for spanish, english in PRODUCT_SEARCH_TERMS.items():
        if name_lower == spanish or name_lower.startswith(spanish):
            return english

    # Partial match
    for spanish, english in PRODUCT_SEARCH_TERMS.items():
        if spanish in name_lower:
            return english

    return name_lower


def get_insumo_search_term(subgrupo: str) -> str:
    """Get the search term for an insumo based on its subgrupo."""
    sg_lower = subgrupo.lower()
    for key, term in INSUMO_SEARCH_TERMS.items():
        if key in sg_lower or sg_lower in key:
            return term
    sg_slug = slugify(subgrupo)
    for key, term in INSUMO_SUBGRUPO_SEARCH.items():
        if key == sg_slug:
            return term
    return subgrupo


# -----------------------------------------------------------------------
# Insert attribution into DB
# -----------------------------------------------------------------------

def insert_attribution(conn, entity_type: str, entity_slug: str,
                       storage_path: str, attr: dict):
    """Insert or update an attribution row."""
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO image_attributions
            (entity_type, entity_slug, storage_path, source_name,
             source_url, source_image_url, license, license_url,
             author, image_title)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (entity_type, entity_slug) DO UPDATE SET
            storage_path = EXCLUDED.storage_path,
            source_name = EXCLUDED.source_name,
            source_url = EXCLUDED.source_url,
            source_image_url = EXCLUDED.source_image_url,
            license = EXCLUDED.license,
            license_url = EXCLUDED.license_url,
            author = EXCLUDED.author,
            image_title = EXCLUDED.image_title,
            fetched_at = NOW()
    """, (
        entity_type,
        entity_slug,
        storage_path,
        attr.get('source_name', 'unknown'),
        attr.get('source_url', ''),
        attr.get('source_image_url', ''),
        attr.get('license', 'Unknown'),
        attr.get('license_url', ''),
        attr.get('author', 'Unknown'),
        attr.get('image_title', ''),
    ))


# -----------------------------------------------------------------------
# Main processing
# -----------------------------------------------------------------------

def process_products(conn):
    """Re-search and record attribution for all product images."""
    cur = conn.cursor()
    cur.execute("""
        SELECT DISTINCT p.canonical_name, sc.canonical_name as sub,
               c.canonical_name as cat
        FROM dim_product p
        JOIN dim_subcategory sc ON p.subcategory_id = sc.id
        JOIN dim_category c ON sc.category_id = c.id
        WHERE sc.canonical_name NOT LIKE 'General%%'
        ORDER BY c.canonical_name, p.canonical_name
    """)
    products = cur.fetchall()

    # Check which already have attributions
    cur.execute("SELECT entity_slug FROM image_attributions WHERE entity_type = 'product'")
    existing = set(r['entity_slug'] for r in cur.fetchall())

    total = len(products)
    safe_print(f"\n{'='*60}")
    safe_print(f"Processing {total} products ({len(existing)} already attributed)")
    safe_print(f"{'='*60}\n")

    # Cache: once we find attribution for a search term, reuse it
    search_cache = {}
    stats = {'found': 0, 'cached': 0, 'failed': 0, 'skipped': 0}

    for i, row in enumerate(products):
        slug = slugify(row['canonical_name'])
        if not slug or len(slug) < 2:
            continue

        if slug in existing:
            stats['skipped'] += 1
            continue

        storage_path = f"products/{slug}.jpg"
        search_term = get_product_search_term(slug, row['canonical_name'], row['cat'])

        if (i + 1) % 50 == 0:
            safe_print(f"  Progress: {i+1}/{total} (found={stats['found']}, cached={stats['cached']})")
            conn.commit()

        # Strategy 1: Check fruits-360
        attr = fruits360_attribution(slug)
        if attr:
            insert_attribution(conn, 'product', slug, storage_path, attr)
            stats['found'] += 1
            continue

        # Strategy 2: Check cache
        if search_term in search_cache:
            attr = search_cache[search_term].copy()
            insert_attribution(conn, 'product', slug, storage_path, attr)
            stats['cached'] += 1
            continue

        # Strategy 3: Search Wikimedia
        time.sleep(0.15)
        results = search_wikimedia_metadata(search_term)
        if results:
            attr = results[0]
            search_cache[search_term] = attr
            insert_attribution(conn, 'product', slug, storage_path, attr)
            stats['found'] += 1
            continue

        # Strategy 4: Search Openverse
        time.sleep(3.0)
        results = search_openverse_metadata(search_term)
        if results:
            attr = results[0]
            search_cache[search_term] = attr
            insert_attribution(conn, 'product', slug, storage_path, attr)
            stats['found'] += 1
            continue

        # Strategy 5: Try category-level fallback search
        time.sleep(0.15)
        cat_term = row['cat'].lower() + ' food'
        if cat_term in search_cache:
            attr = search_cache[cat_term].copy()
        else:
            results = search_wikimedia_metadata(cat_term)
            if results:
                attr = results[0]
                search_cache[cat_term] = attr
            else:
                attr = None

        if attr:
            insert_attribution(conn, 'product', slug, storage_path, attr)
            stats['cached'] += 1
        else:
            # Record as unknown
            insert_attribution(conn, 'product', slug, storage_path, {
                'source_name': 'unknown',
                'source_url': '',
                'license': 'Unknown',
                'author': 'Unknown',
                'image_title': '',
            })
            stats['failed'] += 1

    conn.commit()
    safe_print(f"\nProducts: {stats['found']} found, {stats['cached']} cached, "
               f"{stats['skipped']} skipped, {stats['failed']} unknown")
    return stats


def process_insumos(conn):
    """Record attribution for all insumo images."""
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
    insumos = cur.fetchall()

    cur.execute("SELECT entity_slug FROM image_attributions WHERE entity_type = 'insumo'")
    existing = set(r['entity_slug'] for r in cur.fetchall())

    total = len(insumos)
    safe_print(f"\n{'='*60}")
    safe_print(f"Processing {total} insumos ({len(existing)} already attributed)")
    safe_print(f"{'='*60}\n")

    # First, find attribution for each subgrupo
    subgrupo_attr = {}
    subgrupos = set()
    for row in insumos:
        if row['subgrupo']:
            subgrupos.add(row['subgrupo'])

    safe_print(f"Searching attribution for {len(subgrupos)} subgrupos...")
    for sg in sorted(subgrupos):
        search_term = get_insumo_search_term(sg)
        time.sleep(0.15)
        results = search_wikimedia_metadata(search_term)
        if results:
            subgrupo_attr[sg] = results[0]
            safe_print(f"  {sg}: {results[0]['image_title'][:60]}")
        else:
            time.sleep(3.0)
            results = search_openverse_metadata(search_term)
            if results:
                subgrupo_attr[sg] = results[0]
                safe_print(f"  {sg}: {results[0]['image_title'][:60]} (openverse)")
            else:
                safe_print(f"  {sg}: no attribution found")

    conn.commit()

    # Now attribute each individual insumo from its subgrupo
    stats = {'attributed': 0, 'skipped': 0, 'no_source': 0}

    for i, row in enumerate(insumos):
        slug = slugify(row['canonical_name'])
        if not slug or len(slug) < 2:
            continue
        if slug in existing:
            stats['skipped'] += 1
            continue

        storage_path = f"insumos/{slug}.jpg"
        sg = row['subgrupo'] or ''

        if sg in subgrupo_attr:
            attr = subgrupo_attr[sg].copy()
            insert_attribution(conn, 'insumo', slug, storage_path, attr)
            stats['attributed'] += 1
        else:
            # Record with grupo-level note
            insert_attribution(conn, 'insumo', slug, storage_path, {
                'source_name': 'unknown',
                'source_url': '',
                'license': 'Unknown',
                'author': 'Unknown',
                'image_title': f'No specific image found for {sg}',
            })
            stats['no_source'] += 1

        if (i + 1) % 500 == 0:
            safe_print(f"  Progress: {i+1}/{total}")
            conn.commit()

    conn.commit()
    safe_print(f"\nInsumos: {stats['attributed']} attributed, {stats['skipped']} skipped, "
               f"{stats['no_source']} no source")
    return stats


def main():
    parser = argparse.ArgumentParser(description='Populate image attributions')
    parser.add_argument('--products-only', action='store_true')
    parser.add_argument('--insumos-only', action='store_true')
    args = parser.parse_args()

    safe_print("Connecting to database...")
    conn = get_db_connection()

    try:
        if not args.insumos_only:
            process_products(conn)

        # Reconnect if needed
        try:
            conn.cursor().execute("SELECT 1")
        except Exception:
            safe_print("Reconnecting...")
            conn = get_db_connection(new_connection=True)

        if not args.products_only:
            process_insumos(conn)
    finally:
        conn.close()

    safe_print("\nDone!")


if __name__ == '__main__':
    main()
