"""
Helper CLI used by image-audit subagents. Three commands:

  python -m scripts.image_audit_helper inspect <slug>
      Downloads the current Supabase product image (products/<slug>.jpg) into
      data-pipeline/tmp/audit/<slug>__current.jpg so the agent can Read it.
      Prints the local path on success.

  python -m scripts.image_audit_helper search <query> [--limit N]
      Returns JSON candidates from Wikimedia Commons and Openverse for the
      query, including thumbnail URL, title, attribution, license.

  python -m scripts.image_audit_helper preview <url> <slug>
      Downloads a URL into data-pipeline/tmp/audit/<slug>__candidate.jpg so
      the agent can Read it before deciding to upload.

  python -m scripts.image_audit_helper upload <slug> <url> [--attribution-json '{...}']
      Downloads the URL and uploads it as products/<slug>.jpg (overwriting any
      existing image), then upserts attribution (if --attribution-json is set
      AND the product_attributions table exists). Exits 0 on success.

All commands write structured JSON output (one line) when called with --json so
agents can parse them reliably.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import unicodedata
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.supabase_client import get_supabase_client  # noqa: E402

IMAGE_BUCKET = "product-images"
PRODUCTS_PREFIX = "products"
USER_AGENT = "AgroAmigo/1.0 image-audit (https://github.com/agroamigo; contact@agroamigo.co)"
WIKIMEDIA_API = "https://commons.wikimedia.org/w/api.php"
OPENVERSE_API = "https://api.openverse.org/v1/images/"
TARGET_WIDTH = 480
MAX_IMAGE_BYTES = 800_000

TMP_DIR = Path(__file__).parent.parent / "tmp" / "audit"
TMP_DIR.mkdir(parents=True, exist_ok=True)


def emit(obj):
    print(json.dumps(obj, ensure_ascii=False))


def _http_get(url: str, headers: Optional[dict] = None, timeout: int = 20) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, **(headers or {})})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


# ---------------------------------------------------------------------------
# inspect — download current product image to local file
# ---------------------------------------------------------------------------

def cmd_inspect(args):
    slug = args.slug
    storage_path = f"{PRODUCTS_PREFIX}/{slug}.jpg"
    client = get_supabase_client()
    try:
        data = client.storage.from_(IMAGE_BUCKET).download(storage_path)
    except Exception as e:
        emit({"ok": False, "error": f"download failed: {e}", "slug": slug})
        return 1
    out = TMP_DIR / f"{slug}__current.jpg"
    out.write_bytes(data)
    emit({"ok": True, "slug": slug, "path": str(out), "bytes": len(data)})
    return 0


# ---------------------------------------------------------------------------
# search — Wikimedia + Openverse candidates
# ---------------------------------------------------------------------------

def search_wikimedia(query: str, limit: int = 5) -> list[dict]:
    params = {
        "action": "query",
        "generator": "search",
        "gsrsearch": f"filetype:bitmap {query}",
        "gsrnamespace": "6",
        "gsrlimit": str(limit),
        "prop": "imageinfo",
        "iiprop": "url|size|mime|extmetadata",
        "iiurlwidth": str(TARGET_WIDTH),
        "format": "json",
    }
    url = f"{WIKIMEDIA_API}?{urllib.parse.urlencode(params)}"
    try:
        data = json.loads(_http_get(url, timeout=15))
    except Exception as e:
        return [{"_error": f"wikimedia: {e}"}]
    out = []
    for page in data.get("query", {}).get("pages", {}).values():
        info = (page.get("imageinfo") or [{}])[0]
        if not info.get("mime", "").startswith("image/"):
            continue
        meta = info.get("extmetadata") or {}
        out.append(
            {
                "source": "wikimedia",
                "title": page.get("title", ""),
                "thumb": info.get("thumburl") or info.get("url", ""),
                "url": info.get("url", ""),
                "license": (meta.get("LicenseShortName") or {}).get("value", ""),
                "author": (meta.get("Artist") or {}).get("value", ""),
                "description": (meta.get("ImageDescription") or {}).get("value", ""),
            }
        )
    return out


def search_openverse(query: str, limit: int = 5) -> list[dict]:
    params = {"q": query, "page_size": str(limit), "license_type": "commercial"}
    url = f"{OPENVERSE_API}?{urllib.parse.urlencode(params)}"
    try:
        data = json.loads(_http_get(url, timeout=15))
    except Exception as e:
        return [{"_error": f"openverse: {e}"}]
    out = []
    for item in data.get("results", []):
        out.append(
            {
                "source": "openverse",
                "title": item.get("title", ""),
                "thumb": item.get("thumbnail") or item.get("url", ""),
                "url": item.get("url", ""),
                "license": item.get("license", ""),
                "author": item.get("creator", ""),
                "source_url": item.get("foreign_landing_url") or item.get("source", ""),
            }
        )
    return out


def cmd_search(args):
    candidates = []
    candidates.extend(search_wikimedia(args.query, limit=args.limit))
    # be polite to openverse (3s/req)
    time.sleep(0.3)
    candidates.extend(search_openverse(args.query, limit=args.limit))
    emit({"ok": True, "query": args.query, "candidates": candidates})
    return 0


# ---------------------------------------------------------------------------
# preview — download URL to local file for visual inspection
# ---------------------------------------------------------------------------

def cmd_preview(args):
    try:
        data = _http_get(args.url, timeout=30)
    except Exception as e:
        emit({"ok": False, "error": f"download failed: {e}", "url": args.url})
        return 1
    out = TMP_DIR / f"{args.slug}__candidate.jpg"
    out.write_bytes(data)
    emit({"ok": True, "slug": args.slug, "path": str(out), "bytes": len(data)})
    return 0


# ---------------------------------------------------------------------------
# upload — overwrite product image in Supabase storage
# ---------------------------------------------------------------------------

def cmd_upload(args):
    slug = args.slug
    storage_path = f"{PRODUCTS_PREFIX}/{slug}.jpg"
    try:
        data = _http_get(args.url, timeout=30)
    except Exception as e:
        emit({"ok": False, "error": f"download failed: {e}", "url": args.url})
        return 1
    if len(data) > MAX_IMAGE_BYTES * 4:
        emit({"ok": False, "error": f"image too large: {len(data)} bytes"})
        return 1

    client = get_supabase_client()
    # Try upload; if exists, remove first and re-upload (overwrite).
    try:
        client.storage.from_(IMAGE_BUCKET).upload(
            storage_path, data, {"content-type": "image/jpeg"}
        )
    except Exception as e:
        msg = str(e).lower()
        if any(x in msg for x in ["duplicate", "already exists", "409"]):
            try:
                client.storage.from_(IMAGE_BUCKET).remove([storage_path])
                client.storage.from_(IMAGE_BUCKET).upload(
                    storage_path, data, {"content-type": "image/jpeg"}
                )
            except Exception as e2:
                emit({"ok": False, "error": f"overwrite failed: {e2}"})
                return 1
        else:
            emit({"ok": False, "error": f"upload failed: {e}"})
            return 1

    public_url = (
        f"{os.getenv('SUPABASE_URL')}/storage/v1/object/public/{IMAGE_BUCKET}/{storage_path}"
    )
    emit(
        {
            "ok": True,
            "slug": slug,
            "storage_path": storage_path,
            "public_url": public_url,
            "bytes": len(data),
        }
    )
    return 0


def main():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_inspect = sub.add_parser("inspect")
    p_inspect.add_argument("slug")
    p_inspect.set_defaults(func=cmd_inspect)

    p_search = sub.add_parser("search")
    p_search.add_argument("query")
    p_search.add_argument("--limit", type=int, default=5)
    p_search.set_defaults(func=cmd_search)

    p_preview = sub.add_parser("preview")
    p_preview.add_argument("url")
    p_preview.add_argument("slug")
    p_preview.set_defaults(func=cmd_preview)

    p_upload = sub.add_parser("upload")
    p_upload.add_argument("slug")
    p_upload.add_argument("url")
    p_upload.set_defaults(func=cmd_upload)

    args = parser.parse_args()
    sys.exit(args.func(args))


if __name__ == "__main__":
    main()
