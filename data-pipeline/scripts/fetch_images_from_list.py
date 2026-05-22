"""Process a TSV chunk of canonical entities, searching Wikimedia + Openverse
(+ fallback search variants), and upload the best image found to Supabase storage.

Usage:
    python -u -m scripts.fetch_images_from_list <input.tsv> <kind>
        kind = 'products' or 'insumos'

Input TSV columns: id, canonical_name, category, subcategory, slug

Outputs a result line per entity to stdout:
    OK  <slug>  <source>  <title>
    SKIP <slug>  already_uploaded
    FAIL <slug>  no_image_found
"""
from __future__ import annotations

import csv
import io
import os
import re
import sys
import time
import json
import unicodedata
import urllib.parse
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env")

from backend.supabase_client import get_supabase_client

WIKIMEDIA_API = "https://commons.wikimedia.org/w/api.php"
OPENVERSE_API = "https://api.openverse.org/v1/images/"
USER_AGENT = "AgroAmigo/1.0 (https://github.com/agroamigo; contact@agroamigo.co)"
IMAGE_BUCKET = "product-images"
MAX_BYTES = 800_000


def slugify(text: str) -> str:
    if not text:
        return ""
    text = unicodedata.normalize('NFD', text)
    text = ''.join(c for c in text if unicodedata.category(c) != 'Mn')
    text = text.lower().strip()
    text = re.sub(r'[^\w\s-]', '', text)
    text = re.sub(r'[\s_]+', '_', text)
    text = re.sub(r'-+', '-', text)
    return text


def _http_get(url: str, timeout=15) -> bytes | None:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            data = r.read(MAX_BYTES + 1)
            if len(data) > MAX_BYTES:
                return None
            return data
    except Exception:
        return None


def _http_get_json(url: str, timeout=15) -> dict | None:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8", "replace"))
    except Exception:
        return None


def search_wikimedia(query: str, limit=5) -> list[dict]:
    params = {
        "action": "query",
        "format": "json",
        "generator": "search",
        "gsrsearch": f"{query} filetype:bitmap",
        "gsrnamespace": "6",
        "gsrlimit": str(limit),
        "prop": "imageinfo",
        "iiprop": "url",
        "iiurlwidth": "400",
    }
    url = WIKIMEDIA_API + "?" + urllib.parse.urlencode(params)
    data = _http_get_json(url)
    if not data:
        return []
    pages = (data.get("query") or {}).get("pages") or {}
    out = []
    for p in pages.values():
        ii = (p.get("imageinfo") or [{}])[0]
        thumb = ii.get("thumburl") or ii.get("url")
        if thumb:
            out.append({"title": p.get("title", ""), "thumb": thumb})
    return out


def search_openverse(query: str, limit=5) -> list[dict]:
    url = f"{OPENVERSE_API}?q={urllib.parse.quote(query)}&page_size={limit}&license_type=all"
    data = _http_get_json(url)
    if not data:
        return []
    out = []
    for r in (data.get("results") or [])[:limit]:
        thumb = r.get("thumbnail") or r.get("url")
        if thumb:
            out.append({"title": r.get("title", ""), "thumb": thumb})
    return out


