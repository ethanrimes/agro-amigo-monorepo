"""Reviewed spelling cleanup of published labels, never raw source identities.

The shared lexicon is also used by the app. Matching is against entire labels;
unknown words, commercial names, varieties and numerical dimensions are never
fuzzy-matched. Native PDF geometry/continuation repairs remain in their typed
adapters, where the original glyphs and every other price cell can be verified.
"""

import hashlib
import json
import re
import time
import unicodedata
from pathlib import Path

from psycopg.types.json import Jsonb

LEXICON_PATH = Path(__file__).resolve().parents[2] / "shared/label-normalization.json"
LEXICON_BYTES = LEXICON_PATH.read_bytes()
LEXICON_SHA256 = hashlib.sha256(LEXICON_BYTES).hexdigest()
LEXICON = json.loads(LEXICON_BYTES)
# Audit/checkpoint identity includes code semantics as well as dictionary bytes.
# rules-v2 canonicalizes category parts after separator-whitespace hygiene.
RULES_VERSION = "rules-v2"
VERSION = LEXICON["version"] + ":" + LEXICON_SHA256[:16] + ":" + RULES_VERSION
_VOWELS = str.maketrans("áéíóúü", "aeiouu")
_INVISIBLE = str.maketrans("", "", "\u00ad\u200b\ufeff")
_WHITE_SPACE = re.compile(r"[\t\n\v\f\r \u0085\u00a0\u1680\u2000-\u200a\u2028\u2029\u202f\u205f\u3000]+")


def hygiene(value):
    if not isinstance(value, str):
        raise TypeError("A label must be text")
    text = unicodedata.normalize("NFC", value).translate(_INVISIBLE)
    return _WHITE_SPACE.sub(" ", text).strip(" ")


def key(value):
    # Keep ñ, punctuation, digits, spaces and all commercial dimensions.
    return hygiene(value).lower().translate(_VOWELS)


def _lexicon():
    result = {}
    for domain, labels in LEXICON["domains"].items():
        entries = {}
        for label in labels:
            if not isinstance(label, str) or hygiene(label) != label:
                raise ValueError("Canonical labels must already be clean text")
            k = key(label)
            if k in entries and entries[k] != label:
                raise ValueError("Ambiguous canonical spelling: " + domain + ": " + k)
            entries[k] = label
        for alias, canonical in LEXICON.get("aliases", {}).get(domain, {}).items():
            k = key(alias)
            if (not k or hygiene(alias) != alias
                    or entries.get(key(canonical)) != canonical
                    or k in entries and entries[k] != canonical):
                raise ValueError("Unreviewed or ambiguous label alias: " + domain + ": " + alias)
            entries[k] = canonical
        result[domain] = entries
    for entry in LEXICON.get("product_display_only", []):
        raw, target, product_id = entry["raw"], entry["canonical"], entry["product_id"]
        k = key(raw)
        if (hygiene(raw) != raw or hygiene(target) != target
                or not k or k != key(target) or _slug(raw) != product_id
                or _slug(target) != product_id
                or k in result["product"] and result["product"][k] != target):
            raise ValueError("Unreviewed or identity-changing product display label")
        result["product"][k] = target
    selectors = set()
    for entry in LEXICON.get("source_scoped_product_display_only", []):
        try:
            document_id = entry["document_id"]
            locator = entry["source_locator"]
            product_id = entry["product_id"]
            source_product = entry["source_product"]
            raw, target = entry["raw"], entry["canonical"]
        except (KeyError, TypeError) as error:
            raise ValueError("Incomplete source-scoped product display rule") from error
        if (not isinstance(document_id, str) or not re.fullmatch(r"[a-f0-9]{64}", document_id)
                or not all(isinstance(value, str) and value for value in
                           (locator, product_id, source_product, raw, target))
                or hygiene(raw) != raw or hygiene(source_product) != source_product
                or hygiene(target) != target or key(raw) != key(source_product)
                or _slug(raw) != product_id
                or result["product"].get(key(target)) != target):
            raise ValueError("Unreviewed, duplicate or ambiguous source-scoped product display rule")
        selector = (document_id, locator, product_id, raw, source_product)
        if selector in selectors:
            raise ValueError("Unreviewed, duplicate or ambiguous source-scoped product display rule")
        selectors.add(selector)
    return result


def _slug(value):
    plain = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", plain.lower()).strip("-")


LOOKUP = _lexicon()


def normalize(value, domain="product"):
    if domain not in (*LOOKUP, "input"):
        raise ValueError("Unknown label domain: " + str(domain))
    clean = hygiene(value)
    # Commercial input names are not the food-product dictionary. In
    # particular, a grade/brand/ICA number cannot be discarded as a typo.
    return LOOKUP.get(domain, {}).get(key(clean), clean)


def category(value):
    # Match the app: normalize separator whitespace before recognizing a path.
    return " > ".join(normalize(part, "category") for part in hygiene(value).split(" > "))


def product_label(value):
    """Clean metadata only when the existing published identity stays intact."""
    cleaned = normalize(value, "product")
    # The exact retained Cali city PDF prints one transposed variety spelling.
    # Its raw product ID remains limon-thaiti; only published label metadata
    # may use the reviewed Tahití spelling. All other cross-slug aliases stay held.
    if hygiene(value).casefold() == "limón thaití" and cleaned == "Limón Tahití":
        return cleaned
    return cleaned if _slug(value) == _slug(cleaned) else value


