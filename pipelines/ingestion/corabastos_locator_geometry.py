"""Source-bound relocation guard; never publishes or writes data.

Only the source locator may change. New identities, money or package changes
remain held and require a separately reviewed source repair.
"""
from __future__ import annotations

import hashlib
import json
import re
from urllib.parse import urlsplit

from pipelines.ingestion import colombia_sources

KIND = "colombia-corabastos-pdf"
FIELDS = (
    "product_id", "product_name", "category", "publisher", "series", "basis",
    "currency", "unit", "market", "day", "period_start", "price", "min_price",
    "max_price", "source_page", "presentation", "quantity", "published_unit",
    "quality", "unit_price_as_published",
)
LOCATOR = re.compile(r"PDF page ([1-9]\d*), y (\d+\.\d); price column ([12])\Z")
MAX_BYTES = 8_000_000
MAX_QUOTES = 2000


def full20(row):
    details = row.get("details") or {}
    day = row.get("date", row.get("observed_on"))
    start = row.get("period_start")
    return {
        "source_locator": row["source_locator"],
        **{key: row[key] for key in FIELDS[:9]},
        "day": str(day), "period_start": str(start) if start else None,
        "price": float(row["price"]),
        "min_price": float(row["min_price"]) if row.get("min_price") is not None else None,
        "max_price": float(row["max_price"]) if row.get("max_price") is not None else None,
        "source_page": row.get("source_page") or details.get("source_page"),
        **{key: details.get(key) for key in FIELDS[15:]},
    }


def _index(rows):
    if not 0 < len(rows) <= MAX_QUOTES:
        raise ValueError("Source row count outside guard")
    identities, locators = {}, set()
    for row in rows:
        json.dumps(row, allow_nan=False, sort_keys=True)
        locator = row["source_locator"]
        match = LOCATOR.fullmatch(locator)
        if match is None or locator in locators:
            raise ValueError("Duplicate or invalid source locator")
        locators.add(locator)
        column = 1 if row["quality"] in ("extra", "desde") else 2 if row["quality"] in ("primera", "hasta") else 0
        if int(match[1]) != row["source_page"] or int(match[3]) != column:
            raise ValueError("Source page or price column mismatch")
        identity = tuple(row[key] for key in FIELDS)
        if identity in identities:
            raise ValueError("Ambiguous complete source identity")
        identities[identity] = (locator, match)
    return identities


def plan(document_id, source_url, body, previous, supplied):
    """Reparse exact retained bytes and require every old full20 identity unchanged.

    The eventual caller must read active prior quotes and original metadata in
    one transaction, retain replacements first and checkpoint last. The caller must bind this result to the reviewed publisher and version selector.
    """
    parsed_url = urlsplit(source_url)
    if (parsed_url.scheme != "https" or parsed_url.netloc != "corabastos.com.co"
        or parsed_url.query or parsed_url.fragment
        or not re.fullmatch(r"/wp-content/uploads/\d{4}/\d{2}/[^/]+\.pdf", parsed_url.path)):
        raise ValueError("Unrecognized official source URL")
    if not isinstance(body, bytes) or not 0 < len(body) <= MAX_BYTES or hashlib.sha256(body).hexdigest() != document_id:
        raise ValueError("Retained original content hash mismatch")
    native = [full20(row) for row in colombia_sources.parse(body, source_url, KIND)]
    actual, requested, old = _index(native), _index(supplied), _index(previous)
    if {key: item[0] for key, item in actual.items()} != {key: item[0] for key, item in requested.items()}:
        raise ValueError("Supplied source differs from complete retained native parse")
    if old.keys() != actual.keys():
        raise ValueError("Identity additions, removals or values require separate source review")
    moves = []
    for identity, (old_locator, old_match) in old.items():
        new_locator, new_match = actual[identity]
        if old_locator == new_locator:
            continue
        if old_match[1] != new_match[1] or old_match[3] != new_match[3]:
            raise ValueError("Locator crossed source page or price column")
        if abs(float(old_match[2]) - float(new_match[2])) > 3.0:
            raise ValueError("Locator movement exceeds reviewed geometry bound")
        moves.append((old_locator, new_locator, identity))
    if not moves:
        raise ValueError("No relocation requiring retirement")
    return {"retirements": tuple(sorted(moves)), "new_source_rows": (),
            "complete_source_quotes": len(native),
            "source_sha256": document_id, "source_url": source_url}