def build_queries(name: str, category: str, kind: str) -> list[str]:
    """Build progressively broader search queries for an entity."""
    queries: list[str] = []
    n = name.strip()
    # Remove footnote asterisks, parens
    n = re.sub(r"\s*\*+", "", n)
    n = re.sub(r"\s*\(.*?\)\s*", " ", n).strip()
    cat = (category or "").strip()

    if kind == "products":
        # Spanish primary
        queries.append(f"{n} fruta")
        queries.append(f"{n} alimento")
        queries.append(n)
        if cat:
            queries.append(f"{n} {cat}")
        # English fallback for common items
        translit = n.lower()
        translations = {
            "naranja": "orange fruit", "limón": "lemon", "limon": "lemon",
            "manzana": "apple", "pera": "pear", "uva": "grape",
            "tomate": "tomato", "cebolla": "onion", "papa": "potato",
            "yuca": "cassava", "plátano": "plantain", "platano": "plantain",
            "aguacate": "avocado hass", "carne": "meat",
            "leche": "milk", "queso": "cheese", "pollo": "chicken",
            "pescado": "fish", "huevo": "egg", "harina": "flour",
            "arroz": "rice", "frijol": "beans", "maíz": "corn",
            "zanahoria": "carrot", "lechuga": "lettuce", "espinaca": "spinach",
        }
        for es, en in translations.items():
            if es in translit.lower():
                queries.append(en)
                break
    else:  # insumos
        # Agro inputs — brand + generic
        queries.append(f"{n} fertilizer")
        queries.append(f"{n} agricultural product")
        queries.append(n)
        if cat:
            queries.append(f"{n} {cat}")
        # Common insumo translations
        agro_terms = {
            "fungicida": "fungicide", "herbicida": "herbicide",
            "insecticida": "insecticide", "fertilizante": "fertilizer",
            "abono": "fertilizer", "alimento": "animal feed",
            "vacuna": "veterinary vaccine", "antibiótico": "antibiotic",
            "semilla": "agricultural seed", "urea": "urea fertilizer",
            "sulfato": "sulfate fertilizer", "nitrato": "nitrate fertilizer",
        }
        nl = n.lower()
        for es, en in agro_terms.items():
            if es in nl:
                queries.append(en)
                break

    # De-dup preserving order
    seen = set()
    uniq = []
    for q in queries:
        q2 = q.strip()
        if q2 and q2.lower() not in seen:
            seen.add(q2.lower())
            uniq.append(q2)
    return uniq[:5]


def image_exists(client, path: str) -> bool:
    try:
        folder, fname = path.rsplit("/", 1)
        files = client.storage.from_(IMAGE_BUCKET).list(folder, {"limit": 5000})
        return any(f.get("name") == fname for f in files)
    except Exception:
        return False


def upload(client, path: str, data: bytes) -> bool:
    try:
        client.storage.from_(IMAGE_BUCKET).upload(
            path, data,
            {"content-type": "image/jpeg", "upsert": "true"},
        )
        return True
    except Exception as e:
        es = str(e).lower()
        if "duplicate" in es or "already exists" in es or "409" in es:
            return True
        sys.stderr.write(f"upload err: {e}\n")
        return False


def fetch_one(name: str, category: str, kind: str) -> tuple[bytes | None, str, str]:
    """Returns (image_bytes, source, title) or (None, '', '')."""
    queries = build_queries(name, category, kind)
    for q in queries:
        for source, fn in (("wikimedia", search_wikimedia), ("openverse", search_openverse)):
            try:
                results = fn(q, limit=3)
            except Exception:
                results = []
            for r in results:
                data = _http_get(r["thumb"], timeout=15)
                if data and 1000 < len(data) <= MAX_BYTES:
                    return data, source, r.get("title", "")
            time.sleep(0.4)
    return None, "", ""


def main():
    if len(sys.argv) < 3:
        print("Usage: fetch_images_from_list <input.tsv> <products|insumos>", file=sys.stderr)
        sys.exit(2)
    input_path = sys.argv[1]
    kind = sys.argv[2]
    assert kind in ("products", "insumos")

    client = get_supabase_client()

    with open(input_path, "r", encoding="utf-8") as f:
        rows = list(csv.DictReader(f, delimiter="\t"))

    print(f"Processing {len(rows)} {kind} from {input_path}", flush=True)
    found = skipped = failed = 0
    for i, row in enumerate(rows, 1):
        name = row["canonical_name"]
        cat = row.get("category") or row.get("grupo") or ""
        slug = row.get("slug") or (slugify(name) + ".jpg")
        path = f"{kind}/{slug}"

        if image_exists(client, path):
            skipped += 1
            print(f"[{i}/{len(rows)}] SKIP {slug} already_uploaded", flush=True)
            continue

        data, source, title = fetch_one(name, cat, kind)
        if data and upload(client, path, data):
            found += 1
            print(f"[{i}/{len(rows)}] OK   {slug} {source} {title[:60]}", flush=True)
        else:
            failed += 1
            print(f"[{i}/{len(rows)}] FAIL {slug} no_image", flush=True)

    print(f"\nDone: {found} found, {skipped} skipped, {failed} failed", flush=True)


if __name__ == "__main__":
    main()
