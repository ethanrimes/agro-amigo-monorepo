"""Source-bound retained replay for three untyped DANE February 2014 XLS files.

Only the pinned legacy pending/failed source states can use this no-network
path. The readable native cells are preserved in one document-level review;
they are never converted into typed prices.
"""

from __future__ import annotations

from hashlib import sha256
import re

from .reviewed_weekly_feb2014 import (
    PAIRS,
    REVIEW_LOCATOR,
    REVIEW_MARKER,
    review as review_feb2014,
)


KIND = "dane-weekly-xlsx"
XLS_MEDIA = "application/vnd.ms-excel"
PDF_MEDIA = "application/pdf"
REFERENCE_TEXT = "Serie histórica completa"
OLD_FAILURES = {
    "feb8_2014": None,
    "feb15_2014": "ValueError: Weekly grouped workbook has no explicit period in cells or URL",
    "feb22_2014": "ValueError: Weekly grouped workbook has no explicit period in cells or URL",
}
FEB8_429 = re.compile(
    r"HTTP 429 from www[.]dane[.]gov[.]co; retry after "
    r"20[0-9]{2}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}"
    r"(?:[.][0-9]+)?[+]00:00"
)


def _review_rows(db, document_id):
    return db.execute(
        "SELECT source_locator,parser_version,record,reason "
        "FROM official_source_review WHERE document_id=%s "
        "ORDER BY source_locator,parser_version",
        (document_id,),
    ).fetchall()


def retained_feb2014_original(db, url, kind, asset_version, quote_version=None):
    """Return exact retained XLS bytes for eligible legacy failures only.

    Current completed/review states deliberately return ``None`` so normal
    source refresh behavior remains in control. Any mismatch after an exact
    source match raises, preventing a network fallback around bad evidence.
    """
    case = PAIRS.get(url)
    if case is None or kind != KIND:
        return None
    from .worker import asset_parser_version, parser_version

    expected_version = asset_parser_version(kind, url)
    if asset_version != expected_version or quote_version != expected_version:
        return None
    legacy_version = parser_version(kind)
    suffix = ":reviewed-feb2014-period-untyped-v1"
    if suffix not in expected_version or expected_version.replace(suffix, "") != legacy_version:
        raise ValueError("February 2014 retained repair version binding changed")

    asset = db.execute(
        """SELECT a.status,a.document_id,a.observed_on,a.processor_version,a.records,a.error,
                  d.id,d.title,d.publisher,d.source_url,d.media_type,d.kind,d.reference_period,
                  d.page_count,d.content,d.metadata
           FROM ingestion_asset a JOIN source_document d ON d.id=a.document_id
           WHERE a.url=%s AND a.kind=%s""",
        (url, kind),
    ).fetchone()
    if asset is None:
        return None
    status, asset_did, observed_on, old_version, records, error = asset[:6]
    (document_id,title,publisher,source_url,media_type,document_kind,reference_period,
     page_count,content,metadata) = asset[6:]
    filename = url.rsplit("/", 1)[-1]
    key = filename.removeprefix("Anexo_Bol_Semanal_").removesuffix(".xls")
    old_error = OLD_FAILURES[key]
    exact_old_error = (
        bool(error and FEB8_429.fullmatch(error)) if key == "feb8_2014"
        else error == old_error
    )
    if not (
        status in ("pending", "failed")
        and asset_did == case["xls_sha"]
        and observed_on is None
        and old_version == legacy_version
        and records == 0
        and exact_old_error
    ):
        return None

    expected_metadata = {
        "retention": "permanent",
        "ingestion_kind": KIND,
        "original_filename": filename,
    }
    if (
        document_id != case["xls_sha"]
        or title != "DANE · SIPSA - " + filename
        or publisher != "DANE · SIPSA"
        or source_url != url
        or media_type != XLS_MEDIA
        or document_kind != "original"
        or reference_period != REFERENCE_TEXT
        or page_count is not None
        or (metadata or {}) != expected_metadata
    ):
        raise ValueError("Exact February 2014 XLS original metadata changed")
    body = bytes(content or b"")
    if len(body) != case["xls_size"] or sha256(body).hexdigest() != case["xls_sha"]:
        raise ValueError("Exact February 2014 XLS original SHA or size changed")

    paired_pdf = db.execute(
        """SELECT id,title,publisher,source_url,media_type,kind,reference_period,
                  page_count,content,metadata
           FROM source_document WHERE id=%s""",
        (case["pdf_sha"],),
    ).fetchone()
    pdf_filename = case["pdf_url"].rsplit("/", 1)[-1]
    expected_pdf_metadata = {
        "retention": "permanent",
        "ingestion_kind": "dane-weekly-pdf",
        "original_filename": pdf_filename,
    }
    if (
        paired_pdf is None
        or paired_pdf[0] != case["pdf_sha"]
        or paired_pdf[1] != "DANE · SIPSA - " + pdf_filename
        or paired_pdf[2] != "DANE · SIPSA"
        or paired_pdf[3] != case["pdf_url"]
        or paired_pdf[4] != PDF_MEDIA
        or paired_pdf[5] != "original"
        or str(paired_pdf[6]) != case["period_end"]
        or paired_pdf[7] not in (44, 48)
        or (paired_pdf[7] == 48) != (url == list(PAIRS)[2])
        or (paired_pdf[9] or {}) != expected_pdf_metadata
    ):
        raise ValueError("Exact February 2014 paired PDF metadata changed")
    pdf_body = bytes(paired_pdf[8] or b"")
    if not pdf_body.startswith(b"%PDF-") or sha256(pdf_body).hexdigest() != case["pdf_sha"]:
        raise ValueError("Exact February 2014 paired PDF SHA changed")

    if db.execute(
        "SELECT 1 FROM official_price_quote WHERE document_id=%s LIMIT 1", (document_id,)
    ).fetchone():
        raise ValueError("February 2014 XLS already has typed price quotes")
    if db.execute(
        "SELECT 1 FROM regional_price WHERE document_id=%s LIMIT 1", (document_id,)
    ).fetchone() or db.execute(
        "SELECT 1 FROM historical_price WHERE document_id=%s LIMIT 1", (document_id,)
    ).fetchone():
        raise ValueError("February 2014 XLS already has typed regional or historical prices")

    review_rows = review_feb2014(db, body, document_id, url)
    if len(review_rows) != 1 or review_rows[0].get("price") is not None:
        raise ValueError("February 2014 retained review did not remain unpriced")
    existing = _review_rows(db, document_id)
    if existing:
        raise ValueError("February 2014 legacy source already has review rows")
    checkpoint = db.execute(
        "SELECT records FROM ingestion_checkpoint WHERE document_id=%s "
        "AND processor_version=%s AND step='official:complete'",
        (document_id, expected_version),
    ).fetchone()
    if checkpoint is not None:
        raise ValueError("February 2014 legacy source already has a completion checkpoint")
    return body


def eligible_during_host_cooldown(db, url, kind):
    """True only when exact legacy Feb source work needs no publisher HTTP."""
    if url not in PAIRS or kind != KIND:
        return False
    from .worker import asset_parser_version

    try:
        return retained_feb2014_original(
            db, url, kind, asset_parser_version(kind, url), asset_parser_version(kind, url)
        ) is not None
    except ValueError:
        # Surface this exact-source integrity error locally without HTTP fallback.
        return True
