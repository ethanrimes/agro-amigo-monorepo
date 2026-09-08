"""Archive and publish official references without mixing currencies or price bases.

Source adapters own discovery and extraction. This module enforces quote identity,
validation and immutable revisions. Local wholesale projections remain separate.
"""

import hashlib
import json
import math
from datetime import date

from psycopg.types.json import Jsonb

VERSION = "official-v2"


def adapter(kind):
    if kind.startswith("international-"):
        from . import international_sources

        return international_sources
    if kind.startswith("colombia-"):
        from . import colombia_sources

        return colombia_sources
    raise ValueError("Unregistered official source kind")


def discover_roots(db):
    from .worker import queue

    for prefix in ("international-", "colombia-"):
        module = adapter(prefix)
        for url, kind in module.discover():
            queue(db, url, kind)


def publisher(kind):
    return adapter(kind).PUBLISHERS[kind]


def process(db, data, document_id, url, kind):
    from .worker import queue

    module = adapter(kind)
    for child_url, child_kind in module.discover(body=data, url=url, kind=kind):
        queue(db, child_url, child_kind)
    ocr_pages = ()
    try:
        rows = module.parse(data, url, kind)
    except getattr(
        module,
        "NormalExtractionFailed",
        type("UnusedExtractionFailure", (Exception,), {}),
    ) as exc:
        import io

        import pdfplumber

        from .ocr import VERSION as OCR_VERSION
        from .ocr import compare_readings, enqueue_image

        readings = {}
        with pdfplumber.open(io.BytesIO(data)) as pdf:
            for number in exc.required_pages:
                if number < 1 or number > len(pdf.pages):
                    raise ValueError("OCR requested a nonexistent page")
                page = pdf.pages[number - 1]
                enqueue_image(
                    db,
                    document_id,
                    f"PDF page {number}",
                    page.to_image(resolution=200).original,
                    kind,
                    number,
                )
                cached = db.execute(
                    "SELECT r.result FROM source_ocr_task t JOIN source_ocr_result r ON r.image_id=t.image_id WHERE t.document_id=%s AND t.source_page=%s AND r.version=%s ORDER BY r.reading",
                    (document_id, number, OCR_VERSION),
                ).fetchall()
                if len(cached) == 2 and compare_readings(cached[0][0], cached[1][0]):
                    readings[number] = cached[0][0]
        if len(readings) != len(exc.required_pages):
            return None
        rows = module.parse_with_ocr(data, url, kind, readings)
        ocr_pages = tuple(readings)
    count = publish_rows(db, rows, document_id, kind)
    if ocr_pages:
        db.execute(
            "UPDATE source_ocr_task SET status='published',checked_at=now(),error=NULL WHERE document_id=%s AND source_page=ANY(%s::integer[])",
            (document_id, list(ocr_pages)),
        )
    return count


def publish_rows(db, rows, document_id, kind=None):
    from .worker import parser_version, today

    if kind is None:
        original = db.execute(
            "SELECT metadata->>'ingestion_kind' FROM source_document WHERE id=%s",
            (document_id,),
        ).fetchone()
        if not original:
            raise ValueError("Official source document is missing")
        kind = original[0]
    revision = parser_version(kind)

    values = []
    reviews = []
    seen = {}
    locators = {}
    for row in rows:
        literal = json.dumps(row, sort_keys=True, default=str)
        locator = row["source_locator"]
        if locator in locators and locators[locator] != literal:
            raise ValueError(
                "Source locator maps to multiple official observations; include the exact market or column"
            )
        locators[locator] = literal
        issue = row.get("details", {}).get("quality_issue")
        if issue or row.get("price") is None:
            reviews.append(
                (
                    document_id,
                    row["source_locator"],
                    revision,
                    Jsonb(json.loads(json.dumps(row, default=str))),
                    issue or "No unambiguous positive price",
                )
            )
            continue
        day = row["date"]
        if isinstance(day, str):
            day = date.fromisoformat(day)
        if day > today():
            raise ValueError("Official observation is in the future")
        price = float(row["price"])
        low, high = row.get("min"), row.get("max")
        if not math.isfinite(price) or price <= 0:
            raise ValueError("Official price must be positive and finite")
        if any(
            v is not None and (not math.isfinite(float(v)) or float(v) <= 0)
            for v in (low, high)
        ):
            raise ValueError("Official price range is invalid")
        if (
            low is not None
            and high is not None
            and not float(low) <= price <= float(high)
        ):
            raise ValueError("Official price is outside the stated range")
        identity = {
            key: row[key]
            for key in ("product_id", "series", "market", "currency", "unit", "basis")
        }
        identity["dimensions"] = row.get("identity_dimensions", {})
        quote_key = hashlib.sha256(
            json.dumps(identity, sort_keys=True, ensure_ascii=False).encode()
        ).hexdigest()
        key = (quote_key, day)
        if key in seen and seen[key] != (price, low, high):
            raise ValueError(
                "Conflicting official quote identity; original retained for review"
            )
        seen[key] = (price, low, high)
        details = {
            **row.get("details", {}),
            "identity_dimensions": identity["dimensions"],
        }
        values.append(
            (
                document_id,
                row["source_locator"],
                revision,
                quote_key,
                row["product_id"],
                row["product_name"],
                row["category"],
                row["publisher"],
                row["series"],
                row["basis"],
                row["currency"],
                row["unit"],
                row["market"],
                day,
                row.get("period_start"),
                price,
                low,
                high,
                row.get("source_page") or details.get("source_page"),
                Jsonb(details),
            )
        )
    if reviews:
        with db.cursor() as cur:
            cur.executemany(
                "INSERT INTO official_source_review(document_id,source_locator,parser_version,record,reason) VALUES(%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING",
                reviews,
            )
    if values:
        columns = "document_id,source_locator,parser_version,quote_key,product_id,product_name,category,publisher,series,basis,currency,unit,market,observed_on,period_start,price,min_price,max_price,source_page,details"
        with db.transaction():
            db.execute(
                "CREATE TEMP TABLE official_stage (LIKE official_price_quote INCLUDING DEFAULTS) ON COMMIT DROP"
            )
            with db.cursor().copy(
                f"COPY official_stage ({columns}) FROM STDIN"
            ) as copy:
                for value in values:
                    copy.write_row(value)
            db.execute(
                f"INSERT INTO official_price_quote ({columns}) SELECT {columns} FROM official_stage ON CONFLICT DO NOTHING"
            )
        db.execute(
            "UPDATE ingestion_asset SET observed_on=%s WHERE document_id=%s",
            (max(value[13] for value in values), document_id),
        )
    return len(values)
