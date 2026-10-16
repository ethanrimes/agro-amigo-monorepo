"""Exact retained September 2014 DANE input PDF department spelling review.

The original prints ``Armenia (Quindio)`` three times. These rows name the
validated department Quindío while retaining the literal printed text. The
whole PDF, not merely the three additions, is validated before publication.
"""

import hashlib
import json
import unicodedata
from datetime import date
from decimal import Decimal

URL = (
    "https://www.dane.gov.co/files/investigaciones/agropecuario/sipsa/"
    "insumos_factores_de_produccion_sep_2014.pdf"
)
SHA256 = "14784c8d8f7e4c25b9715d2c2828ae2568aebfda6ce14f615f56288c97f61c3f"
DAY = date(2014, 9, 30)
VERSION = "inputs-pdf-v16"
FULL_ROWS = 7245
FULL_ROWS_SHA256 = "31f62b94ba55b13e284248879de84ffe1baee917ffaf0cf38f3c54266e4ca938"
REVIEWED_ROWS = (
    ("PDF page 34,col 1,y 227.3; inputs-pdf-v16", "Todo en Uno", "1 kilogramo", 3633, 0.0),
    ("PDF page 34,col 2,y 691.3; inputs-pdf-v16", "Wuxal Tapa Negra", "1 litro", 30300, 0.3),
    ("PDF page 35,col 1,y 451.3; inputs-pdf-v16", "Wuxal Tapa Roja", "1 litro", 26900, 0.6),
)


def _fold(label):
    return "".join(
        char for char in unicodedata.normalize("NFKD", label)
        if not unicodedata.combining(char)
    ).casefold()


def _departments():
    from .special_prices import DEPARTMENTS

    names = {}
    for canonical in DEPARTMENTS:
        folded = _fold(canonical)
        if folded in names and names[folded] != canonical:
            raise ValueError("Validated departments collide after accent/case folding")
        names[folded] = canonical
    return names


def canonical_department(label):
    """An exact unique validated name after accent/case folding, or None."""
    return _departments().get(_fold(label))


def validate_rows(rows):
    if len(rows) != FULL_ROWS or len({row[0] for row in rows}) != FULL_ROWS:
        raise ValueError("September 2014 input PDF is incomplete or has duplicate locators")
    digest = hashlib.sha256(json.dumps(
        rows, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str,
    ).encode("utf-8")).hexdigest()
    if digest != FULL_ROWS_SHA256:
        raise ValueError("September 2014 input PDF full source projection changed")
    by_locator = {row[0]: row for row in rows}
    for locator, name, presentation, price, variation in REVIEWED_ROWS:
        row = by_locator[locator]
        if (row[1], row[2], row[3], row[4], row[5], row[6], row[7]) != (
            "dane-inputs-pdf", DAY, name, "Armenia", presentation, price, variation
        ) or row[-1]["category"] != "Fertilizantes y enmiendas" or (
            row[-1]["department"], row[-1]["municipality"],
            row[-1]["printed_location_lines"], row[-1]["parser_version"],
        ) != ("Quindío", "Armenia", ["Armenia (Quindio)"], VERSION):
            raise ValueError("Reviewed September 2014 Armenia source cell changed")
    return rows


def parse_reviewed_quindio_sep2014(data, day, url):
    if (
        url != URL or day != DAY or not data.startswith(b"%PDF-")
        or hashlib.sha256(data).hexdigest() != SHA256
    ):
        raise ValueError("September 2014 input repair requires exact URL, date and PDF SHA")
    from .pdf_sources import parse_input_pdf

    return validate_rows(list(parse_input_pdf(data, day, parser_version=VERSION)))


def assert_stored_version_rows(db, rows, *, complete=False):
    """Refuse a pre-existing same-locator row with different immutable data."""
    expected = {row[0]: row for row in rows}
    found = db.execute(
        """SELECT source_locator,series,observed_on,product_name,market_name,
                  unit,price,change_percent,details
           FROM historical_price WHERE document_id=%s
             AND (source_locator LIKE '%%; inputs-pdf-v16'
                  OR details->>'parser_version'=%s)""",
        (SHA256, VERSION),
    ).fetchall()
    if complete and len(found) != FULL_ROWS:
        raise ValueError("September 2014 v16 stored row count is incomplete")
    for locator, series, day, name, market, unit, price, variation, details in found:
        parsed = expected.get(locator)
        if parsed is None or (
            (series, day, name, market, unit, Decimal(str(price)),
             Decimal(str(variation)) if variation is not None else None, details)
            !=
            (parsed[1], parsed[2], parsed[3], parsed[4], parsed[5],
             Decimal(str(parsed[6])),
             Decimal(str(parsed[7])) if parsed[7] is not None else None,
             parsed[8])
        ):
            raise ValueError("September 2014 retained v16 price cell conflicts with original")
    return len(found)


def retained_exact_quindio_pdf(db, url, kind, expected_version):
    """Use only the matching immutable original; never fetch around bad bytes."""
    if url != URL or kind != "inputs-pdf" or expected_version != VERSION:
        return None
    row = db.execute(
        """SELECT d.content FROM ingestion_asset a JOIN source_document d
           ON d.id=a.document_id
           WHERE a.url=%s AND a.kind='inputs-pdf' AND a.observed_on=%s
             AND a.document_id=%s AND a.status IN ('complete','review','failed','pending')
             AND d.id=%s AND d.kind='original' AND d.source_url=a.url
             AND d.media_type='application/pdf'
             AND d.metadata->>'ingestion_kind'='inputs-pdf'
             AND NOT coalesce((a.processor_version ~ '^inputs-pdf-v[0-9]+$'
               AND substring(a.processor_version from '([0-9]+)$')::numeric>16),false)
             AND NOT EXISTS (
               SELECT 1 FROM ingestion_checkpoint c
               WHERE c.document_id=a.document_id AND c.step='inputs-pdf:published'
                 AND c.processor_version ~ '^inputs-pdf-v[0-9]+$'
                 AND substring(c.processor_version from '([0-9]+)$')::numeric>=16)
           LIMIT 1""",
        (URL, DAY, SHA256, SHA256),
    ).fetchone()
    if row is None:
        return None
    body = bytes(row[0] or b"")
    if not body.startswith(b"%PDF-") or hashlib.sha256(body).hexdigest() != SHA256:
        raise ValueError("Retained September 2014 input PDF bytes differ from immutable SHA")
    return body
