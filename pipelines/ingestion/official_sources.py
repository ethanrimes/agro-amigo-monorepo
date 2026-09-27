"""Archive and publish official references without mixing currencies or price bases.

Source adapters own discovery and extraction. This module enforces quote identity,
validation and immutable revisions. Local wholesale projections remain separate.
"""

import hashlib
import json
import math
import time
from datetime import date

from psycopg.types.json import Jsonb

VERSION = "official-v2"


def is_reference_kind(kind):
    """Source families handled wholly by the official-reference publisher."""
    from . import dane_weekly

    return (
        kind.startswith(("international-", "colombia-"))
        or kind in dane_weekly.PUBLISHERS
    )


def adapter(kind):
    from . import dane_weekly

    if kind in dane_weekly.PUBLISHERS:
        return dane_weekly
    if kind in ("coffee", "coffee-pdf"):
        from . import coffee_sources

        return coffee_sources
    if kind.startswith("international-"):
        from . import international_sources

        return international_sources
    if kind.startswith("colombia-"):
        from . import colombia_sources

        return colombia_sources
    raise ValueError("Unregistered official source kind")


def discover_roots(db):
    from . import dane_weekly

    for module in (adapter("international-"), adapter("colombia-"), dane_weekly):
        for url, kind in module.discover():
            _queue_source(db, url, kind)


def _queue_source(db, url, kind):
    from . import dane_weekly
    from .worker import queue

    if kind in dane_weekly.PUBLISHERS and kind not in dane_weekly.INDEX_KINDS:
        queue(db, url, kind, dane_weekly.source_date(url))
    else:
        queue(db, url, kind)


def publisher(kind):
    return adapter(kind).PUBLISHERS[kind]


def process(db, data, document_id, url, kind):
    module = adapter(kind)
    for child_url, child_kind in (
        module.discover(body=data, url=url, kind=kind)
        if kind not in ("coffee", "coffee-pdf")
        else ()
    ):
        _queue_source(db, child_url, child_kind)
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
    if kind in ("coffee", "coffee-pdf"):
        rows = module.publication_rows(rows)
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
        literal = json.dumps(row, sort_keys=True, default=str, allow_nan=False)
        locator = row["source_locator"]
        if not isinstance(locator, str) or not locator.strip():
            raise ValueError("Official source locator must be nonempty text")
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
        for field in (
            "product_id",
            "product_name",
            "category",
            "publisher",
            "series",
            "basis",
            "currency",
            "unit",
            "market",
        ):
            if not isinstance(row.get(field), str) or not row[field].strip():
                raise ValueError(f"Official {field} must be nonempty text")
        if row["currency"] not in {"COP", "USD", "EUR", "GBP"}:
            raise ValueError("Unsupported official currency")
        day = row["date"]
        if isinstance(day, str):
            day = date.fromisoformat(day)
        if not isinstance(day, date):
            raise ValueError("Official observation date is invalid")
        period_start = row.get("period_start")
        if isinstance(period_start, str):
            period_start = date.fromisoformat(period_start)
        if period_start is not None and (
            not isinstance(period_start, date) or period_start > day
        ):
            raise ValueError("Official period starts after its observation date")
        source_page = row.get("source_page") or row.get("details", {}).get(
            "source_page"
        )
        if source_page is not None and (
            type(source_page) is not int or not 1 <= source_page <= 2147483647
        ):
            raise ValueError("Official source page is invalid")
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
        json.dumps(details, allow_nan=False)
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
                period_start,
                price,
                low,
                high,
                source_page,
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
        # Validate the entire source first, then retain bounded batches. Existing
        # immutable rows make a resumed asset idempotent without firing insert
        # triggers for every already-published quote. A caller's outer transaction
        # still preserves its own atomicity (for example a retained PDF replay).
        from .resumable_inputs import WorkDeferred
        from .worker import RUN_DEADLINE

        for start in range(0, len(values), 2000):
            deadline = RUN_DEADLINE.get()
            if deadline is not None and time.monotonic() >= deadline:
                raise WorkDeferred(
                    "Official source validated; committed quote batches will resume"
                )
            with db.transaction():
                db.execute(
                    "CREATE TEMP TABLE IF NOT EXISTS official_stage (LIKE official_price_quote INCLUDING DEFAULTS) ON COMMIT DROP"
                )
                db.execute("TRUNCATE pg_temp.official_stage")
                with db.cursor().copy(
                    f"COPY official_stage ({columns}) FROM STDIN"
                ) as copy:
                    for value in values[start : start + 2000]:
                        copy.write_row(value)
                db.execute(
                    f"INSERT INTO official_price_quote ({columns}) SELECT {columns} FROM official_stage s "
                    "WHERE NOT EXISTS(SELECT 1 FROM official_price_quote q "
                    "WHERE q.document_id=s.document_id AND q.source_locator=s.source_locator "
                    "AND q.parser_version=s.parser_version) ON CONFLICT DO NOTHING"
                )
        db.execute(
            "UPDATE ingestion_asset SET observed_on=%s WHERE document_id=%s",
            (max(value[13] for value in values), document_id),
        )
    from .resumable_inputs import WorkDeferred
    from .worker import RUN_DEADLINE

    deadline = RUN_DEADLINE.get()
    if deadline is not None and time.monotonic() >= deadline:
        raise WorkDeferred(
            "Official quote batches retained; catalog completion will resume"
        )
    with db.transaction():
        from .official_catalog import refresh_document

        refresh_document(db, document_id)
        db.execute(
            "INSERT INTO ingestion_checkpoint(document_id,processor_version,step,records) "
            "VALUES(%s,%s,'official:complete',%s) ON CONFLICT DO NOTHING",
            (document_id, revision, len(values)),
        )
    return len(values)