def official_product_label(row):
    """Display-only source projection; never call from identity or ingestion code."""
    product_name = row.get("product_name")
    if not isinstance(product_name, str):
        return product_name
    details = row.get("details")
    identity = details.get("identity_dimensions") if isinstance(details, dict) else None
    source_product = identity.get("source_product") if isinstance(identity, dict) else None
    matches = [entry for entry in LEXICON.get("source_scoped_product_display_only", [])
               if row.get("document_id") == entry["document_id"]
               and row.get("source_locator") == entry["source_locator"]
               and row.get("product_id") == entry["product_id"]
               and product_name == entry["raw"]
               and source_product == entry["source_product"]]
    if len(matches) > 1:
        raise ValueError("Ambiguous source-scoped product display match")
    return matches[0]["canonical"] if matches else product_label(product_name)


def change(value, domain):
    cleaned = category(value) if domain == "category" else normalize(value, domain)
    if cleaned == value:
        return None
    return {
        "original": value,
        "normalized": cleaned,
        "domain": domain,
        "version": VERSION,
        "dictionary_sha256": LEXICON_SHA256,
        "method": "exact-reviewed-label" if (
            key(value) in LOOKUP.get(domain, {}) or domain == "category"
            and any(key(part) in LOOKUP["category"] for part in hygiene(value).split(" > "))
        )
        else "unicode-whitespace",
    }


def drain(db, *, limit=1000, deadline=None):
    """Bounded cyclic scan; atomic label/audit/cursor writes, no raw-row writes.

    This runs before and after ordinary publication. A persistent keyset cursor
    covers existing metadata without making the historical backlog wait for a
    full-table rebuild. A completed cycle restarts so new or revised labels at
    an earlier key are cleaned too. Failure cannot advance a checkpoint.
    """
    if not 1 <= limit <= 5000:
        raise ValueError("Label scan limit must be 1..5000")
    result = {"version": VERSION, "available": False, "scanned": 0,
              "changed": 0, "cycle_complete": False, "deferred": False}
    if deadline is not None and time.monotonic() >= deadline:
        result["deferred"] = True
        return result
    available = db.execute(
        "SELECT to_regclass('published_label_correction'),"
        "to_regclass('published_label_scan')"
    ).fetchone()
    if not available or not all(available):
        return result
    result["available"] = True
    while result["scanned"] < limit:
        if deadline is not None and time.monotonic() >= deadline:
            result["deferred"] = True
            break
        # Independent committed pages prevent a slow network or many changed
        # labels from rolling back an entire thousand-row pass forever.
        size = min(64, limit - result["scanned"])
        scanned, changed, complete = _batch(db, size, deadline)
        result["scanned"] += scanned
        result["changed"] += changed
        result["cycle_complete"] = complete
        if complete:
            break
    return result


def _batch(db, size, deadline):
    changed = 0
    with db.transaction():
        remaining = 5000 if deadline is None else max(1, min(
            5000, int((deadline - time.monotonic()) * 1000)))
        db.execute("SELECT set_config('statement_timeout',%s,true)", (str(remaining),))
        db.execute("SET LOCAL lock_timeout='2s'")
        db.execute("INSERT INTO published_label_scan(version,entity) VALUES(%s,'product') "
                   "ON CONFLICT DO NOTHING", (VERSION,))
        after = db.execute(
            "SELECT after_id FROM published_label_scan WHERE version=%s "
            "AND entity='product' FOR UPDATE", (VERSION,)
        ).fetchone()[0]
        rows = db.execute(
            "SELECT id,name,category FROM product WHERE id>%s ORDER BY id LIMIT %s",
            (after, size),
        ).fetchall()
        for ident, literal_name, literal_category in rows:
            if deadline is not None and time.monotonic() >= deadline:
                # Roll back the entire batch, including label changes/audits.
                raise TimeoutError("Label normalization batch deadline reached")
            changes = []
            name = product_label(literal_name)
            group = category(literal_category)
            if name != literal_name:
                changes.append(("name", change(literal_name, "product")))
            if group != literal_category:
                changes.append(("category", change(literal_category, "category")))
            for field, evidence in changes:
                old = db.execute(
                    "SELECT normalized_value FROM published_label_correction "
                    "WHERE version=%s AND entity='product' AND entity_id=%s "
                    "AND field=%s AND original_value=%s",
                    (VERSION, ident, field, evidence["original"]),
                ).fetchone()
                if old and old[0] != evidence["normalized"]:
                    raise ValueError("Immutable spelling correction conflicts with candidate")
                db.execute(
                    "INSERT INTO published_label_correction(version,entity,entity_id,field,"
                    "original_value,normalized_value,evidence) "
                    "VALUES(%s,'product',%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING",
                    (VERSION, ident, field, evidence["original"],
                     evidence["normalized"], Jsonb(evidence)),
                )
            if changes:
                db.execute("UPDATE product SET name=%s,category=%s WHERE id=%s "
                           "AND name=%s AND category=%s",
                           (name, group, ident, literal_name, literal_category))
                changed += 1
        complete = len(rows) < size
        db.execute("UPDATE published_label_scan SET after_id=%s,scanned_at=now() "
                   "WHERE version=%s AND entity='product'",
                   ("" if complete else rows[-1][0], VERSION))
    return len(rows), changed, complete
